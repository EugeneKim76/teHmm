#!/usr/bin/env python

#Copyright (C) 2013 by Glenn Hickey
#
#Released under the MIT license, see LICENSE.txt
#!/usr/bin/env python

import os
import sys
from pybedtools import BedTool, Interval

""" all track-data specific io code goes here.  Just BED implemented for now,
will eventually add WIG and maybe eventually bigbed / bigwig """

###########################################################################

def readTrackData(trackPath, chrom, start, end):
    """ read genome annotation track into python list of values.  a value
    is returned for every element in range (default value is None).  The
    type of file is detected from the extension"""
    data = None
    if not os.path.isfile(trackPath):
        sys.stderr.write("Warning: track file not found %s\n" %
                         trackPath)
        return None

    trackExt = os.path.splitext(trackPath)[1]
    if trackExt == ".bed":
        return readBedData(trackPath, chrom, start, end)
    else:
        sys.stderr.write("Warning: non-BED file skipped %s\n" %
                         trackPath)
    return None

###########################################################################

def readBedData(bedPath, chrom, start, end):
    data = [None] * (end - start)
    bedTool = BedTool(bedPath) 
    interval = Interval(chrom, start, end)
    
    # todo: check how efficient this is
    for overlap in bedTool.all_hits(interval):
        # todo: parameterize bed column we want to use
        oStart = max(start, overlap.start)
        oEnd = min(end, overlap.end)
        val = overlap.name
        for i in xrange(oEnd - oStart):
            data[i + oStart - start] = val

    return data

###########################################################################

def readBedIntervals(bedPath, chrom = None, start = None, end = None):
    if not os.path.isfile(bedPath):
        raise RuntimeError("Bed interval file %s not found" % bedPath)
    bedTool = BedTool(bedPath)
    if chrom is None:
        return [(feat.chrom, feat.start, feat.end) for feat in bedTool]
    else:
        assert start is not None and end is not None
        interval = Interval(chrom, start, end)            
        return [(feat.chrom, max(start, feat.start), min(end, feat.end))
                for feat in bedTool.all_hits(interval)]

