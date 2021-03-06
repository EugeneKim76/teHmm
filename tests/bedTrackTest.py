#!/usr/bin/env python

#Copyright (C) 2013 by Glenn Hickey
#
#Released under the MIT license, see LICENSE.txt
import unittest
import sys
import os
from numpy.testing import assert_array_equal, assert_array_almost_equal
import scipy

from teHmm.trackIO import *
from teHmm.track import *
from teHmm.tests.common import getTestDirPath
from teHmm.tests.common import TestBase
from teHmm.common import intersectSize

def getTracksInfoPath(idx = 1):
    if idx == 1:
        return getTestDirPath("tracksInfo.xml")
    else:
        return getTestDirPath("tracksInfo%d.xml" % idx)

def getTrackList(idx = 1):
    return TrackList(getTracksInfoPath(idx))

def getStatesPath():
    return getTestDirPath("states.bed")

def getSegmentsPath():
    return getTestDirPath("segments.bed")

def getMaskPath():
    return getTestDirPath("mask.bed")

class TestCase(TestBase):

    def setUp(self):
        super(TestCase, self).setUp()
    
    def tearDown(self):
        super(TestCase, self).tearDown()

    def testBedQuery(self):
        ti = getTrackList()
        cbBedPath = ti.getTrackByName("cb").getPath()
        bedData = readTrackData(cbBedPath, "scaffold_1", 3000050, 3000070)
        for i in xrange(10):
            assert int(bedData[i]) == 4
        for i in xrange(11,20):
            assert int(bedData[i]) == 5

    def testBedIntervals(self):
        ti = getTrackList()
        cbBedPath = ti.getTrackByName("cb").getPath()
        intervals = readBedIntervals(cbBedPath, 3, "scaffold_1", 0, 3000060)
        assert len(intervals) == 2
        assert intervals[0] == ("scaffold_1", 0, 2000040)
        assert intervals[1] == ("scaffold_1", 2000040, 3000060)

    def testTrackTable(self):
        for TableType in [IntegerTrackTable]:
            table = TableType(3, "scaffold_1", 3000050, 3000070)
            mappedTable = TableType(3, "scaffold_1", 3000050, 3000070)
            catMap = CategoryMap()
            catMap.update(1000)
            catMap.update(66)
            catMap.update(0)
            catMap.update(1)
            catMap.update(2)
            assert table.getNumTracks() == 3
            assert len(table) == 3000070 - 3000050
            for track in xrange(3):
                table.writeRow(track, [track] * len(table))
                mappedTable.writeRow(
                    track,
                    [catMap.getMap(x) for x in [track] * len(table)])
            assert catMap.getMap(0) == 3
            assert catMap.getMap(1) == 4
            assert catMap.getMap(3) == catMap.getMissingVal()

            for col in xrange(len(table)): 
                for track in xrange(3):                
                    assert table[col][track] == track
                    assert mappedTable[col][track] == track + 3

    def testTrackData(self):
        trackData = TrackData(np.uint16)
        trackData.loadTrackData(getTracksInfoPath(),
                                [("scaffold_1", 0, 200004),
                                ("scaffold_1", 2000040, 3000060)])
        assert trackData.getNumTracks() == 3
        trackList = trackData.getTrackList()
        assert len(trackList) == 3
        assert trackList.getTrackByName("cb").name == "cb"
        assert trackList.getTrackByName("cb").getValCol() == 4
        assert trackList.getTrackByName("cb").getDist() == "multinomial"
        assert trackList.getTrackByName("kmer").name == "kmer"
        assert trackList.getTrackByName("blin") == None

        tableList = trackData.getTrackTableList()
        assert len(tableList) == 2
        assert tableList[0].getNumTracks() == 3
        assert tableList[1].getNumTracks() == 3
        assert len(tableList[0]) == 200004
        assert len(tableList[1]) == 3000060 - 2000040

        cbTrack = trackList.getTrackByName("cb")
        
        for i in xrange(len(tableList[0])):
            assert tableList[0][i][cbTrack.number] == 2

        for i in xrange(len(tableList[1])):
            assert tableList[1][i][cbTrack.number] == 3

    def testReadStates(self):
        bedIntervals = readBedIntervals(getStatesPath(), ncol=4)
        for interval in bedIntervals:
            assert int(interval[3]) == 0 or int(interval[3]) == 1

    def testBinaryTrack(self):
        trackData = TrackData()
        trackData.loadTrackData(getTracksInfoPath(2),
                                [("scaffold_1", 0, 200004),
                                ("scaffold_Q", 2000040, 3000060)])
        assert trackData.getNumTracks() == 3
        trackList = trackData.getTrackList()
        assert len(trackList) == 3
        assert trackList.getTrackByName("cb").name == "cb"
        assert trackList.getTrackByName("cb").getDist() == "binary"
        assert trackList.getTrackByName("kmer").name == "kmer"
        assert trackList.getTrackByName("blin") == None

        tableList = trackData.getTrackTableList()
        assert len(tableList) == 2
        assert tableList[0].getNumTracks() == 3
        assert tableList[1].getNumTracks() == 3
        assert len(tableList[0]) == 200004
        assert len(tableList[1]) == 3000060 - 2000040

        cbTrack = trackList.getTrackByName("cb")
        
        for i in xrange(len(tableList[0])):
            assert tableList[0][i][cbTrack.number] == 2

        for i in xrange(len(tableList[1])):
            assert tableList[1][i][cbTrack.number] == 1

    def testAlignmentTrack(self):
        trackData = TrackData(dtype=np.uint16)
        trackData.loadTrackData(getTracksInfoPath(1),
                                [("scaffold_1", 0, 200004),
                                ("scaffold_Q", 2000040, 3000060)])
        assert trackData.getNumTracks() == 3
        trackList = trackData.getTrackList()
        alignmentTrack = trackList.getAlignmentTrack() is not None
        assert alignmentTrack is not None

        trackTableList = trackData.getTrackTableList()
        assert trackTableList[0].getNumTracks() == 3
        alignmentTableList = trackData.getAlignmentTrackTableList()
        assert alignmentTableList[0].getNumTracks() == 1

        trackData2 = TrackData()
        trackData2.loadTrackData(getTracksInfoPath(2),
                                 [("scaffold_1", 0, 200004),
                                  ("scaffold_Q", 2000040, 3000060)])
        trackList2 = trackData2.getTrackList()
        alignmentTrack2 = trackList2.getAlignmentTrack()
        assert alignmentTrack2 is None

    def testScale(self):
        trackData1 = TrackData()
        trackData1.loadTrackData(getTracksInfoPath(),
                                 [("scaffold_1", 0, 10)])

        trackData2 = TrackData()
        trackData2.loadTrackData(getTracksInfoPath(2),
                                 [("scaffold_1", 0, 10)])

        tableList1 = trackData1.getTrackTableList()
        tableList2 = trackData2.getTrackTableList()
        track1 = trackData1.getTrackList().getTrackByName("kmer")
        track2 = trackData2.getTrackList().getTrackByName("kmer")
        trackNo1 = track1.getNumber()
        trackNo2 = track2.getNumber()
        assert len(tableList1) == len(tableList2)
        assert len(tableList1) == 1
        for i in xrange(len(tableList1[0])):
            bedVal = tableList1[0][i][trackNo1]
            bedVal2 = tableList2[0][i][trackNo2]
            bedVal = track1.getValueMap().getMapBack(bedVal)
            for j in xrange(len(tableList1[0])):
                bedValJ = tableList1[0][j][trackNo1]
                bedValJ2 = tableList2[0][j][trackNo2]
                bedValJ = track1.getValueMap().getMapBack(bedValJ)
                if int(0.1 * float(bedVal)) == int(0.1 * float(bedValJ)): 
                    assert bedVal2 == bedValJ2
                else:
                    assert bedVal2 != bedValJ2

    def testScale2(self):
        cmap = CategoryMap()
        assert cmap.getMap(None) == 0

        cmap = CategoryMap(scale=0.1)
        assert cmap.getMap(10, update=True) == 1
        assert cmap.getMapBack(1) == 10
        assert cmap.getMap(15, update=True) == 1
        assert cmap.getMapBack(1) == 10
        assert cmap.getMap(35, update=True) == 2
        assert cmap.getMap(25, update=True) == 3
        assert cmap.getMapBack(3) == 20
        assert cmap.getMap(0, update=True) == 4
        assert cmap.getMapBack(4) == 0

        cmap = CategoryMap(logScale=2.)
        assert cmap.getMap(1) == 0
        assert cmap.getMap(1, update=True) == 1
        assert cmap.getMap(0.001, update=True) == 2
        assert cmap.getMap(0.0015, update=True) == 2
        assert cmap.getMap(1100, update=True) == 3
        assert cmap.getMap(1600, update=True) == 3
        cmb = cmap.getMapBack(3)
        assert int(np.log2(cmb)) == int(np.log2(1100))
        assert int(np.log2(cmb)) == int(np.log2(1600))

    def testDeltaMode(self):
        trackData1 = TrackData()
        trackData1.loadTrackData(getTracksInfoPath(5),
                                 [("scaffold_1", 0, 100)])

        tableList1 = trackData1.getTrackTableList()
        track1 = trackData1.getTrackList().getTrackByName("kmer")
        track2 = trackData1.getTrackList().getTrackByName("kmerDelta")
        trackNo1 = track1.getNumber()
        trackNo2 = track2.getNumber()
        pv1 = 0
        for i in xrange(len(tableList1[0])):
            bedVal = tableList1[0][i][trackNo1]
            bedVal2 = tableList1[0][i][trackNo2]
            v1 = int(track1.getValueMap().getMapBack(bedVal))
            v2 = int(track2.getValueMap().getMapBack(bedVal2))
            assert v2 == v1 - pv1
            pv1 = v1

    def testShift(self):
        trackData1 = TrackData()
        trackData1.loadTrackData(getTracksInfoPath(5),
                                 [("scaffold_1", 999, 1002)])
        tableList1 = trackData1.getTrackTableList()
        track1 = trackData1.getTrackList().getTrackByName("kmer")
        track2 = trackData1.getTrackList().getTrackByName("kmerShift")
        track3 = trackData1.getTrackList().getTrackByName("kmerShiftLog")
        trackNo1 = track1.getNumber()
        trackNo2 = track2.getNumber()
        trackNo3 = track3.getNumber()

        vm1 = track1.getValueMap()
        vm2 = track2.getValueMap()
        vm3 = track3.getValueMap()
        
        for i in xrange(len(tableList1[0])):
            bedVal1 = float(vm1.getMapBack(tableList1[0][i][trackNo1]))
            bedVal2 = float(vm2.getMapBack(tableList1[0][i][trackNo2]))
            bedVal3 = float(vm3.getMapBack(tableList1[0][i][trackNo3]))
            assert bedVal2 == bedVal1
            assert bedVal3 == np.power(2., int(np.log(bedVal1 + 10.0) / np.log(2.))) - 10.0

        cmap = CategoryMap(shift=1, logScale=10, defaultVal=0.0)
        for i in xrange(0, 999):
            cmap.update(i)
        x = cmap.getMap('0')
        for i in xrange(0, 9):
            assert cmap.getMap(str(i)) == x
        y = cmap.getMap('10')
        assert y != x
        for i in xrange(10, 99):
            assert cmap.getMap(str(i)) == y
        z = cmap.getMap('100')
        assert z != x and z != y
        for i in xrange(100, 999):
            assert cmap.getMap(str(i)) == z
        assert cmap.getMissingVal() == cmap.getMap('0')

            
    
    def testFastaTrack(self):
        trackData = TrackData()
        trackData.loadTrackData(getTracksInfoPath(4),
                                [("scaffold_1", 1, 19),
                                 ("scaffold_2", 0, 10)]),
        assert trackData.getNumTracks() == 3
        trackList = trackData.getTrackList()
        assert len(trackList) == 3
        assert trackList.getTrackByName("seqBinary").name == "seqBinary"
        assert trackList.getTrackByName("seqBinary").getDist() == "binary"
        assert trackList.getTrackByName("seqMulti").name == "seqMulti"
        assert trackList.getTrackByName("seqMulti").getDist() == "multinomial"
        assert trackList.getTrackByName("seqMulti").getCaseSensitive() == False
        assert trackList.getTrackByName("seqMultiCS").getCaseSensitive() == True
        assert trackList.getTrackByName("blin") == None

        tableList = trackData.getTrackTableList()
        assert len(tableList) == 2
        assert tableList[0].getNumTracks() == 3
        assert tableList[1].getNumTracks() == 3
        assert len(tableList[0]) == 18
        assert len(tableList[1]) == 10

        binTrack = trackList.getTrackByName("seqBinary")
        assert binTrack.getDist() == "binary"
        track = trackList.getTrackByName("seqMulti")
        assert track.getDist() == "multinomial"
        trackCS = trackList.getTrackByName("seqMultiCS")
        assert trackCS.getDist() == "multinomial"

        trueString = "AAATTTGGGCCCGGGccc"[1:19]
        for i in xrange(len(trueString)):
            bval = tableList[0][i][binTrack.number]
            val = tableList[0][i][track.number]
            valCS = tableList[0][i][trackCS.number]

            bval = binTrack.getValueMap().getMapBack(bval)
            val = track.getValueMap().getMapBack(val)
            valCS = trackCS.getValueMap().getMapBack(valCS)

            assert bval == 1
            assert val == trueString[i].upper()
            assert valCS == trueString[i]

        trueString = "TTTT"
        for i in xrange(len(trueString)):
            bval = tableList[1][i][binTrack.number]
            val = tableList[1][i][track.number]
            valCS = tableList[1][i][trackCS.number]

            bval = binTrack.getValueMap().getMapBack(bval)
            val = track.getValueMap().getMapBack(val)
            valCS = trackCS.getValueMap().getMapBack(valCS)

            assert bval == 1
            assert val == trueString[i].upper()
            assert valCS == trueString[i]

        for i in xrange(len(trueString), 10):
            bval = tableList[1][i][binTrack.number]
            val = tableList[1][i][track.number]
            valCS = tableList[1][i][trackCS.number]

            bval = binTrack.getValueMap().getMapBack(bval)
            val = track.getValueMap().getMapBack(val)
            valCS = trackCS.getValueMap().getMapBack(valCS)

            assert bval == 0
            assert val == None
            assert valCS == None

    def testCatMapSort(self):        
        catMap = CategoryMap()
        catMap.update(1000)
        catMap.update(66)
        catMap.update(0)
        catMap.update(1)
        catMap.update(2)

        catMap.sort()

        for key, val in catMap.catMap.items():
            for key2, val2 in catMap.catMap.items():
                if key2 < key:
                    assert val2 < val
                elif key < key2:
                    assert val2 > val

        catMap.update('1000')
        catMap.update('66')
        catMap.update('0')
        catMap.update('1')
        catMap.update('2')

        catMap.sort()

        for key, val in catMap.catMap.items():
            for key2, val2 in catMap.catMap.items():
                if int(key2) < int(key):
                    assert val2 < val
                elif int(key) < int(key2):
                    assert val2 > val

    def testDefault(self):
        trackData1 = TrackData()
        trackData1.loadTrackData(getTracksInfoPath(5),
                                 [("scaffold_1", 99999, 100001)])
        tableList1 = trackData1.getTrackTableList()
        track1 = trackData1.getTrackList().getTrackByName("kmer")
        track2 = trackData1.getTrackList().getTrackByName("kmerDefault")
        trackNo1 = track1.getNumber()
        trackNo2 = track2.getNumber()

        vm1 = track1.getValueMap()
        vm2 = track2.getValueMap()

        assert track1.getDefaultVal() == None
        assert track2.getDefaultVal() == "0.0"

        i = 0
        bedVal1 = float(vm1.getMapBack(tableList1[0][i][trackNo1]))
        bedVal2 = float(vm2.getMapBack(tableList1[0][i][trackNo2]))
        assert bedVal2 == bedVal1

        i = 1
        bedVal1 = vm1.getMapBack(tableList1[0][i][trackNo1])
        bedVal2 = vm2.getMapBack(tableList1[0][i][trackNo2])
        assert bedVal1 == None
        assert bedVal2 == "0.0"

    def testSegment(self):
        statesPath = getStatesPath()
        segPath = getSegmentsPath()

        bedIntervals = readBedIntervals(getStatesPath(), sort=True)
        segIntervals = readBedIntervals(getSegmentsPath(), sort=True)
        
        trackData = TrackData()
        trackData.loadTrackData(getTracksInfoPath(7), bedIntervals)

        segTrackData = TrackData()
        segTrackData.loadTrackData(getTracksInfoPath(7), bedIntervals,
                                   segmentIntervals=segIntervals,
                                   interpolateSegments=False)
        segTrackData2 = TrackData()
        segTrackData2.loadTrackData(getTracksInfoPath(7), bedIntervals,
                                   segmentIntervals=segIntervals,
                                   interpolateSegments=True)

        tlist1 = trackData.getTrackTableList()
        tlist2 = segTrackData.getTrackTableList()
        assert len(tlist1) == len(tlist2)
        assert len(tlist1) == 5
        tlist3 = segTrackData2.getTrackTableList()
        assert len(tlist3) == len(tlist2)

        trackList = trackData.getTrackList()
        segTrackList = segTrackData2.getTrackList()
        
        icount = 0
        segLens = [2, 1, 3, 2, 2]
        for i in xrange(5):
            t1 = tlist1[i]
            t2 = tlist2[i]
            t3 = tlist3[i]
            assert len(t1) == bedIntervals[i][2] - bedIntervals[i][1]
            assert len(t2) == segLens[i]
            segLenRatios = t2.getSegmentLengthsAsRatio(100)
            for j in xrange(len(t2)):
                assert_array_equal(t2[j], t1[t2.segOffsets[j]])
                coord = t2.segOffsets[j] + t2.getStart()
                assert coord == segIntervals[icount][1]
                length = segIntervals[icount][2] - segIntervals[icount][1]
                assert length == t2.getSegmentLength(j)
                assert float(length) / 100. == segLenRatios[j]
                originalData = t1[t2.segOffsets[j]:t2.segOffsets[j] + length]
                for track in trackList:
                    trackNo = track.getNumber()
                    if track.getDist() != "gaussian":
                        originalMode = scipy.stats.mode(originalData)[0][0]
                        assert_array_equal(originalMode[trackNo], t3[j][trackNo])
                    else:
                        originalValues = [track.getValueMap().getMapBack(
                            originalData[x, trackNo])
                            for x in xrange(len(originalData))]
                        originalMean = np.mean(originalValues)
                        dataMean = t3[j][trackNo]
                        originalScaledMean = segTrackList.getTrackByName(
                            track.getName()).getValueMap().getMap(originalMean)
                        assert_array_equal(originalScaledMean, t3[j][trackNo])
                icount += 1

    def testMask(self):
        trackData1 = TrackData()
        trackData1.loadTrackData(getTracksInfoPath(8),
                                 [("scaffold_1", 0, 50)])        
        tableList1 = trackData1.getTrackTableList()

        trackData2 = TrackData()
        trackData2.loadTrackData(getTracksInfoPath(7),
                                 [("scaffold_1", 0, 50)])        
        tableList2 = trackData2.getTrackTableList()

        assert len(tableList1) == 1
        assert len(tableList2) == len(tableList1)
        table1 = tableList1[0]
        table2 = tableList2[0]

        assert len(table2) == 50
        assert len(table1) == 39

        maskOffsets1 = table1.getMaskRunningOffsets()
        maskOffsets2 = table2.getMaskRunningOffsets()

        assert maskOffsets2 == None
        for i in xrange(len(table1)):
            v1 = table1[i]
            v2 = table2[i + maskOffsets1[i]]
            assert_array_equal(v1, v2)

        # now test segmentation
        statesPath = getStatesPath()
        segPath = getSegmentsPath()

        bedIntervals = getMergedBedIntervals(getStatesPath(), sort=True)
        segIntervals = readBedIntervals(getSegmentsPath(), sort=True)
        
        segTrackData2 = TrackData()
        segTrackData2.loadTrackData(getTracksInfoPath(7), bedIntervals,
                                   segmentIntervals=segIntervals,
                                   interpolateSegments=True)
        segTrackData3 = TrackData()
        segTrackData3.loadTrackData(getTracksInfoPath(9), bedIntervals,
                                   segmentIntervals=segIntervals,
                                   interpolateSegments=True)

        tlist3 = segTrackData2.getTrackTableList()
        tlist4 = segTrackData3.getTrackTableList()
        assert len(tlist4) == 3
        assert len(tlist3) == 4

        maskIntervals = getMergedBedIntervals(getMaskPath(), sort=True)

        tracks2 = segTrackData2.getTrackList()
        tracks3 = segTrackData3.getTrackList()

        for i in xrange(len(tlist4)):
            t3 = tlist3[i]
            t4 = tlist4[i]
            maskOffsets = t4.getMaskRunningOffsets()
            assert maskOffsets is not None
            assert t3.getMaskRunningOffsets() is None
            k = 0
            for j in xrange(len(t3)):
                start3 = t3.start + t3.segOffsets[j]
                len3 = t3.getSegmentLength(j)
                end3 = start3 + len3
                i3 = (t3.chrom, start3, end3)
                masked = False
                for x in maskIntervals:
                    if intersectSize(i3, x) > 0:
                        masked = True
                        assert intersectSize(i3, x) == i3[2] - i3[1]
                if masked is False:
                    start4 = t4.start + t4.segOffsets[k] + maskOffsets[k]
                    len4 = t4.getSegmentLength(k)
                    end4 = start4 + len4
                    i4 = (t4.chrom, start4, end4)
                    assert_array_equal(i3, i4)
                    v3 = [tracks2.getTrackByNumber(x).getValueMap().getMapBack(t3[j][x]) for x in xrange(len(t3[j]))]
                    v4 = [tracks3.getTrackByNumber(x).getValueMap().getMapBack(t4[k][x]) for x in xrange(len(t4[k]))]
                    assert_array_equal(v3, v4)
                    k += 1                    
        
def main():
    sys.argv = sys.argv[:1]
    unittest.main()
        
if __name__ == '__main__':
    main()

