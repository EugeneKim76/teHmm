#!/usr/bin/env python

#Copyright (C) 2013 by Glenn Hickey
#
# Class derived from _BaseHMM and MultinomialHMM from sklearn/tests/hmm.py
# (2010 - 2013, scikit-learn developers (BSD License))
#
#Released under the MIT license, see LICENSE.txt
#!/usr/bin/env python

import os
import sys
import numpy as np
import pickle
import string
import copy
import logging
from collections import Iterable
from numpy.testing import assert_array_equal, assert_array_almost_equal

from .emission import IndependentMultinomialEmissionModel
from .track import TrackList, TrackTable, Track
from .common import EPSILON, myLog
from sklearn.hmm import _BaseHMM
from sklearn.hmm import MultinomialHMM
from sklearn.hmm import _hmmc
from sklearn.hmm import NEGINF
from sklearn.utils import check_random_state, deprecated 


"""
This class is based on the MultinomialHMM from sckikit-learn, but we make
the emission model a parameter. The custom emission model we support at this
point is a multi-*dimensional* multinomial. 
"""
class MultitrackHmm(_BaseHMM):
    def __init__(self, emissionModel=None,
                 startprob=None,
                 transmat=None, startprob_prior=None, transmat_prior=None,
                 algorithm="viterbi", random_state=None,
                 n_iter=10, thresh=1e-2, params=string.ascii_letters,
                 init_params=string.ascii_letters,
                 state_name_map=None,
                 fudge=0.0,
                 fixTrans=False,
                 fixEmission=False):
        if emissionModel is not None:
            n_components = emissionModel.getNumStates()
        else:
            n_components = 1

        """Create a hidden Markov model that supports multiple tracks.
        emissionModel must have already been created"""
        _BaseHMM.__init__(self, n_components=n_components,
                          startprob=startprob,
                          transmat=transmat,
                          startprob_prior=startprob_prior,
                          transmat_prior=transmat_prior,
                          algorithm=algorithm,
                          random_state=random_state,
                          n_iter=n_iter,
                          thresh=thresh,
                          params=params,
                          init_params=init_params)
        # remember init_params
        self.init_params = init_params
        #: emission model is specified as parameter here
        self.emissionModel = emissionModel
        #: a TrackList object specifying information about the tracks
        self.trackList = None
        #: a map between state values and names (track.CategoryMap)
        self.stateNameMap = state_name_map
        # little constant that gets added to frequencies during training
        # to prevent zero probabilities.  The bigger it is, the flatter
        # the distribution... (note that emission class has its own)
        self.fudge = fudge
        # freeze input transmat
        self.fixTrans = fixTrans
        # freeze input EmissionModel
        self.fixEmission = fixEmission
        # keep track of number of EM iterations performed
        self.current_iteration = None

    def train(self, trackData):
        """ Use EM to estimate best parameters from scratch (unsupervised)"""
        self.trackList = trackData.getTrackList()
        self.fit(trackData.getTrackTableList())
        self.validate()

    def supervisedTrain(self, trackData, bedIntervals):
        """ Train directly from set of known states (4th column in the
        bedIntervals provided.  We assume that the most likely parameters
        are also just the expected values, which works for our basic
        multinomial distribution. Note that the states should already
        have been mapped to integers"""
        # NOTE bedIntervals must be sorted!
        self.trackList = trackData.getTrackList()
        N = self.emissionModel.getNumStates()
        transitionCount = self.fudge + np.zeros((N,N), np.float)
        freqCount = self.fudge + np.zeros((N,), np.float)
        prevInterval = None
        logging.debug("beginning supervised transition stats")
        for interval in bedIntervals:
            state = int(interval[3])
            assert state < N
            transitionCount[state,state] += interval[2] - interval[1] - 1
            freqCount[state] += interval[2] - interval[1]
            if prevInterval is not None and prevInterval[0] == interval[0]:
                if interval[1] < prevInterval[2]:
                    raise RuntimeError(
                        "Overlapping or out of order training intervals"
                        " detected: %s and %s."
                        (prevInterval, interval))
                elif interval[1] == prevInterval[2]:
                    transitionCount[prevInterval[3], state] += 1
            prevInterval = interval
        for row in xrange(len(transitionCount)):
            transitionCount[row] /= np.sum(transitionCount[row])
        self.transmat_ = np.copy(transitionCount)
        # scikit learn is too chicken to have 0-probs.  so we go back and
        # hack them in if necessary
        self._log_transmat = myLog(transitionCount)
        freqCount /= np.sum(freqCount)
        self.startprob_ = freqCount
        self.emissionModel.supervisedTrain(trackData, bedIntervals)
        self.validate()
        

    def logProb(self, trackData):
        """ Return the log probability of the data (one score for each
        interval"""
        logProbList = []
        for trackTable in trackData.getTrackTableList():
            totalLogProb.append(self.score(trackTable))
        return logProbList

    def viterbi(self, trackData, numThreads = 1):
        """ Return the output of the Viterbi algorithm on the loaded
        data: a tuple of (log likelihood of best path, and the path itself)
        (one data point of each interval of track data)
        """
        # Thread interface provided but not implemented:
        assert numThreads == 1
        output = []
        for trackTable in trackData.getTrackTableList():
            prob, states = self.decode(trackTable)
            if self.stateNameMap is not None:
                states = map(self.stateNameMap.getMapBack, states)
            output.append((prob,states))
        return output
        
    def __str__(self):
        states = [x for x in xrange(self.n_components)]
        if self.stateNameMap is not None:
            states = map(self.stateNameMap.getMapBack, states)
        s = "\nNumStates = %d:\n%s\n" % (self.n_components, str(states))
        sp = [(states[i], self.startprob_[i])
              for i in xrange(self.n_components)] 
        s += "\nStart probs =\n%s\n" % str(sp)
        s += "\nTransitions =\n%s\n" % str(self.transmat_)
        s += "\nlogTransitions = \n%s\n" % str(myLog(self.transmat_))
        em = self.emissionModel         
        s += "\nNumber of symbols per track=\n%s\n" % str(
            em.getNumSymbolsPerTrack())
        s += "\nEmissions =\n"
        emProbs = em.getLogProbs()
        for state, stateName in enumerate(states):
            s += "State %s:\n" % stateName
            for trackNo in xrange(em.getNumTracks()):
                track = self.trackList.getTrackByNumber(trackNo)
                s += "  Track %d %s (%s):\n" % (track.getNumber(),
                                                track.getName(),
                                                track.getDist())
                numSymbolsPerTrack =  em.getNumSymbolsPerTrack()
                for idx, symbol in enumerate(em.getTrackSymbols(trackNo)):
                    symbolName = track.getValueMap().getMapBack(symbol)
                    prob = np.exp(emProbs[trackNo][state][symbol])
                    if idx <= 2 or prob > 0.005:
                        logval = str(myLog(prob))
                        if prob == 0.0:
                            logval = "-inf"
                        s += "    %s) %s: %f (log=%s)\n" % (symbol, symbolName,
                                                            prob, logval)
        return s

    def getTrackList(self):
        return self.trackList

    def getStartProbs(self):
        return self.startprob_

    def getTransitionProbs(self):
        return self.transmat_

    def getStateNameMap(self):
        return self.stateNameMap

    def getEmissionModel(self):
        return self.emissionModel

    def validate(self):
        assert len(self.startprob_) == self.emissionModel.getNumStates()
        assert not isinstance(self.startprob_[0], Iterable)
        assert len(self.transmat_) == self.emissionModel.getNumStates()
        assert len(self.transmat_[0]) == self.emissionModel.getNumStates()
        assert_array_almost_equal(np.sum(self.startprob_), 1.)
        for i in xrange(self.emissionModel.getNumStates()):
            assert_array_almost_equal(np.sum(self.transmat_[i]), 1.)
        self.emissionModel.validate()
        
    ###########################################################################
    #       SCIKIT LEARN BASEHMM OVERRIDES BELOW 
    ###########################################################################

    def _compute_log_likelihood(self, obs):
        return self.emissionModel.allLogProbs(obs)

    def _generate_sample_from_state(self, state, random_state=None):
        return self.emissionModel.sample(state)

    def _init(self, obs, params='ste'):
        self.params = params
        if self.fixTrans is True:
            self.params = self.params.replace("t", "")
        if self.fixEmission is True:
            self.params = self.params.replace("e", "")
        super(MultitrackHmm, self)._init(obs, params=params)
        self.random_state = check_random_state(self.random_state)
        randomize = 'e' in params
        self.emissionModel.initParams(randomize=randomize)

    def _initialize_sufficient_statistics(self):
        stats = super(MultitrackHmm, self)._initialize_sufficient_statistics()
        stats['obs'] = self.emissionModel.initStats()
        return stats
    
    def _accumulate_sufficient_statistics(self, stats, obs, framelogprob,
                                          posteriors, fwdlattice, bwdlattice,
                                          params):
        logging.debug("%d: beginning MultitrackHMM E-step" %
                      self.current_iteration)
        super(MultitrackHmm, self)._accumulate_sufficient_statistics(
            stats, obs, framelogprob, posteriors, fwdlattice, bwdlattice,
            params)
        if 'e' in params:
            logging.debug("beginning Emissions E-substep")
            self.emissionModel.accumulateStats(obs, stats['obs'], posteriors)

        logging.debug("ending MultitrackHMM E-step")

    def _do_mstep(self, stats, params):
        logging.debug("%d: beginning MultitrackHMM M-step" %
                      self.current_iteration)
        super(MultitrackHmm, self)._do_mstep(stats, params)
        if 'e' in params:
            self.emissionModel.maximize(stats['obs'])
        logging.debug("%d: ending MultitrackHMM M-step" %
                      self.current_iteration)
        self.current_iteration += 1

    def fit(self, obs, **kwargs):
        self.current_iteration = 1
        return _BaseHMM.fit(self, obs, **kwargs)

    # Getting annoyed with epsilons being added by scikit learn
    # so redo tranmat property to allow zeros (should probably do
    # for start probs as well at some point)
    def _get_transmat(self):
        """Matrix of transition probabilities."""
        return np.exp(self._log_transmat)

    def _set_transmat(self, transmat):
        if transmat is None:
            transmat = np.tile(1.0 / self.n_components,
                               (self.n_components, self.n_components))

        if (np.asarray(transmat).shape
                != (self.n_components, self.n_components)):
            raise ValueError('transmat must have shape '
                             '(n_components, n_components)')
        if not np.all(np.allclose(np.sum(transmat, axis=1), 1.0)):
            raise ValueError('Rows of transmat must sum to 1.0')

        self._log_transmat = myLog(np.asarray(transmat).copy())

    transmat_ = property(_get_transmat, _set_transmat)
