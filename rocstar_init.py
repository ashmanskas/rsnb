#! /usr/bin/env python3

import argparse
import glob
import os
import sys
import time

from collections import namedtuple
from dataclasses import dataclass
from typing import Any, List

import pexpect

sys.path.append("/home/ashmansk/u/proj/rocstar/gui/")
import busio
import testpattern as tp


@dataclass
class Event:
    tcell: int
    whichdrs: int
    ddfdat: List[int]
    wavedat: List[int]


class RocstarInit(object):

    def __init__(self, boardnum=45):
        self.ipaddr = "192.168.1.%d"%(boardnum)
        self.m = None

    def is_alive(self):
        print("++ check whether board is alive")
        cmd = "ping -c 1 %s"%(self.ipaddr)
        print(cmd)
        log, rc = pexpect.run(cmd, withexitstatus=1)
        self.ping_log = log
        if rc==0:
            print("%s is alive"%(self.ipaddr))
        else:
            print("%s is dead"%(self.ipaddr))
        return rc==0

    def sleep(self, seconds):
        for i in range(int(math.ceil(seconds)), 0, -1):
            print("  wait %d seconds ..."%(i), end="\r", flush=True)
            time.sleep(1)
        print("  wait for %.0f seconds ... done"%(seconds))

    def sep(self, cmd, echo=False, timeout=-1, comment=None):
        """
        send line, then expect prompt
        """
        c = self.child
        if comment:
            print("# %s"%(comment))
        if echo:
            print(cmd, end="\r", flush=True)
        c.sendline(cmd)
        c.expect(self.prompt, timeout=timeout)
        if echo:
            print(c.before.strip().decode())

    def ssh_connect(self):
        print("++ ssh connect")
        self.prompt = "zynq%s>"%(self.ipaddr.split(".")[-1])
        self.logfnam = "ssh_%s.log"%(self.ipaddr.replace(".", "_"))
        self.logfp = open(self.logfnam, "wb")
        cmd = "ssh root@%s"%(self.ipaddr)
        print(cmd)
        self.child = pexpect.spawn(cmd)
        self.child.logfile = self.logfp
        c = self.child
        c.expect("password: ")
        self.sep("root")
        self.sep("uptime")
        print(c.before.decode("utf-8").replace("\r\n", " "))

    def cblw(self):
        """
        self.child.before split into lines, each line split into words
        """
        lines = self.child.before.decode(
            "utf-8").replace("\r", "").strip().split("\n")
        splitlines = [l.split() for l in lines]
        return splitlines

    def fpga_config(self):
        c = self.child
        self.sep("cd /mnt/uzed/")
        # Did NFS mount of /mnt/uzed succeed (at boot time)?
        self.sep("pwd", comment="Check that /mnt/uzed is present")
        wd = c.before.decode(
            "utf-8").replace("\r", "").strip().split("\n")[-1]
        print(wd)
        assert(wd=="/mnt/uzed")
        # Careful: bus i/o during PL config hangs up Microzed
        self.sep("killall server.elf")
        self.sep("killall -9 server.elf")
        # Configure Zynq PL
        binfnam = "uzed_rocstar_*.bin"
        binfnam = os.path.join("/mnt/uzed/", binfnam)
        binfnam = sorted(glob.glob(binfnam))[-1]
        binfnam = os.path.split(binfnam)[-1]
        cmd = "cat %s >> /dev/xdevcfg"%(binfnam)
        self.sep(cmd, echo=True, comment="Configure Zynq PL")
        time.sleep(2)
        # Is Zynq PL "bus" I/O working?
        self.sep("./rd 0002 && ./rd 0001",
                 echo=True, comment="Check Zynq PL bus I/O")
        l = self.cblw()
        assert(l[-2][-1]=="dead")
        assert(l[-1][-1]=="beef")
        # There was more stuff in mrb2_init.py that I've left out for now

    def spartan6_config(self, fpgabinfnam):
        c = self.child
        self.sep("cd /mnt/uzed/")
        # Did NFS mount of /mnt/uzed succeed (at boot time)?
        self.sep("pwd", comment="Check that /mnt/uzed is present")
        wd = c.before.decode(
            "utf-8").replace("\r", "").strip().split("\n")[-1]
        print(wd)
        assert(wd=="/mnt/uzed")
        # Configure Zynq PL
        cmd = "./spartan6_config.elf %s"%(fpgabinfnam)
        self.sep(cmd, echo=True, comment="Configure Spartan6 FPGA")
        time.sleep(2)
        # Is Spartan6 "bus" I/O working?
        self.sep("./v5rd 0013 && ./v5rd 0001",
                 echo=True, comment="Check Spartan6 bus I/O")
        l = self.cblw()
        assert(l[-2][-1]=="6666")
        assert(l[-1][-1]=="beef")
        # There was more stuff in mrb2_init.py that I've left out for now

    def start_weiwei_server(self):
        self.sep("./server.elf >> /dev/null &",
                 echo=True, comment="Start weiwei server")

    def ssh_disconnect(self):
        self.sep("")
        self.child.sendline("exit")
        self.child.expect(" closed.")
        self.child.wait()
        self.child = None
        print("-- ssh disconnected")

    def weiwei_connect(self):
        #boardid = int(self.ipaddr.split(".")[-1])
        boardid = self.ipaddr
        print("connecting to weiwei server on board %s"%(boardid))
        self.m = busio.Mrb(boardid)
        
    # More stuff from mrb2_init.py left out here for now

    def initialize_everything(self, fpgabinfnam):
        f = self  # shortcut to save typing
        alive = f.is_alive()
        if not alive:
            print("this is where poweron() would go")
            assert(f.is_alive())
        f.ssh_connect()
        f.fpga_config()
        f.spartan6_config(fpgabinfnam)
        f.start_weiwei_server()
        f.ssh_disconnect()
        time.sleep(3)

    def wr(self, addr, data):
        "write microzed PL register"
        return self.m.wr(addr, data)

    def v5wr(self, addr, data):
        "write spartan6 register"
        return self.m.v5wr(addr, data)

    def w6(self, addr, data):
        "write spartan6 register"
        return self.m.v5wr(addr, data)

    def v5rd(self, addr):
        "read spartan6 register"
        return self.m.v5rd(addr)
        
    def r6(self, addr):
        "read spartan6 register"
        return self.m.v5rd(addr)
        
    def set_calib_mode(self,
                       calib_mode=True, sine_enable=False, verbose=True):
        if not calib_mode:
            if verbose:
                print("put DRS4 inputs into non-calibration mode")
            self.m.v5wr(0x0006, 0xe)
        elif sine_enable:
            if verbose:
                print("put DRS4 inputs into calibration mode,",
                      "sine waves ON")
            self.m.v5wr(0x0006, 0x30)
        else:
            if verbose:
                print("put DRS4 inputs into calibration mode,",
                      "sine waves OFF")
            self.m.v5wr(0x0006, 0)
        if verbose:
            print("s6:0006 = {:016b}".format(self.r6(0x0006)))

    def setup_waveform_readout(self):
        # this is probably junk, but I copy it for now
        # ---
        # software trigger mode
        tp.setTrig(2)
        # trigger only DRSA, not DRSB (will override this later)
        self.w6(0x0d06, 0x0002)  # DRS_sel_mode=1, DRS_manual_sel=0
        # read out only DRS channel 'n'
        q0d00 = self.r6(0x0d00)
        q0d00 &= 0xff00
        self.drs_which_chnl = 4
        q0d00 |= 1<<self.drs_which_chnl
        self.w6(0x0d00, q0d00)
        readout_ncells = 1023
        self.w6(0x0d01, readout_ncells)

    def drain_dd_fifo(self):
        words = []
        nw = self.r6(0x0d0a)
        while nw!=0:
            cmd = b"df 10d0a 10d0b"
            ret = self.m.b.docmd(cmd)
            w = ret.split()
            assert(w[0] == b"250")
            assert(w[1] == b"DF")
            nwret = int(w[2])
            assert(len(w) == nwret + 3)
            block = [int(ww, 16) for ww in w[3:]]
            words.extend(block)
            nw = self.r6(0x0d0a)
        return words

    def readout_one_trigger(self, verbose=True, whichdrs=0):
        # 0=A 1=B
        assert(whichdrs==0 or whichdrs==1)  

        f = self
        # trigger only DRS 'whichdrs'
        # DRS_sel_mode=1, DRS_manual_sel=whichdrs   
        f.m.v5wr(0x0d06, 0x0002 | whichdrs)

        # issue a fifo_reset
        f.m.v5wr(0x000e, 0x0001)

        ddfnw = f.m.v5rd(0x0d0a)  # dynode_data_fifo.nwords
        ddfq = f.m.v5rd(0x0d0b)
        if verbose:
            print("dynode_data_fifo: nwords={:d} q={:04x}".format(ddfnw, ddfq))

        rfsma_fifone = f.m.v5rd(0xd2a)
        rfsmb_fifone = f.m.v5rd(0xd2b)
        if verbose:
            print("rfsma_fifos_ne={:04x} rfsmb_fifos_ne={:04x}".format(
                rfsma_fifone, rfsmb_fifone))

        trigcount_0 = f.m.v5rd(0x0d26+whichdrs)
        tsgo_0 = f.m.v5rd(0x0d28+whichdrs)

        tp.trig()
        trigcount_1 = f.m.v5rd(0x0d26+whichdrs)
        tsgo_1 = f.m.v5rd(0x0d28+whichdrs)
        if verbose:
            print("number of times DRS has triggered = %d (was %d)"%(
                trigcount_1, trigcount_0))
            print("DRS latest timestamp = %d (was %d)"%(tsgo_1, tsgo_0))
        assert(trigcount_1 == (trigcount_0 + 1) & 0xffff)
        if False:
            # oops, I just broke this with 2019-01-25 evening compile
            assert(tsgo_1 > tsgo_0)

        ddfnw = f.m.v5rd(0x0d0a)  # dynode_data_fifo.nwords
        ddfq = f.m.v5rd(0x0d0b)
        if verbose:
            print("dynode_data_fifo: nwords={:d} q={:04x}".format(ddfnw, ddfq))

        ddfdat = self.drain_dd_fifo()
        if verbose:
            print("len(ddfdat) =", len(ddfdat))
            print("words left over in fifo? : nw =", f.m.v5rd(0x0d0a))
            print("number of read out words : len(ddfdat) =", len(ddfdat))
            print(" ".join([" {:04x}".format(ddfdat[i]) for i in range(13)]))
            print(" ".join(["{:5d}".format(ddfdat[i]) for i in range(13)]))
        assert(ddfdat[0]==0xa5a5)

        if verbose:
            print("len(ddfdat)={:d} ddfdat[1]={:d}".format(
                len(ddfdat), ddfdat[1]))
        assert(len(ddfdat) == ddfdat[1]+3)
        drs4_channel_ena = f.m.v5rd(0x0d00) & 0xff
        assert(ddfdat[2] == drs4_channel_ena)
        assert(drs4_channel_ena == 1<<self.drs_which_chnl)
        tc = ddfdat[3] & 0x3ff  # DRS trigger cell
        readout_whichdrs = ddfdat[3]>>11 & 1
        assert(readout_whichdrs == whichdrs)
        readout_ncells = f.m.v5rd(0x0d01)
        assert(ddfdat[4] == readout_ncells)
        tstamp = ddfdat[5] | ddfdat[6]<<16 | ddfdat[7]<<32
        drs_latest_tstamp = f.m.v5rd(0x0d28+whichdrs)
        if verbose:
            print("trigger_timestamp = {:012x}".format(tstamp))
            print("drs_latest_tstamp = {:04x}".format(drs_latest_tstamp))
        if False:
            # oops: 'timestamp' vs. 'trigger_timestamp' confusion in
            # dynode_path.v
            assert(drs_latest_tstamp == tstamp>>24 & 0xffff)

        wavedat = ddfdat[8:]
        assert(len(wavedat) == readout_ncells)

        t = Event(
            tcell=tc, 
            whichdrs=readout_whichdrs,
            ddfdat=ddfdat,
            wavedat=ddfdat[8:]
        )

        return t        


if __name__=="__main__":
    print("rocstar_init.py starting at", time.ctime())
    # +++ follows Beazley cookbook recipe 13.3
    parser = argparse.ArgumentParser(
        description="initialize rocstar board")
    parser.add_argument(dest="boardid", type=int, nargs="?",
                        help="board to connect " +
                        " (45=Bill, 47=Manny, 192.168.1.n)")
    parser.add_argument("--noinit", action="store_true",
                        help="skip microzed/fpga reset/download")
    parser.add_argument("--fpgabin", nargs="?", default="rocstar.bin",
                        action="store",
                        help=".bin file to send to Spartan6 fpga")
    args = parser.parse_args()
    # ---
    print("connecting to board {}".format(args.boardid))
    f = RocstarInit(args.boardid)
    if not args.noinit:
        f.initialize_everything(fpgabinfnam=args.fpgabin)
    if f.m is None:
        print("connecting to weiwei server")
        f.weiwei_connect()
    print("testing microzed bus read via weiwei server")
    assert(f.m.rd(0x0002)==0xdead)
    assert(f.m.rd(0x0001)==0xbeef)
    print("success!")
    print("++ testing register access to spartan6 FPGA")
    for addr in [0x0000, 0x0001, 0x0002, 0x0008]:
        data = f.m.v5rd(addr)
        print("v5rd[addr=%04x] ==> %04x"%(addr, data))
    assert(f.m.v5rd(0x0001)==0xbeef)
    print("microzed FPGA version:",
          " ".join(["%04x"%f.m.rd(a) for a in [0x0010, 0x0011, 0x0012]]))
    print("spartan6 FPGA version:",
          " ".join(["%04x"%f.m.v5rd(a) for a in [0x0010, 0x0011, 0x0012]]))
    print("connecting 'testpattern' library to board")
    tp.connect(f.m.b.addr)
    print("do 'soft_reset' from Microzed to Spartan6")
    print("count_reset_from_uzed={:04x}".format(f.m.v5rd(0x0019)))
    f.m.wr(0x0019, 0x0001)
    print("count_reset_from_uzed={:04x}".format(f.m.v5rd(0x0019)))
    f.m.wr(0x0019, 0x0000)
    print("count_reset_from_uzed={:04x}".format(f.m.v5rd(0x0019)))
    print("ending at", time.ctime())
    print(30*"=-")
