#!/usr/bin/env python

#Copyright (C) 2013 by Glenn Hickey
#
#Released under the MIT license, see LICENSE.txt
import unittest
import sys
import os
import argparse
import logging
import random
import numpy as np

from teHmm.track import TrackData
from teHmm.trackIO import readBedIntervals, getMergedBedIntervals
from teHmm.hmm import MultitrackHmm
from teHmm.emission import IndependentMultinomialAndGaussianEmissionModel
from teHmm.emission import PairEmissionModel
from teHmm.track import CategoryMap, BinaryMap
from teHmm.cfg import MultitrackCfg
from teHmm.modelIO import saveModel
from teHmm.common import myLog, EPSILON, initBedTool, cleanBedTool, LOGZERO
from teHmm.common import addLoggingOptions, setLoggingFromOptions, logger
from teHmm.common import runParallelShellCommands
from teHmm.bin.compareBedStates import checkExactOverlap

def main(argv=None):
    if argv is None:
        argv = sys.argv
        
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Create a teHMM")

    parser.add_argument("tracksInfo", help="Path of Tracks Info file "
                        "containing paths to genome annotation tracks")
    parser.add_argument("trainingBed", help="Path of BED file containing"
                        " genome regions to train model on.  If --supervised "
                        "is used, the names in this bed file will be treated "
                        "as the true annotation (otherwise it is only used for "
                        "interval coordinates)")
    parser.add_argument("outputModel", help="Path of output hmm")
    parser.add_argument("--numStates", help="Number of states in model",
                        type = int, default=2)
    parser.add_argument("--iter", help="Number of EM iterations",
                        type = int, default=100)
    parser.add_argument("--supervised", help="Use name (4th) column of "
                        "<traingingBed> for the true hidden states of the"
                        " model.  Transition parameters will be estimated"
                        " directly from this information rather than EM."
                        " NOTE: The number of states will be determined "
                        "from the bed.",
                        action = "store_true", default = False)
    parser.add_argument("--cfg", help="Use Context Free Grammar insead of "
                        "HMM.  Only works with --supervised for now",
                        action = "store_true", default = False)
    parser.add_argument("--saPrior", help="Confidence in self alignment "
                        "track for CFG.  Probability of pair emission "
                        "is multiplied by this number if the bases are aligned"
                        " and its complement if bases are not aligned. Must"
                        " be between [0,1].", default=0.95, type=float)
    parser.add_argument("--pairStates", help="Comma-separated list of states"
                        " (from trainingBed) that are treated as pair-emitors"
                        " for the CFG", default=None)
    parser.add_argument("--emFac", help="Normalization factor for weighting"
                        " emission probabilities because when there are "
                        "many tracks, the transition probabilities can get "
                        "totally lost. 0 = no normalization. 1 ="
                        " divide by number of tracks.  k = divide by number "
                        "of tracks / k", type=int, default=0)
    parser.add_argument("--initTransProbs", help="Path of text file where each "
                        "line has three entries: FromState ToState Probability"
                        ".  This file (all other transitions get probability 0)"
                        " is used to specifiy the initial transition model."
                        " The names and number of states will be initialized "
                        "according to this file (overriding --numStates)",
                        default = None)
    parser.add_argument("--fixTrans", help="Do not learn transition parameters"
                        " (best used with --initTransProbs)",
                        action="store_true", default=False)
    parser.add_argument("--initEmProbs", help="Path of text file where each "
                        "line has four entries: State Track Symbol Probability"
                        ".  This file (all other emissions get probability 0)"
                        " is used to specifiy the initial emission model. All "
                        "states specified in this file must appear in the file"
                        " specified with --initTransProbs (but not vice versa).",
                        default = None)
    parser.add_argument("--fixEm", help="Do not learn emission parameters"
                        " (best used with --initEmProbs)",
                        action="store_true", default=False)
    parser.add_argument("--initStartProbs", help="Path of text file where each "
                        "line has two entries: State Probability"
                        ".  This file (all other start probs get probability 0)"
                        " is used to specifiy the initial start dist. All "
                        "states specified in this file must appear in the file"
                        " specified with --initTransProbs (but not vice versa).",
                        default = None)
    parser.add_argument("--fixStart", help="Do not learn start parameters"
                        " (best used with --initStartProbs)",
                        action="store_true", default=False)
    parser.add_argument("--forceTransProbs",
                        help="Path of text file where each "
                        "line has three entries: FromState ToState Probability" 
                        ". These transition probabilities will override any "
                        " learned probabilities after each training iteration"
                        " (unspecified "
                        "will not be set to 0 in this case. the learned values"
                        " will be kept, but normalized as needed)" ,
                        default=None)
    parser.add_argument("--forceEmProbs", help="Path of text file where each "
                        "line has four entries: State Track Symbol Probability"
                        ". These "
                        "emission probabilities will override any learned"
                        " probabilities after each training iteration "
                        "(unspecified "
                        "will not be set to 0 in this case. the learned values"
                        " will be kept, but normalized as needed.)" ,
                        default = None) 
    parser.add_argument("--flatEm", help="Use a flat emission distribution as "
                        "a baseline.  If not specified, the initial emission "
                        "distribution will be randomized by default.  Emission"
                        " probabilities specified with --initEmpProbs or "
                        "--forceEmProbs will never be affected by randomizaiton"
                        ".  The randomization is important for Baum Welch "
                        "training, since if two states dont have at least one"
                        " different emission or transition probability to begin"
                        " with, they will never learn to be different.",
                        action="store_true", default=False)
    parser.add_argument("--emRandRange", help="When randomly initialzing an"
                        " emission distribution, constrain"
                        " the values to the given range (pair of "
                        "comma-separated numbers).  Overridden by "
                        "--initEmProbs and --forceEmProbs when applicable."
                        " Completely overridden by --flatEm (which is equivalent"
                        " to --emRandRange .5,.5.). Actual values used will"
                        " always be normalized.", default="0.2,0.8")
    parser.add_argument("--segment", help="Bed file of segments to treat as "
                        "single columns for HMM (ie as created with "
                        "segmentTracks.py).  IMPORTANT: this file must cover "
                        "the same regions as the traininBed file. Unless in "
                        "supervised mode, probably best to use same bed file "
                        " as both traingBed and --segment argument.  Otherwise"
                        " use intersectBed to make sure the overlap is exact",
                        default=None)
    parser.add_argument("--segLen", help="Effective segment length used for"
                        " normalizing input segments (specifying 0 means no"
                        " normalization applied)", type=int, default=0)
    parser.add_argument("--seed", help="Seed for random number generator"
                        " which will be used to initialize emissions "
                        "(if --flatEM and --supervised not specified)",
                        default=None, type=int)
    parser.add_argument("--reps", help="Number of replicates (with different"
                         " random initializations) to run. The replicate"
                         " with the highest likelihood will be chosen for the"
                         " output", default=1, type=int)
    parser.add_argument("--numThreads", help="Number of threads to use when"
                        " running replicates (see --rep) in parallel.",
                        type=int, default=1)
    parser.add_argument("--emThresh", help="Threshold used for convergence"
                        " in baum welch training.  IE delta log likelihood"
                        " must be bigger than this number (which should be"
                        " positive) for convergence", type=float,
                        default=0.001)
    parser.add_argument("--saveAllReps", help="Save all replicates (--reps)"
                        " models to disk, instead of just the best one"
                        ". Format is <outputModel>.repN.  There will be "
                        " --reps -1 such models saved as the best output"
                        " counts as a replicate",
                        action="store_true", default=False)
    parser.add_argument("--maxProb", help="Gaussian distributions and/or"
                        " segment length corrections can cause probability"
                        " to *decrease* during BW iteration.  Use this option"
                        " to remember the parameters with the highest probability"
                        " rather than returning the parameters after the final "
                        "iteration.", action="store_true", default=False)
    parser.add_argument("--maxProbCut", help="Use with --maxProb option to stop"
                        " training if a given number of iterations go by without"
                        " hitting a new maxProb", default=None, type=int)
    parser.add_argument("--transMatEpsilons", help="By default, epsilons are"
                        " added to all transition probabilities to prevent "
                        "converging on 0 due to rounding error only for fully"
                        " unsupervised training.  Use this option to force this"
                        " behaviour for supervised and semisupervised modes",
                        action="store_true", default=False)

    addLoggingOptions(parser)
    args = parser.parse_args()
    if args.cfg is True:
        assert args.supervised is True
        assert args.saPrior >= 0. and args.saPrior <= 1.
    if args.pairStates is not None:
        assert args.cfg is True
    if args.initTransProbs is not None or args.fixTrans is True or\
      args.initEmProbs is not None or args.fixEm is not None:
        if args.cfg is True:
            raise RuntimeError("--transProbs, --fixTrans, --emProbs, --fixEm "
                               "are not currently compatible with --cfg.")
    if args.fixTrans is True and args.supervised is True:
        raise RuntimeError("--fixTrans option not compatible with --supervised")
    if args.fixEm is True and args.supervised is True:
        raise RuntimeError("--fixEm option not compatible with --supervised")
    if (args.forceTransProbs is not None or args.forceEmProbs is not None) \
      and args.cfg is True:
        raise RuntimeError("--forceTransProbs and --forceEmProbs are not "
                           "currently compatible with --cfg")
    if args.flatEm is True and args.supervised is False and\
      args.initEmProbs is None and args.initTransProbs is None:
      raise RuntimeError("--flatEm must be used with --initEmProbs and or"
                         " --initTransProbs")
    if args.initEmProbs is not None and args.initTransProbs is None:
        raise RuntimeError("--initEmProbs can only be used in conjunction with"
                           " --initTransProbs")
    if args.emRandRange is not None:
        args.emRandRange = args.emRandRange.split(",")
        try:
            assert len(args.emRandRange) == 2
            args.emRandRange = (float(args.emRandRange[0]),
                                float(args.emRandRange[1]))
        except:
            raise RuntimeError("Invalid --emRandRange specified")
    if args.transMatEpsilons is False:
        # old logic here. now overriden with above options
        args.transMatEpsilons = (args.supervised is False and
                                 args.initTransProbs is None and
                                 args.forceTransProbs is None)

    setLoggingFromOptions(args)
    tempBedToolPath = initBedTool()

    # read training intervals from the bed file
    logger.info("loading training intervals from %s" % args.trainingBed)
    mergedIntervals = getMergedBedIntervals(args.trainingBed, ncol=4)
    if mergedIntervals is None or len(mergedIntervals) < 1:
        raise RuntimeError("Could not read any intervals from %s" %
                           args.trainingBed)

    # read segment intervals
    segIntervals = None
    if args.segment is not None:
        logger.info("loading segment intervals from %s" % args.segment)
        try:
            checkExactOverlap(args.trainingBed, args.segment)
        except:
            raise RuntimeError("bed file passed with --segments option"
                               " must exactly overlap trainingBed")
        segIntervals = readBedIntervals(args.segment, sort=True)
    elif args.segLen > 0:
        raise RuntimeError("--segLen can only be used with --segment")
    if args.segLen <= 0:
        args.segLen = None
    if args.segLen > 0 and args.segLen != 1:
        logger.warning("--segLen should be 0 (no correction) or 1 (base"
                       " correction).  Values > 1 may cause bias.")

    # read the tracks, while intersecting them with the training intervals
    logger.info("loading tracks %s" % args.tracksInfo)
    trackData = TrackData()
    trackData.loadTrackData(args.tracksInfo, mergedIntervals,
                            segmentIntervals=segIntervals)

    catMap = None
    userTrans = None
    if args.supervised is False and args.initTransProbs is not None:
        logger.debug("initializing transition model with user data")
        catMap = stateNamesFromUserTrans(args.initTransProbs)
        # state number is overrided by the transProbs file
        args.numStates = len(catMap)

    truthIntervals = None
    # state number is overrided by the input bed file in supervised mode
    if args.supervised is True:
        logger.info("processing supervised state names")
        # we reload because we don't want to be merging them here
        truthIntervals = readBedIntervals(args.trainingBed, ncol=4)
        catMap = mapStateNames(truthIntervals)
        args.numStates = len(catMap)

    # train the model
    seeds = [random.randint(0, 4294967294)]
    if args.seed is not None:
        seeds = [args.seed]
        random.seed(args.seed)
    seeds += [random.randint(0, sys.maxint) for x in xrange(1, args.reps)]

    def trainClosure(randomSeed):
        return trainModel(randomSeed, trackData=trackData, catMap=catMap,
                          userTrans=userTrans, truthIntervals=truthIntervals,
                          args=args)
    
    modelList = runParallelShellCommands(argList=seeds, numProc = args.numThreads,
                                         execFunction = trainClosure,
                                         useThreads = True)

    # select best model
    logmsg = ""
    bestModel = (-1, LOGZERO)
    for i in xrange(len(modelList)):
        curModel = (i, modelList[i].getLastLogProb())
        if curModel[1] > bestModel[1]:
            bestModel = curModel
        if curModel[1] is not None:
            logmsg += "Rep %i: TotalProb: %f\n" % curModel
    if len(modelList) > 1:
        logging.info("Training Replicates Statistics:\n%s" % logmsg)
        logging.info("Selecting best replicate (%d, %f)" % bestModel)
    model = modelList[bestModel[0]]
        
    # write the model to a pickle
    logger.info("saving trained model to %s" % args.outputModel)
    saveModel(args.outputModel, model)

    # write all replicates
    writtenCount = 0
    if args.saveAllReps is True:
        for i, repModel in enumerate(modelList):
            if i != bestModel[0]:
                repPath = "%s.rep%d" % (args.outputModel, writtenCount)
                logger.info("saving replicate model to %s" % repPath)                
                saveModel(repPath, repModel)
                writtenCount += 1

    cleanBedTool(tempBedToolPath)

###########################################################################

def trainModel(randomSeed, trackData, catMap, userTrans, truthIntervals,
               args):
    """ Run the whole training pipeline
    """
    # activate the random seed
    randGen = np.random.RandomState(randomSeed)

    # create the independent emission model
    logger.info("creating emission model")
    numSymbolsPerTrack = trackData.getNumSymbolsPerTrack()
    logger.debug("numSymbolsPerTrack=%s" % numSymbolsPerTrack)
    # only randomize model if using Baum-Welch 
    randomize = args.supervised is False and args.flatEm is False
    emissionModel = IndependentMultinomialAndGaussianEmissionModel(
        args.numStates,
        numSymbolsPerTrack,
        trackData.getTrackList(),
        normalizeFac=args.emFac,
        randomize=randomize,
        effectiveSegmentLength = args.segLen,
        random_state = randGen,
        randRange = args.emRandRange)

    # create the model
    if not args.cfg:
        logger.info("creating hmm model")
        model = MultitrackHmm(emissionModel, n_iter=args.iter,
                              state_name_map=catMap,
                              fixTrans = args.fixTrans,
                              fixEmission = args.fixEm,
                              fixStart = args.fixStart,
                              forceUserEmissions = args.forceEmProbs,
                              forceUserTrans = args.forceTransProbs,
                              random_state = randGen,
                              thresh = args.emThresh,
                              transMatEpsilons = args.transMatEpsilons,
                              maxProb = args.maxProb,
                              maxProbCut = args.maxProbCut)
    else:
        pairEM = PairEmissionModel(emissionModel, [args.saPrior] *
                                   emissionModel.getNumStates())
        assert args.supervised is True
        nestStates = []
        if args.pairStates is not None:
            pairStates = args.pairStates.split(",")
            nestStates = map(lambda x: catMap.getMap(x), pairStates)
        logger.info("Creating cfg model")
        model = MultitrackCfg(emissionModel, pairEM, nestStates,
                              state_name_map=catMap)

    # initialize the user specified transition probabilities now if necessary
    if args.initTransProbs is not None:
        with open(args.initTransProbs) as f:
            model.applyUserTrans(f.readlines())

    # initialize the user specified emission probabilities now if necessary
    if args.initEmProbs is not None:
        with open(args.initEmProbs) as f:
            # can't apply emissions without a track list! 
            model.trackList = trackData.getTrackList()
            model.applyUserEmissions(f.readlines())

    # initialize the user specified start probabilities now if necessary
    if args.initStartProbs is not None:
        with open(args.initStartProbs) as f:
            model.applyUserStarts(f.readlines())

    # make sure initialization didnt screw up
    model.validate()

    # do the training
    if args.supervised is False:
        logger.info("training via EM")
        model.train(trackData)
    else:
        logger.info("training from input bed states")
        model.supervisedTrain(trackData, truthIntervals)

    # reset the user specified transition probabilities now if necessary
    if args.forceTransProbs is not None:
        with open(args.forceTransProbs) as f:
            model.applyUserTrans(f.readlines())

    # reset the user specified emission probabilities now if necessary
    if args.forceEmProbs is not None:
        with open(args.forceEmProbs) as f:
            model.applyUserEmissions(f.readlines())

    return model

###########################################################################
                
def stateNamesFromUserTrans(userTransPath):
    """ Scan the user transitions to determine all state names.  """
    catMap = CategoryMap(reserved=0)
    f = open(userTransPath, "r")
    for line in f:
        if len(line.lstrip()) > 0 and line.lstrip()[0] is not "#":
            toks = line.split()
            assert len(toks) == 3
            float(toks[2])
            catMap.getMap(toks[0], update=True)
            catMap.getMap(toks[1], update=True)
    f.close()
    return catMap

###########################################################################
    
def mapStateNames(bedIntervals):
    """ sanitize the states (column 4) of each bed interval, mapping to unique
    integer in place.  return the map"""
    catMap = CategoryMap(reserved=0)
    for idx, interval in enumerate(bedIntervals):
        if len(interval) < 4 or interval[3] is None:
            raise RuntimeError("Could not read state from 4th column" %
                               str(interval))
        bedIntervals[idx] = (interval[0], interval[1], interval[2],
                             catMap.getMap(interval[3], update=True))
    return catMap

###########################################################################



if __name__ == "__main__":
    sys.exit(main())

    
