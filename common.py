#!/usr/bin/env python

#Copyright (C) 2013 by Glenn Hickey
#
#Released under the MIT license, see LICENSE.txt
import sys
import os
import argparse
import subprocess
from multiprocessing import Pool
import logging
import collections
import numpy as np
import string
import random
import pybedtools

LOGZERO = -1e100
EPSILON = np.finfo(float).eps

def __myLogFloat(x):
    if np.abs(x) < EPSILON:
        return LOGZERO
    return np.log(x)

""" Replace np.log to accept zero """
myLog = np.vectorize(__myLogFloat)
    
def runShellCommand(command):
    try:
        logging.debug("Running %s" % command)
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE,
                                   stderr=sys.stderr, bufsize=-1)
        output, nothing = process.communicate()
        sts = process.wait()
        if sts != 0:
            raise RuntimeError("Command: %s exited with non-zero status %i" %
                               (command, sts))
        return output
    except KeyboardInterrupt:
        raise RuntimeError("Aborting %s" % command)

def runParallelShellCommands(cmdList, numProc):
    if numProc == 1 or len(cmdList) == 1:
        map(runShellCommand, cmdList)
    elif len(cmdList) > 0:
        mpPool = Pool(processes=min(numProc, len(cmdList)))
        result = mpPool.map_async(runShellCommand, cmdList)
        # specifying a timeout allows keyboard interrupts to work?!
        # http://stackoverflow.com/questions/1408356/keyboard-interrupts-with-pythons-multiprocessing-pool
        try:
            result.get(sys.maxint)
        except KeyboardInterrupt:
            mpPool.terminate()
            raise RuntimeError("Keyboard interrupt")
        if not result.successful():
            raise "One or more of commands %s failed" % str(cmdList)

def initBedTool(tempPrefix=""):
    # keep temporary files in current directory, to make it a little harder to
    # lose track of them and clog up the system....
    S = string.ascii_uppercase + string.digits
    tag = ''.join(random.choice(S) for x in range(5))
    tempPath = os.path.join(os.getcwd(), "%sTempBedTool_%s" % (tempPrefix, tag))
    logging.info("Temporary directory for BedTools (you may need to manually"
                 " erase in event of crash): %s" % tempPath)
    return tempPath

def cleanBedTool(tempPath):
    # do best to erase temporary bedtool files if necessary
    # (tempPath argument must have been created with initBedTool())
    assert "TempBedTool_" in tempPath
    pybedtools.cleanup(remove_all=True)
    runShellCommand("rm -rf %s" % tempPath)

        
