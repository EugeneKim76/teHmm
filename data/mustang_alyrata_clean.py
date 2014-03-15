#!/usr/bin/env python

#Copyright (C) 2014 by Glenn Hickey
#
#Released under the MIT license, see LICENSE.txt
import sys
import os
import argparse
import logging
import numpy as np
import math
import copy

from teHmm.track import TrackList
from teHmm.trackIO import readTrackData
from teHmm.common import myLog, EPSILON, initBedTool, cleanBedTool
from teHmm.common import addLoggingOptions, setLoggingFromOptions, logger
from teHmm.common import runShellCommand, getLogLevelString, getLocalTempPath

"""

The HMM cannot use annotation tracks as output by several tools (ex repeatmasker)
without first doing some name-munging and setting some scaling parameters for binning.

This script takes as input a list of "raw" annotation tracks, and runs all the necessary scripts to produce a list of "clean" tracks that can be used by the HMM.

NOTE: This script is really hardcoded to run only on ./mustang_alyrata_tracks.xml at the moment, and needs to be updated to reflect changes to that file (maybe).  A more general workflow will need to be put in place later....
"""

def main(argv=None):
    if argv is None:
        argv = sys.argv

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Generate HMM-usable tracklist from raw tracklist. EX "
        "used to transform mustang_alyrata_tracks.xml -> "
        "mustang_alyrata_clean.xml.  Runs cleanChaux.py cleanLtrFinder.py and "
        " cleanTermini.py and addTsdTrack.py and setTrackScaling.py (also runs "
        " removeBedOverlaps.py before each of the clean scripts)")
    
    parser.add_argument("tracksInfo", help="Path of Tracks Info file "
                        "containing paths to genome annotation tracks")
    parser.add_argument("cleanTrackPath", help="Directory to write cleaned BED"
                        " tracks to")
    parser.add_argument("outTracksInfo", help="Path to write modified tracks XML"
                        " to.")
    parser.add_argument("--numBins", help="Maximum number of bins after scaling",
                        default=10, type=int)
    parser.add_argument("--scaleTracks", help="Comma-separated list of tracks "
                        "to process for scaling. If not set, all"
                        " tracks listed as having a multinomial distribution"
                        " (since this is the default value, this includes "
                        "tracks with no distribution attribute) will be"
                        " processed.", default=None)
    parser.add_argument("--skipScale", help="Comma-separated list of tracks to "
                        "skip for scaling.", default=None)
    parser.add_argument("--chaux", help="Name of chaux track", default="chaux")
    parser.add_argument("--ltrfinder", help="Name of ltrfinder track",
                        default="ltr_finder")
    parser.add_argument("--termini", help="Name of termini track",
                        default="termini")
    parser.add_argument("--sequence", help="Name of fasta sequence track",
                        default="sequence")
    parser.add_argument("--tsd", help="Name of tsd track to generate",
                        default="tsd")
    parser.add_argument("--tir", help="Name of tir_termini track",
                        default="tir_termini")
    parser.add_argument("--hollister", help="Name of hollister track",
                        default="hollister")
    parser.add_argument("--noScale", help="Dont do any scaling", default=False,
                        action="store_true")
    parser.add_argument("--noTsd", help="Dont generate TSD track.  NOTE:"
                        " TSD track is hardcoded to be generated from "
                        "termini and (non-LTR elements of ) chaux",
                        default=False, action="store_true")
    
    addLoggingOptions(parser)
    args = parser.parse_args()
    setLoggingFromOptions(args)
    tempBedToolPath = initBedTool()
    args.logOpString = "--logLevel %s" % getLogLevelString()
    if args.logFile is not None:
        args.logOpString += " --logFile %s" % args.logFile

    try:
        os.makedirs(args.cleanTrackPath)
    except:
        pass
    if not os.path.isdir(args.cleanTrackPath):
        raise RuntimeError("Unable to find or create cleanTrack dir %s" %
                           args.cleanTrackPath)

    tempTracksInfo = getLocalTempPath("Temp_mustang_alyrata_clean", "xml")
    runCleaning(args, tempTracksInfo)
    assert os.path.isfile(tempTracksInfo)

    runTsd(args, tempTracksInfo)
    
    runScaling(args, tempTracksInfo)

    runShellCommand("rm -f %s" % tempTracksInfo)

    cleanBedTool(tempBedToolPath)

def cleanPath(args, track):
    """ path of cleaned track """
    oldPath = track.getPath()
    oldFile = os.path.basename(oldPath)
    oldName, oldExt = os.path.splitext(oldFile)
    return os.path.join(args.cleanTrackPath, oldName + "_clean" + ".bed")
    
def runCleaning(args, tempTracksInfo):
    """ run scripts for cleaning chaux, ltr_finder, and termini"""
    trackList = TrackList(args.tracksInfo)

    # run cleanChaux.py on chaux track
    chauxTrack = trackList.getTrackByName(args.chaux)
    if chauxTrack is not None:
        inFile = chauxTrack.getPath()
        outFile = cleanPath(args, chauxTrack)
        tempBed = getLocalTempPath("Temp_chaux", ".bed")
        runShellCommand("removeBedOverlaps.py %s > %s" % (inFile, tempBed))
        runShellCommand("cleanChaux.py --keepUnderscore %s > %s" % (tempBed,
                                                                    outFile))
        runShellCommand("rm -f %s" % tempBed)
        chauxTrack.setPath(outFile)
    else:
        logger.warning("Could not find chaux track")

    # run cleanChaux.py on hollister track
    hollisterTrack = trackList.getTrackByName(args.hollister)
    if hollisterTrack is not None:
        inFile = hollisterTrack.getPath()
        outFile = cleanPath(args, hollisterTrack)
        tempBed = getLocalTempPath("Temp_hollister", ".bed")
        runShellCommand("removeBedOverlaps.py %s > %s" % (inFile, tempBed))
        runShellCommand("cleanChaux.py %s > %s" % (tempBed, outFile))
        runShellCommand("rm -f %s" % tempBed)
        hollisterTrack.setPath(outFile)
    else:
        logger.warning("Could not find hollister track")
                
    # run cleanTermini.py
    lastzTracks = [trackList.getTrackByName(args.termini),
                  trackList.getTrackByName(args.tir)]
    for terminiTrack in lastzTracks:
        if terminiTrack is not None:
            outFile = cleanPath(args, terminiTrack)
            inFile = terminiTrack.getPath()
            tempBed = None
            if inFile[-3:] == ".bb":
                tempBed = getLocalTempPath("Temp_termini", ".bed")
                runShellCommand("bigBedToBed %s %s" % (inFile, tempBed))
                inFile = tempBed
            runShellCommand("cleanTermini.py %s %s" % (inFile, outFile))
            terminiTrack.setPath(outFile)
            if tempBed is not None:
                runShellCommand("rm -f %s" % tempBed)
        else:
            logger.warning("Could not find termini track")

    # run cleanLtrFinder.py
    ltrfinderTrack = trackList.getTrackByName(args.ltrfinder)
    if ltrfinderTrack is not None:
        inFile = ltrfinderTrack.getPath()
        outFile = cleanPath(args, ltrfinderTrack)
        tempBed = getLocalTempPath("Temp_ltrfinder", ".bed")
        runShellCommand("removeBedOverlaps.py %s > %s" % (inFile, tempBed))
        runShellCommand("cleanLtrFinderID.py %s %s" % (tempBed, outFile))
        runShellCommand("rm -f %s" % tempBed)
        ltrfinderTrack.setPath(outFile)
    else:
        logger.warning("Could not find ltrfinder track")

    # save a temporary xml
    trackList.saveXML(tempTracksInfo)

def runScaling(args, tempTracksInfo):
    """ run setTrackScaling on temp track list"""
    tracksArg = ""
    if args.scaleTracks is not None:
        tracksArg = args.scaleTracks
    skipArg = ""
    if args.skipScale is not None:
        skipArg = args.skipScale

    if args.noScale is False:
        cmd = "setTrackScaling.py %s %d %s --logLevel %s %s %s" % (
            tempTracksInfo, args.numBins, args.outTracksInfo,
            getLogLevelString(), tracksArg, skipArg)
    else:
        cmd = "cp %s %s" % (tempTracksInfo, args.outTracksInfo)
    runShellCommand(cmd)

def runTsd(args, tempTracksInfo):
    """ run addTsdTrack on termini and chaux to generate tsd track"""
    if args.noTsd is True:
        return

    origTrackList = TrackList(args.tracksInfo)
    outTrackList = TrackList(tempTracksInfo)

    tempFiles = []
    tsdInputFiles = []
    tsdInputTracks = []
        
    # preprocess termini
    lastzTracks = [origTrackList.getTrackByName(args.termini)]
                  #origTrackList.getTrackByName(args.tir)]
    for terminiTrack in lastzTracks:
        if terminiTrack is not None:
            inFile = terminiTrack.getPath()
            fillFile = getLocalTempPath("Temp_fill", ".bed")
            tempBed = None
            if inFile[-3:] == ".bb":
                tempBed = getLocalTempPath("Temp_termini", ".bed")
                runShellCommand("bigBedToBed %s %s" % (inFile, tempBed))
                inFile = tempBed
            runShellCommand("fillTermini.py %s %s" % (inFile, fillFile))
            tsdInputFiles.append(fillFile)
            tsdInputTracks.append(terminiTrack.getName())
            tempFiles.append(fillFile)
            if tempBed is not None:
                runShellCommand("rm -f %s" % tempBed)
        else:
            logger.warning("Could not find termini track")

    # add chaux
    chauxTrack = outTrackList.getTrackByName(args.chaux)
    if chauxTrack is not None:
        tsdInputFiles.append(chauxTrack.getPath())
        tsdInputTracks.append(chauxTrack.getName())

    # run addTsdTrack (appending except first time)
    # note we override input track paths in each case
    assert len(tsdInputFiles) == len(tsdInputTracks)
    for i in xrange(len(tsdInputFiles)):
        appString = ""
        if i > 0:
            appString = "--append"
        nameString = ""
        if tsdInputTracks[i] == args.chaux:
            nameString = "--names non-LTR"

        tempXMLOut = getLocalTempPath("Temp_tsd_xml", ".xml")
        runShellCommand("addTsdTrack.py %s %s %s %s %s %s --inPath %s %s %s %s" % (
            tempTracksInfo,
            args.cleanTrackPath,
            tempXMLOut,
            tsdInputTracks[i],
            args.sequence,
            args.tsd,
            tsdInputFiles[i],
            appString,
            nameString,
            args.logOpString))
        
        runShellCommand("mv %s %s" % (tempXMLOut, tempTracksInfo))

    for i in xrange(len(tempFiles)):
        runShellCommand("rm %s" % tempFiles[i])

if __name__ == "__main__":
    sys.exit(main())
