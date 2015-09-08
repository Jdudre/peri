import numpy as np
from cbamf.util import Tile, cdd, amin, amax

class SphereCollectionRealSpace(object):
    def __init__(self, pos, rad, shape, support_size=4, typ=None, pad=None):
        self.support_size = support_size
        self.pos = pos.astype('float')
        self.rad = rad.astype('float')
        self.N = rad.shape[0]

        if typ is None:
            self.typ = np.ones(self.N)
            if pad is not None and pad <= self.N:
                self.typ[-pad:] = 0
        else:
            self.typ = typ.astype('float')

        self.shape = shape
        self._setup()

    def _setup(self):
        z,y,x = Tile(self.shape).coords()
        self.rvecs = np.rollaxis(np.array(np.broadcast_arrays(z,y,x)), 0, 4)
        self.particles = np.zeros(self.shape)
        self._diff_field = np.zeros(self.shape)

    def _particle(self, pos, rad, zscale, sign=1, dodiff=False):
        p = np.round(pos)
        r = np.round(np.array([1.0/zscale,1,1])*np.ceil(rad)+self.support_size)

        tile = Tile(p-r, p+r, 0, self.shape)
        subr = self.rvecs[tile.slicer + (np.s_[:],)]
        rvec = (subr - pos)

        # apply the zscale and find the distances to make a ellipsoid
        # note: the appearance of PI in the last line is because of leastsq
        # fits to the correct Fourier version of the sphere, j_{3/2} / r^{3/2}
        # happened to fit right at pi -- what?!
        rvec[...,0] *= zscale
        rdist = np.sqrt((rvec**2).sum(axis=-1))

        t = sign/(1.0 + np.exp(5.0*(rdist - rad)))
        self.particles[tile.slicer] += t

        if dodiff:
            self._diff_field[tile.slicer] += t

    def _update_particle(self, n, p, r, t, zscale, dodiff=True):
        if self.typ[n] == 1:
            self._particle(self.pos[n], self.rad[n], zscale, -1, dodiff=dodiff)

        self.pos[n] = p
        self.rad[n] = r
        self.typ[n] = t

        if self.typ[n] == 1:
            self._particle(self.pos[n], self.rad[n], zscale, +1, dodiff=dodiff)

    def initialize(self, zscale):
        if len(self.pos.shape) != 2:
            raise AttributeError("Position array needs to be (-1,3) shaped, (z,y,x) order")

        self.particles = np.zeros(self.shape)
        for p0, r0, t0 in zip(self.pos, self.rad, self.typ):
            if t0 == 1:
                self._particle(p0, r0, zscale)

    def set_tile(self, tile):
        self.tile = tile

    def update(self, ns, pos, rad, typ, zscale, difference=True):
        for n, p, r, t in zip(ns, pos, rad, typ):
            self._update_particle(n, p, r, t, zscale, dodiff=difference)

    def get_field(self):
        return self.particles[self.tile.slicer]

    def get_diff_field(self):
        c = self._diff_field[self.tile.slicer].copy()
        self._diff_field[self.tile.slicer] *= 0
        return c

    def get_support_size(self, p0, r0, t0, p1, r1, t1, zscale):
        rsc = self.support_size

        zsc = np.array([1.0/zscale, 1, 1])
        r0, r1 = zsc*r0, zsc*r1

        off0 = r0 + rsc
        off1 = r1 + rsc

        if t0[0] == 1 and t1[0] == 1:
            pl = amin(p0-off0-1, p1-off1-1)
            pr = amax(p0+off0+1, p1+off1+1)
        if t0[0] != 1 and t1[0] == 1:
            pl = (p1-off1-1)
            pr = (p1+off1+1)
        if t0[0] == 1 and t1[0] != 1:
            pl = (p0-off0-1)
            pr = (p0+off0+1)
        if t0[0] != 1 and t1[0] != 1:
            c = np.array(self.shape)
            pl = c/2 - c/8
            pr = c/2 + c/8

        if len(pl.shape) > 1:
            pl = pl[0]
            pr = pr[0]
        return pl, pr

    def get_params(self):
        return np.hstack([self.pos.ravel(), self.rad])

    def get_params_pos(self):
        return self.pos.ravel()

    def get_params_rad(self):
        return self.rad

    def get_params_typ(self):
        return self.typ

    def __getstate__(self):
        odict = self.__dict__.copy()
        cdd(odict, ['rvecs', 'particles', '_diff_field'])
        return odict

    def __setstate__(self, idict):
        self.__dict__.update(idict)
        self._setup()


class Slab(object):
    def __init__(self, pos, shape, normal=(1,0,0), support_size=4, typ=None, pad=None):
        self.support_size = support_size

        self.pos = np.array(pos).astype('float')
        self.normal = np.array(normal).astype('float')
        self.normal /= np.sqrt(self.normal.dot(self.normal))

        self.shape = shape
        self._setup()

    def _setup(self):
        z,y,x = Tile(self.shape).coords()
        self.rvecs = np.rollaxis(np.array(np.broadcast_arrays(z,y,x)), 0, 4)
        self.image = np.zeros(self.shape)

    def _slab(self, pos, norm, sign=1):
        p = (self.rvecs - pos).dot(norm)
        t = sign/(1.0 + np.exp(np.pi*p))
        self.image += t

    def initialize(self):
        self.image = np.zeros(self.shape)
        self._slab(self.pos, self.normal)

    def set_tile(self, tile):
        self.tile = tile

    def update(self, pos, norm):
        self._slab(self.pos, self.normal, -1)
        self.pos = pos
        self.normal = norm / np.sqrt(norm.dot(norm))
        self._slab(self.pos, self.normal, +1)

    def get_field(self):
        return self.image[self.tile.slicer]

    def get_support_size(self, p=None):
        return pl, pr

    def get_params(self):
        return np.hstack([self.pos.ravel(), self.normal.ravel()])

    def __getstate__(self):
        odict = self.__dict__.copy()
        cdd(odict, ['rvecs', 'image'])
        return odict

    def __setstate__(self, idict):
        self.__dict__.update(idict)
        self._setup()
