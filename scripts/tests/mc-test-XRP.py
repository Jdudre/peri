import matplotlib as mpl
mpl.use('Agg')
import matplotlib.gridspec as gridspec
import pylab as pl

import copy
import scipy as sp
import numpy as np
import scipy.ndimage as nd

from colloids.cu import nbody, fields, mc
from colloids.salsa import process
from colloids.sim import Sim

SEED = 10
nbody.initializeDevice(0)
nbody.setSeed(SEED)
mc.setSeed(SEED)
np.random.seed(SEED)

def generate_configuration(N=8, radius=5.0, phi=0.63):
    out = Sim(N, radius=radius)
    out.init_random_2d(phi=phi)

    perturb_radii(out, mu=radius, sigma=0.10)
    out.do_relaxation(2000)
    return out

def perturb_radii(out, mu=5.0, sigma=0.1):
    rad = np.zeros(out.N, dtype='float32')
    nbody.simGetRadii(out.sim, rad)
    rad = mu - sigma*np.random.rand(out.N)
    nbody.simSetRadii(out.sim, rad.astype('float32'))

def sample_hamiltonian(sim, NN=100):
    sim.do_steps(100)

def sample_radii(sim, mu=5.0, sigma=0.1, n=2):
    mc.propose_particle_radius(sim.sim, sim.nn, mu, sigma, n)

def sample_psf(psf, sigma=6):
    #psf -= sigma*(2*np.random.rand(*psf.shape)-1)
    return (sigma + sigma*(2*np.random.rand(*psf.shape)-1)).astype('float32')
    #print psf

sigma = 0.05

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

NNG = 32
NNZ = 16
CUT = NNZ/2
gfield = fields.createField(np.array([NNG,NNG,NNZ], dtype='int32'))
fields.setupFFT(gfield)

def gen_image(ss, params, donoise=False):
    t = np.zeros((NNZ,NNG,NNG), dtype='float32').flatten()

    fields.fieldSet(gfield, t)
    fields.process_image(gfield, ss.sim, params, fields.PSF_ISOTROPIC_DISC)

    fields.fieldGet(gfield, t)
    t = t.reshape(NNZ,NNG,NNG)
    t -= t.min()
    t /= t.max()
    tslice = np.s_[:]
    #tslice = np.s_[CUT,:,:]
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
    psftrue = np.array([1.2, 10.], dtype='float32')
    simtrue = generate_configuration()
    itrue,ntrue = gen_image(simtrue, psftrue, True)
    xtrue = simtrue.get_pos()
    rtrue = simtrue.get_radii()

    sim = copy.deepcopy(simtrue)
    perturb_radii(sim, mu=5.00, sigma=0.0)
    sim.do_relaxation(1000)

    sim.set_param_hs()
    sim.do_steps(250)
    sim.set_param_mc()

    psf = np.array([4, 4], dtype='float32')
    istart = gen_image(sim, psf)
    xstart = sim.get_pos()
    rstart = sim.get_radii()

    nwarm = int(2e4)
    nsteps = nwarm + int(1e3)

    rguess = 0*rtrue
    pguess = 0*psf
    guess, std, total = 0*xtrue, 0*xtrue, 0
    positions, crosses = [], []
    lnew = lold = loglikelihood(istart, itrue)
    accepts = 0
    likes = []

    print "goal:", loglikelihood(ntrue, 0*ntrue)
    r = np.sqrt(((sim.get_pos()- xtrue)**2).sum(-1))
    print r.mean()

    for i in xrange(nsteps):
        vsig = 10.0000
        simcopy = copy.deepcopy(sim)
        psfcopy = psf[:]
        nbody.init_set_random_velocities(sim.sim, 0, vsig)
        startv = sim.get_vel()

        if i % 3 == 0:
            sample_hamiltonian(sim, 20)
        elif i % 3 == 1:
            sample_radii(sim, mu=5.0, sigma=0.20, n=1)
        elif i % 3 == 2:
            psf = sample_psf(psf, 6)

        t = sim.get_pos()
        r = sim.get_radii()
        im = gen_image(sim, psf)
        lnew = loglikelihood(im, itrue)

        endv = sim.get_vel()
        vfact1 = np.exp(-(startv**2).sum(axis=-1).mean()/(2*(vsig**2)))
        vfact2 = np.exp(-(endv**2).sum(axis=-1).mean()/(2*(vsig**2)))

        acceptance = np.exp(lnew-lold)
        acceptance *= (vfact1/vfact2)

        if i % 100 == 1:
            print i, 'ratio', lnew, lold, acceptance, total, float(accepts)/i

        if np.random.rand() < min(acceptance, 1):
            lold = lnew
            accepts += 1
            likes.append(-lnew)
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

    r = np.sqrt(((guess - xtrue)**2)[:,:2].sum(-1))
    print r.mean(), r.std()#, std
    plot_compare(itrue, istart, iguess, itrue-iguess-ntrue)
