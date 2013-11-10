#!/usr/bin/env python

#Copyright (C) 2013 by Glenn Hickey
#
#Released under the MIT license, see LICENSE.txt
#!/usr/bin/env python

import os
import sys
import numpy as np
import pickle
import string
import copy

from sklearn.hmm import _BaseHMM
from sklearn.hmm import MultinomialHMM
from sklearn.hmm import GaussianHMM
from sklearn.utils import check_random_state, deprecated
from sklearn.utils.extmath import logsumexp
from sklearn.base import BaseEstimator
from sklearn.hmm import cluster
from sklearn.hmm import _hmmc
from sklearn.hmm import normalize
from sklearn.hmm import NEGINF

""" Generlization of the sckit-learn multinomial to k dimensions.  Ie that the
observations are k-dimensional vectors -- one element for each track.
The probability of an observation in this model is the product of probabilities
for each track because we make the simplifying assumption that the tracks are
independent """
class IndependentMultinomialEmissionModel(object):
    def __init__(self, numStates, numSymbolsPerTrack, params = None):
        self.numStates = numStates
        self.numTracks = len(numSymbolsPerTrack)
        self.numSymbolsPerTrack = numSymbolsPerTrack
        # [TRACK, STATE, SYMBOL]
        self.probs = None
        self.logProbs = None
        self.initParams(params)

    def getLogProbs(self):
        return self.logProbs

    def getNumStates(self):
        return self.numStates

    def getNumTracks(self):
        return self.getNumTracks
    
    def initParams(self, params = None):
        """ initalize emission parameters such that all values are
        equally probable for each category.  if params is specifed, then
        assume it is the emission probability matrix and set our log probs
        to the log of it."""
        self.logProbs = []
        self.probs = []
        #todo: numpyify

        for i in xrange(self.numTracks):
            stateList = []
            logStateList = []
            for j in xrange(self.numStates):
                if params is None:
                    dist = normalize(1. + np.zeros(
                        self.numSymbolsPerTrack[i], dtype=np.float))
                else:
                    dist = np.array(params[i][j], dtype=np.float)
                stateList.append(dist)
                logStateList.append(np.log(dist))
            self.probs.append(stateList)
            self.logProbs.append(logStateList)
            
        assert len(self.logProbs) == self.numTracks
        for i in xrange(self.numTracks):
            assert len(self.logProbs[i]) == self.numStates
            for j in xrange(self.numStates):
                assert len(self.logProbs[i][j]) == self.numSymbolsPerTrack[i]
                assert np.array_equal(self.logProbs[i][j],
                                      np.log(self.probs[i][j]))

    def singleLogProb(self, state, singleObs):
        """ Compute the log probability of a single observation, obs given
        a state."""
        assert state < self.numStates
        logProb = 0.
        for track in xrange(self.numTracks):
            obsSymbol = singleObs[track]
            assert obsSymbol < self.numSymbolsPerTrack[track]
            # independence assumption means we can just add the tracks
            logProb += self.logProbs[track][state][obsSymbol]
        return logProb

    def allLogProbs(self, obs):
        """ obs is an array of observation vectors.  return an array of log
        probabilities.  this output array contains the probabilitiy for
        each state for each observation"""
        allLogProbs = np.zeros((obs.shape[0], self.numStates), dtype=np.float)
        for i in xrange(len(obs)):
            for state in xrange(self.numStates):
                allLogProbs[i, state] = self.singleLogProb(state, obs[i])
        return allLogProbs
    
    def sample(self, state):
        return None
        ##TODO adapt below code for multidimensional input
        cdf = np.cumsum(self.emissionprob_[state, :])
        random_state = check_random_state(random_state)
        rand = random_state.rand()
        symbol = (cdf > rand).argmax()
        return symbol

    def initStats(self):
        """ Initialize an array to hold the accumulation statistics
        looks something like obsStats[TRAC][STATE][SYMBOL] = total probability
        of that STATE/SYMBOL pair across all observations """
        obsStats = []
        for track in xrange(self.numTracks):
            obsStats.append(np.zeros((self.numStates,
                                      self.numSymbolsPerTrack[track]),
                                     dtype=np.float))
        return obsStats

    def accumulateStats(self, obs, obsStats, posteriors):
        """ For each observation, add the posterior probability of each state at
        that position, to the emission table.  Note that tracks are also
        treated completely independently here"""
        assert obs.shape[1] == self.numTracks
        
        for i in xrange(len(obs)):
            for track in xrange(self.numTracks):
                for state in xrange(self.numStates):
                    obsVal = obs[i,track]
                    obsStats[track][state, obsVal] += posteriors[i, state]
        return obsStats
        
    def maximize(self, obsStats):
        for track in xrange(self.numTracks):
            for state in xrange(self.numStates):
                totalSymbol = 0.0
                for symbol in xrange(self.numSymbolsPerTrack[track]):
                    totalSymbol += obsStats[track][state, symbol]
                for symbol in xrange(self.numSymbolsPerTrack[track]):
                    denom = max(1e-20, totalSymbol)
                    symbolProb = obsStats[track][state, symbol] / denom
                    symbolProb = max(1e-20, symbolProb)
                    self.logProbs[track][state][symbol] = np.log(symbolProb)