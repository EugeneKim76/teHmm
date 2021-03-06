from libc.math cimport exp, log
import numpy as np
cimport numpy as np
cimport cython
from .track import TrackTable
np.import_array()

ctypedef np.float64_t dtype_t
ctypedef np.int32_t itype_t

cdef dtype_t _NINF = -np.inf
cdef dtype_t _MINDBL = -1e20

def canFast(obs):
    return isinstance(obs, TrackTable) or (
        isinstance(obs, np.ndarray) and (obs.dtype == np.int32 or
                                         obs.dtype == np.uint16 or
                                         obs.dtype == np.uint8))
        
@cython.boundscheck(False)
def fastAllLogProbs(obs, logProbs, outProbs, normalize, segRatios):
    if isinstance(obs, TrackTable):
        obs = obs.getNumPyArray()
    assert isinstance(obs, np.ndarray)
    assert isinstance(logProbs, np.ndarray)
    assert isinstance(outProbs, np.ndarray)
    assert len(obs.shape) == 2
    assert len(logProbs.shape) == 3
    assert logProbs.dtype == np.float
    assert outProbs.dtype == np.float
    assert outProbs.shape[0] == obs.shape[0]
    assert logProbs.shape[0] == obs.shape[1]
    cdef itype_t nObs = obs.shape[0]
    cdef itype_t nTracks = obs.shape[1]
    cdef itype_t nStates = logProbs.shape[1]

    if obs.dtype == np.int32:
        _fastAllLogProbs32(nObs, nTracks, nStates, obs, logProbs, outProbs,
                           normalize, segRatios)
    elif obs.dtype == np.uint16:
        _fastAllLogProbsU16(nObs, nTracks, nStates, obs, logProbs, outProbs,
                            normalize, segRatios)
    elif obs.dtype == np.uint8:
        _fastAllLogProbsU8(nObs, nTracks, nStates, obs, logProbs, outProbs,
                           normalize, segRatios)
    else:
        print obs.dtype
        assert False

@cython.boundscheck(False)
def _fastAllLogProbsU8(itype_t nObs, itype_t nTracks, itype_t nStates,
                      np.ndarray[np.uint8_t, ndim=2] obs,
                      np.ndarray[dtype_t, ndim=3] logProbs,
                      np.ndarray[dtype_t, ndim=2] outProbs,
                      dtype_t normalize,
                      np.ndarray[dtype_t, ndim=1] segRatios):
    cdef itype_t i, j, k
    cdef dtype_t minDbl = _MINDBL
    cdef dtype_t maxProb = _MINDBL
    cdef itype_t hasRatio = 0
    if segRatios is not None:
        hasRatio = 1
        
    with nogil:
        for i in xrange(nObs):
           for j in xrange(nStates):
               outProbs[i,j] = 0.0
               for k in xrange(nTracks):
                   outProbs[i, j] += logProbs[k, j, obs[i, k]]
               outProbs[i, j] *= normalize
               if hasRatio == 1:
                   outProbs[i, j] *= segRatios[i]           
               if outProbs[i, j] > maxProb:
                   maxProb = outProbs[i, j]
           # no state that can emit symbol so we give every state 0
           # NOTE: should print a warning message since this implies
           # that data impossible with model.
           if maxProb == minDbl:
               for j in xrange(nStates):
                   outProbs[i, j] = 0.0
       
@cython.boundscheck(False)
def _fastAllLogProbsU16(itype_t nObs, itype_t nTracks, itype_t nStates,
                        np.ndarray[np.uint16_t, ndim=2] obs,
                        np.ndarray[dtype_t, ndim=3] logProbs,
                        np.ndarray[dtype_t, ndim=2] outProbs,
                        dtype_t normalize,
                        np.ndarray[dtype_t, ndim=1] segRatios):
    cdef itype_t i, j, k
    cdef dtype_t minDbl = _MINDBL
    cdef dtype_t maxProb = _MINDBL
    cdef itype_t hasRatio = 0
    if segRatios is not None:
        hasRatio = 1
        
    with nogil:
        for i in xrange(nObs):
           for j in xrange(nStates):
               outProbs[i,j] = 0.0
               for k in xrange(nTracks):
                   outProbs[i, j] += logProbs[k, j, obs[i, k]]
               outProbs[i, j] *= normalize
               if hasRatio == 1:
                   outProbs[i, j] *= segRatios[i]           
               if outProbs[i, j] > maxProb:
                   maxProb = outProbs[i, j]
           # no state that can emit symbol so we give every state 0
           # NOTE: should print a warning message since this implies
           # that data impossible with model.
           if maxProb == minDbl:
               for j in xrange(nStates):
                   outProbs[i, j] = 0.0

@cython.boundscheck(False)
def _fastAllLogProbs32(itype_t nObs, itype_t nTracks, itype_t nStates,
                      np.ndarray[np.int32_t, ndim=2] obs,
                      np.ndarray[dtype_t, ndim=3] logProbs,
                      np.ndarray[dtype_t, ndim=2] outProbs,
                      dtype_t normalize,
                      np.ndarray[dtype_t, ndim=1] segRatios):                      
    cdef itype_t i, j, k
    cdef dtype_t minDbl = _MINDBL
    cdef dtype_t maxProb = _MINDBL
    cdef itype_t hasRatio = 0
    if segRatios is not None:
        hasRatio = 1
        
    with nogil:
        for i in xrange(nObs):
           for j in xrange(nStates):
               outProbs[i,j] = 0.0
               for k in xrange(nTracks):
                   outProbs[i, j] += logProbs[k, j, obs[i, k]]
               outProbs[i, j] *= normalize
               if hasRatio == 1:
                   outProbs[i, j] *= segRatios[i]           
               if outProbs[i, j] > maxProb:
                   maxProb = outProbs[i, j]
           # no state that can emit symbol so we give every state 0
           # NOTE: should print a warning message since this implies
           # that data impossible with model.
           if maxProb == minDbl:
               for j in xrange(nStates):
                   outProbs[i, j] = 0.0

@cython.boundscheck(False)
def fastAccumulateStats(obs, obsStats, posteriors, segRatios):
    if isinstance(obs, TrackTable):
        obs = obs.getNumPyArray()
    assert isinstance(obs, np.ndarray)

    assert len(obs.shape) == 2

    cdef itype_t nObs = obs.shape[0]
    cdef itype_t nTracks = obs.shape[1]
    cdef itype_t nStates = obsStats[0].shape[0]

    if obs.dtype == np.int32:
        _fastAccumulateStats32(nObs, nTracks, nStates, obs, obsStats,
                               posteriors, segRatios)
    elif obs.dtype == np.uint16:
        _fastAccumulateStatsU16(nObs, nTracks, nStates, obs, obsStats,
                               posteriors, segRatios)
    elif obs.dtype == np.uint8:
        _fastAccumulateStatsU8(nObs, nTracks, nStates, obs, obsStats,
                               posteriors, segRatios)
    else:
        assert False

@cython.boundscheck(False)
def _fastAccumulateStatsU8(itype_t nObs, itype_t nTracks, itype_t nStates,
                           np.ndarray[np.uint8_t, ndim=2] obs, 
                           np.ndarray[dtype_t, ndim=3] obsStats,
                           np.ndarray[dtype_t, ndim=2] posteriors,
                           np.ndarray[dtype_t, ndim=1] segRatios):
    cdef itype_t i, track, state, obsVal
    cdef dtype_t segProb
    cdef itype_t hasRatio = 0
    if segRatios is not None:
        hasRatio = 1

    with nogil:
        for i in xrange(nObs):
            for track in xrange(nTracks):
                obsVal = obs[i,track]
                for state in xrange(nStates):
                    segProb = posteriors[i, state]
                    if hasRatio == 1:
                        segProb *= segRatios[i]
                    obsStats[track, state, obsVal] += segProb

@cython.boundscheck(False)
def _fastAccumulateStatsU16(itype_t nObs, itype_t nTracks, itype_t nStates,
                           np.ndarray[np.uint16_t, ndim=2] obs, 
                           np.ndarray[dtype_t, ndim=3] obsStats,
                           np.ndarray[dtype_t, ndim=2] posteriors,
                           np.ndarray[dtype_t, ndim=1] segRatios):
    cdef itype_t i, track, state, obsVal
    cdef dtype_t segProb
    cdef itype_t hasRatio = 0
    if segRatios is not None:
        hasRatio = 1

    with nogil:
        for i in xrange(nObs):
            for track in xrange(nTracks):
                obsVal = obs[i,track]
                for state in xrange(nStates):
                    segProb = posteriors[i, state]
                    if hasRatio == 1:
                        segProb *= segRatios[i]
                    obsStats[track, state, obsVal] += segProb

@cython.boundscheck(False)
def _fastAccumulateStats32(itype_t nObs, itype_t nTracks, itype_t nStates,
                            np.ndarray[np.int32_t, ndim=2] obs, 
                            np.ndarray[dtype_t, ndim=3] obsStats,
                            np.ndarray[dtype_t, ndim=2] posteriors,
                            np.ndarray[dtype_t, ndim=1] segRatios):                            
    cdef itype_t i, track, state, obsVal
    cdef dtype_t segProb
    cdef itype_t hasRatio = 0
    if segRatios is not None:
        hasRatio = 1

    with nogil:
        for i in xrange(nObs):
            for track in xrange(nTracks):
                obsVal = obs[i,track]
                for state in xrange(nStates):
                    segProb = posteriors[i, state]
                    if hasRatio == 1:
                        segProb *= segRatios[i]
                    obsStats[track, state, obsVal] += segProb

@cython.boundscheck(False)
def fastUpdateCounts(bedInterval, trackTable, obsStats, segRatios):
    assert isinstance(trackTable, TrackTable)
    
    obs = trackTable.getNumPyArray()

    assert isinstance(obs, np.ndarray)
    assert len(obs.shape) == 2
    
    cdef itype_t tableStart = trackTable.getStart()
    cdef itype_t start = bedInterval[1]
    cdef itype_t end = bedInterval[2]
    cdef itype_t symbol = bedInterval[3]
    cdef itype_t nObs = obs.shape[0]
    cdef itype_t nTracks = obs.shape[1]
    cdef itype_t nStates = obsStats[0].shape[0]

    if obs.dtype == np.int32:
        _fastUpdateCounts32(nObs, nTracks, nStates, start, end, symbol,
                            tableStart, obs, obsStats, segRatios)
    elif obs.dtype == np.uint16:
        _fastUpdateCountsU16(nObs, nTracks, nStates, start, end, symbol,
                             tableStart, obs, obsStats, segRatios)
    elif obs.dtype == np.uint8:
        _fastUpdateCountsU8(nObs, nTracks, nStates, start, end, symbol,
                            tableStart, obs, obsStats, segRatios)
    else:
        assert False

@cython.boundscheck(False)
def _fastUpdateCounts32(itype_t nObs, itype_t nTracks, itype_t nStates,
                        itype_t start, itype_t end, itype_t symbol,
                        itype_t tableStart, 
                        np.ndarray[np.int32_t, ndim=2] obs,
                        np.ndarray[dtype_t, ndim=3] obsStats,
                        np.ndarray[dtype_t, ndim=1] segRatios):
    cdef itype_t pos, tablePos, track
    cdef dtype_t val
    cdef itype_t hasRatio = 0    
    if segRatios is not None:
        hasRatio = 1
        
    with nogil:
        for pos in xrange(start, end):
            # note that pos must be in table-relative coordinates
            # (ie as from getOverlapinTableCoords())
            val = 1.0
            if hasRatio == 1:
                val = segRatios[pos]
            for track in xrange(nTracks):
                obsStats[track, symbol, obs[pos, track]] += val

@cython.boundscheck(False)
def _fastUpdateCountsU16(itype_t nObs, itype_t nTracks, itype_t nStates,
                        itype_t start, itype_t end, itype_t symbol,
                        itype_t tableStart, 
                        np.ndarray[np.uint16_t, ndim=2] obs,
                        np.ndarray[dtype_t, ndim=3] obsStats,
                        np.ndarray[dtype_t, ndim=1] segRatios):
    cdef itype_t pos, tablePos, track
    cdef dtype_t val
    cdef itype_t hasRatio = 0    
    if segRatios is not None:
        hasRatio = 1
        
    with nogil:
        for pos in xrange(start, end):
            # note that pos must be in table-relative coordinates
            # (ie as from getOverlapinTableCoords())
            val = 1.0
            if hasRatio == 1:
                val = segRatios[pos]
            for track in xrange(nTracks):
                obsStats[track, symbol, obs[pos, track]] += val

@cython.boundscheck(False)
def _fastUpdateCountsU8(itype_t nObs, itype_t nTracks, itype_t nStates,
                        itype_t start, itype_t end, itype_t symbol,
                        itype_t tableStart, 
                        np.ndarray[np.uint8_t, ndim=2] obs,
                        np.ndarray[dtype_t, ndim=3] obsStats,
                        np.ndarray[dtype_t, ndim=1] segRatios):
    cdef itype_t pos, tablePos, track
    cdef dtype_t val
    cdef itype_t hasRatio = 0    
    if segRatios is not None:
        hasRatio = 1
        
    with nogil:
        for pos in xrange(start, end):
            # note that pos must be in table-relative coordinates
            # (ie as from getOverlapinTableCoords())
            val = 1.0
            if hasRatio == 1:
                val = segRatios[pos]
            for track in xrange(nTracks):
                obsStats[track, symbol, obs[pos, track]] += val
