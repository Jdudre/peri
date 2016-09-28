"""
The FFT module is an abstraction that switches between numpy.fft and pyfftw.
If pyfftw is present than it uses the pyfftw.interfaces to build a fast
interface for fftw with wisdom storage. Since the interfaces are the same for
numpy and pyfftw, that identical interface is passed on through the
peri.fft.fft object.

*IMPORTANT* The one caveat is that every function call to peri.fft.fft.* must
unpack extra arguments:

    peri.fft.fft.ifftn(..., **peri.fft.fftkwargs)

"""
import atexit
import pickle
import numpy as np

from multiprocessing import cpu_count

from peri import conf
from peri.util import Tile
from peri.logger import log
log = log.getChild('fft')

try:
    import pyfftw
    hasfftw = True
except ImportError as e:
    log.warning(
        'FFTW not found, which can improve speed by 20x. '
        'Try `pip install pyfftw`.'
    )
    hasfftw = False
    
FFTW_PLAN_FAST = 'FFTW_ESTIMATE'
FFTW_PLAN_NORMAL = 'FFTW_MEASURE'
FFTW_PLAN_SLOW = 'FFTW_PATIENT'

def load_wisdom(wisdomfile):
    if wisdomfile is None:
        return

    try:
        pyfftw.import_wisdom(pickle.load(open(wisdomfile)))
    except IOError as e:
        log.warn("No wisdom present, generating some at %r" % wisdomfile)
        save_wisdom(wisdomfile)

def save_wisdom(wisdomfile):
    if wisdomfile is None:
        return

    if wisdomfile:
        pickle.dump(
            pyfftw.export_wisdom(), open(wisdomfile, 'wb'),
            protocol=-1
        )

if hasfftw:
    _var = conf.load_conf()
    effort = _var['fftw-planning-effort']
    threads = _var['fftw-threads']
    threads = threads if threads > 0 else cpu_count()

    # these variables must be passed to every fft.* function
    fftkwargs = {
        'planner_effort': effort,
        'threads': threads,
        'overwrite_input': False,
        'auto_align_input': True,
        'auto_contiguous': True
    }

    # allow the interface to store memory aligned arrays temporarily for
    # speed of allocation, default now is 30 seconds.
    pyfftw.interfaces.cache.enable()
    pyfftw.interfaces.cache.set_keepalive_time(30)

    # setup the exposed interface and load the wisdom
    fft = pyfftw.interfaces.numpy_fft
    load_wisdom(conf.get_wisdom())

    @atexit.register
    def goodbye():
        save_wisdom(conf.get_wisdom())
else:
    fftkwargs = {}
    fft = np.fft
