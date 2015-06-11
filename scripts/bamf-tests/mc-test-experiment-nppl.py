import matplotlib as mpl
mpl.use('Agg')
import matplotlib.gridspec as gridspec
import pylab as pl

import copy
import scipy as sp
import numpy as np
import scipy.ndimage as nd
from scipy.misc import imread

from colloids.cu import nbody, fields, mc
from colloids.salsa import process
from colloids.sim import Sim
import colloids.bamf.initialize as sf

SEED = 10
nbody.initializeDevice(0)
nbody.setSeed(SEED)
mc.setSeed(SEED)
np.random.seed(SEED)

TRUECUT = 128
NNG = TRUECUT
NNZ = 16
CUT = NNZ/2
gfield = fields.createField(np.array([NNG,NNG,NNZ], dtype='int32'))
fields.setupFFT(gfield)
sigma = 0.15

def create_exp_data(filename='./data/colloid-2d-slice.png'):
    from skimage.feature import peak_local_max
    tim = imread(filename)
    ff = np.fft.fftfreq(tim.shape[-1])
    fr = np.sqrt(ff[:,None]**2 + ff[None,:]**2)
    im = np.real( np.fft.ifftn( np.fft.fftn(tim) * (fr > 0.02)) )
    z = peak_local_max(nd.gaussian_filter(im,3, mode='reflect'), min_distance=10).astype('float32')
    pos = np.hstack([z[:,1][:,None], z[:,0][:,None], np.ones((z.shape[0],1))]).astype('float32')

    newpos = pos[pos[:,0] < TRUECUT]
    newpos = newpos[newpos[:,1] < TRUECUT]
    tim = tim[:TRUECUT,:TRUECUT].astype('float32')
    tim -= tim.min()
    tim /= tim.max()

    NPARTICLES = 32
    sim = Sim(NPARTICLES, radius=9.5)
    sim.init_from_positions(newpos[:NPARTICLES,:], radius=9.5, shell=1)
    return tim, sim

def perturb_radii(out, mu=10.0, sigma=0.1):
    rad = np.zeros(out.N, dtype='float32')
    nbody.simGetRadii(out.sim, rad)
    rad = mu - sigma*np.random.rand(out.N)
    nbody.simSetRadii(out.sim, rad.astype('float32'))

def sample_hamiltonian(sim, NN=100):
    sim.do_steps(NN)

def sample_radii(sim, mu=10.0, sigma=5.0, n=2):
    mc.propose_particle_radius(sim.sim, sim.nn, mu, sigma, n)

def sample_psf(psf, sigma=20):
    #psf -= sigma*(2*np.random.rand(*psf.shape)-1)
    psf = (0.3 + sigma*np.random.rand(*psf.shape)).astype('float32')
    #psf = (sigma + sigma*(2*np.random.rand(*psf.shape)-1)).astype('float32')
    #psf[0] = abs(psf[0])
    #psf[3] = abs(psf[3])
    return psf
    #return psf - sigma*(2*np.random.rand(*psf.shape)-1).astype('float32')

def psfval(psf):
    x = np.linspace(0.001, np.pi, 10000)
    y = np.polyval(psf[0:3][::-1], x*psf[-1]) / np.polyval(psf[3:-1][::-1], x*psf[-1])
    return x,y

def plot_single(x, L):
    pl.figure()
    pl.imshow(genimage(x,L), cmap=mpl.cm.bone, interpolation='nearest')

def plot_compare(*imgs):
    imgs = list(imgs)
    fig = pl.figure()
    gs = gridspec.GridSpec(1, len(imgs))
    gs.update(left=0.05, right=0.9, hspace=0.05, wspace=0.1)

    for i in xrange(len(imgs)):
        ax = pl.subplot(gs[0,i])
        ax.imshow(imgs[i][4,:,:], cmap=mpl.cm.bone, interpolation='nearest')
        ax.set_xticks([])
        ax.set_yticks([])

def gen_image(ss, params, donoise=False):
    t = np.zeros((NNZ,NNG,NNG), dtype='float32').flatten()

    fields.fieldSet(gfield, t)
    fields.process_image(gfield, ss.sim, params, fields.PSF_ISOTROPIC_DISC)
    #fields.process_image(gfield, ss.sim, params, fields.PSF_ISOTROPIC_PADE_3_5)

    fields.fieldGet(gfield, t)
    t = t.reshape(NNZ,NNG,NNG)
    t -= t.min()
    t /= t.max()
    #tslice = np.s_[:]
    tslice = np.s_[CUT,:,:]
    if donoise:
        noise = np.random.normal(0, sigma/1, (NNZ,NNG,NNG))
        return (t+noise)[tslice], noise[tslice]
    return t[tslice]

def likelihood(iguess, itrue):
    return np.exp(loglikelihood(igues, itrue))

def loglikelihood(iguess, itrue):
    return -((iguess - itrue)**2).sum() / (2*sigma**2)

#def dosample_mcmc():
if True:
    itrue, sim = create_exp_data()
    sim.set_param_mc()

    psf = np.ones((9), dtype='float32')
    psf = np.ones((2), dtype='float32')
    psf[0] = 1.7
    psf[1] = 100
    istart = gen_image(sim, psf)
    xstart = sim.get_pos()
    rstart = sim.get_radii()

    nwarm = int(8e3)
    nsteps = nwarm + int(1e3)

    pguess = 0*psf
    rguess = np.zeros(sim.N, dtype='float32')
    guess, std, total = 0*xstart, 0*xstart, 0
    positions, crosses = [], []
    lnew = lold = loglikelihood(istart, itrue)
    accepts = 0

    for i in xrange(nsteps):
        vsig = 20.#20*np.random.rand()#10.0000
        simcopy = copy.deepcopy(sim)
        psfcopy = psf[:]
        nbody.init_set_random_velocities(sim.sim, 0, vsig)
        startv = sim.get_vel()

        if i % 3 == 0:
            sample_hamiltonian(sim, 40)
        elif i % 3 == 1:
            sample_radii(sim, mu=10.5, sigma=2.00, n=2)
        elif i % 3 == 2:
            sample_radii(sim, mu=10.5, sigma=2.00, n=4)
            #psf = sample_psf(psf)

        t = sim.get_pos()
        r = sim.get_radii()
        im = gen_image(sim, psf)
        lnew = loglikelihood(im, itrue)

        endv = sim.get_vel()
        vfact1 = np.exp(-(startv**2).sum(axis=-1).mean()/(2*(vsig**2)))
        vfact2 = np.exp(-(endv**2).sum(axis=-1).mean()/(2*(vsig**2)))

        acceptance = np.exp(lnew-lold)
        #acceptance *= pnew/pold
        #acceptance *= np.exp(pnew-pold)
        acceptance *= (vfact1/vfact2)

        if i % 50 == 1:
            print i, 'ratio', lnew, lold, acceptance, total, float(accepts)/i

        if np.random.rand() < min(acceptance, 1):
            lold = lnew
            accepts += 1
        else:
            psf = psfcopy[:]
            nbody.simsys_cpu2cpu(simcopy.sim, sim.sim)
        if i > nwarm and i % 100 == 0:
            total += 1
            guess += t
            std += t*t
            rguess += r
            pguess += psf

    rguess /= total
    pguess /= total
    guess /= total
    std = np.sqrt(std/total - guess**2)

    sim.set_pos(guess)
    sim.set_radii(rguess)
    iguess = gen_image(sim, pguess)

    """
    r = PPL*np.sqrt(((guess - xtrue)**2)[:,:2].sum(-1))
    print r.mean(), r.std()#, std
    plot_compare(itrue, istart, iguess, itrue-iguess-ntrue)
    """
