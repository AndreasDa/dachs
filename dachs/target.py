# SPDX-License-Identifier: BSD-2-Clause
#
# Copyright (c) 2018 Andreas Dachsberger.  All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR AND CONTRIBUTORS ``AS IS'' AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
# OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGE.

import abc
import configparser
import functools
import queue
import re
import serial
import subprocess
import tempfile
import tftpy
import threading
import time

import https_server

#raddress and rport are just syntactically needed
def _getFile(index, fileName, raddress, rport):
    print("using dyn_file_func")
    print(fileName)
    print("Trying to send data")
    try:
        imgFile = TQMa7DHandler.IMG_FILE_QUEUE[index].get_nowait()
        TQMa7DHandler.READ_THREAD_QUEUE_IN[index].put_nowait("Start")
        return open(imgFile.name,"r+b")
    except queue.Empty:
        return None

   
class transmitThread(threading.Thread):
    def __init__(self, tftp, tftpTimeout, listenport):
        threading.Thread.__init__(self)
        self.tftp = tftp
        self.stopRequested = False
        self.tftpTimeout = tftpTimeout
        self.listenport = listenport
        
    def run(self):
        while True:
            print("starting tftp server")
            self.tftp.listen(listenport = self.listenport, timeout = self.tftpTimeout)
        
        
class readThread(threading.Thread):
    END_STRING = []
    SERIAL_READ_TIMEOUT = None
    
    def __init__(self, clientConfigFileName, index):
        threading.Thread.__init__(self)
        self.serDev = serial.Serial(port = "/dev/ttyUSB0", baudrate = 115200, timeout = self.SERIAL_READ_TIMEOUT)
        config = configparser.ConfigParser()
        config.read(clientConfigFileName)
        if index >= len(readThread.END_STRING):
            if index == len(readThread.END_STRING):
                readThread.END_STRING.append(re.escape(config["Config"]["endString"]))
            else:
                raise https_server.FatalException("END_STRING has not the right length")
        readThread.SERIAL_READ_TIMEOUT = config["Config"].getint("serialTimeout")
        self.stopRequested = False
        self.index = index
        
    def run(self):
        print("serial thread started")
        while True:
            currentOutput = self.serDev.read(100).decode(errors = "ignore")

            try:
                message = TQMa7DHandler.READ_THREAD_QUEUE_IN[self.index].get_nowait()
                if message == "Start":
                    print("Started now")
                    while not self.stopRequested and re.search(self.END_STRING[self.index], currentOutput) == None:
                        currentOutput += self.serDev.read(100).decode(errors = "ignore")
                        print(currentOutput)
                        print()
                    
                    if self.stopRequested:
                        print("in stop stopRequested")
                        self.stopRequested = False
                        currentOutput = None
                        self.serDev.reset_input_buffer()
                    else:    
                        endMatch = re.search(self.END_STRING[self.index], currentOutput)
                        output = currentOutput[:endMatch.end()]
                        TQMa7DHandler.READ_THREAD_QUEUE_OUT[self.index].put_nowait(output)
                    
                    
                else:
                    raise https_server.FatalException("readThread gone wrong")
            except queue.Empty:
                continue
            
        raise https_server.FatalException("Serdev is closed, should not happen")
        self.serDev.close() 
    
class FileProcessor(abc.ABC):
    @abc.abstractmethod
    def process(self):
        pass
    
class TQMa7DProcessor(FileProcessor):
    def __init__(self, testFile, pathToDir):
        self.testFile = testFile
        self.pathToDir = pathToDir
        
    def process(self):
        binFile = tempfile.NamedTemporaryFile(suffix = ".bin", delete = True, dir = self.pathToDir)
        gzFile = tempfile.NamedTemporaryFile(suffix = ".bin.gz", delete = True, dir = self.pathToDir)
        imgFile = tempfile.NamedTemporaryFile(suffix = ".img", delete = True, dir = self.pathToDir)
        
        subprocess.call("arm-rtems5-objcopy -O binary " + self.testFile.name + " " + binFile.name, shell = True, timeout = 10)
        subprocess.call("gzip -9 -f -c " +  binFile.name + " > " + gzFile.name, shell = True, timeout = 10)
        subprocess.call("mkimage -A arm -O linux -T kernel -a 0x80200000 -e 0x80200000 -n RTEMS -d " + gzFile.name + " " + imgFile.name, shell = True, timeout = 10)
        
        self.testFile.close()
        binFile.close()
        gzFile.close()
        
        return imgFile
    
    
class TQMa7DHandler(https_server.TargetHandler):
    IMG_FILE_QUEUE = []
    TFTP_SERVER_THREAD = []
    READ_THREAD = []
    READ_THREAD_QUEUE_IN = []
    READ_THREAD_QUEUE_OUT = []
    
    def __init__(self, testFile, clientConfigFileName, index, targetConfig, sectionName):
        self.testFile = testFile
        self.targetConfig = targetConfig
        self.sectionName = sectionName
        self.timeout = int(self.targetConfig.getValue(self.sectionName, "transmitTimeout"))
        self.fileProcessor = TQMa7DProcessor(testFile, self.targetConfig.getValue("httpsServer", "pathToDir"))
        self.index = index
        self.listenport = int(self.targetConfig.getValue(self.sectionName, "listenport"))
        
        config = configparser.ConfigParser()
        config.read(clientConfigFileName)
        self.clientConfigFileName = clientConfigFileName
        self.readTimeout = config["Config"].getint("timeout")
            
        #"or not" maybe not necessary
        if self.index >= len(TQMa7DHandler.READ_THREAD) or not TQMa7DHandler.READ_THREAD[self.index]:
            self.readThread = readThread(clientConfigFileName, self.index)
            
            if len(TQMa7DHandler.READ_THREAD) == index:
                TQMa7DHandler.READ_THREAD.append(self.readThread)
            else:
                raise https_server.FatalException("readThread[] has not the right length")
        else:
            self.readThread = TQMa7DHandler.READ_THREAD[index]
            
        if self.index >= len(TQMa7DHandler.READ_THREAD_QUEUE_IN):
            if self.index == len(TQMa7DHandler.READ_THREAD_QUEUE_IN):
                TQMa7DHandler.READ_THREAD_QUEUE_IN.append(queue.Queue())
            else:
                raise https_server.FatalException("READ_THREAD_QUEUE_IN has not the right length")
            
        if self.index >= len(TQMa7DHandler.IMG_FILE_QUEUE):
            if self.index == len(TQMa7DHandler.IMG_FILE_QUEUE):
                TQMa7DHandler.IMG_FILE_QUEUE.append(queue.Queue())
            else:
                raise https_server.FatalException("IMG_FILE_QUEUE has not the right length")
            
        if self.index >= len(TQMa7DHandler.READ_THREAD_QUEUE_OUT):
            if self.index == len(TQMa7DHandler.READ_THREAD_QUEUE_OUT):
                TQMa7DHandler.READ_THREAD_QUEUE_OUT.append(queue.Queue())
            else:
                raise https_server.FatalException("READ_THREAD_QUEUE_OUT has not the right length")
        
    def run(self):
        if self.index >= len(TQMa7DHandler.TFTP_SERVER_THREAD):
            if self.index == len(TQMa7DHandler.TFTP_SERVER_THREAD):
                tftp = tftpy.TftpServer(tftproot = None, dyn_file_func = functools.partial(_getFile, self.index))
                self.transmitThread = transmitThread(tftp, self.timeout, self.listenport)
                TQMa7DHandler.TFTP_SERVER_THREAD.append(self.transmitThread)
                print("transmitThread not yet alive")
                self.transmitThread.start()
            else:
                raise https_server.FatalException("TFTP_SERVER_THREAD has not the right length")
        else:
            self.transmitThread = TQMa7DHandler.TFTP_SERVER_THREAD[self.index]
        if not self.readThread.is_alive():
            print("readThread not yet alive")
            self.readThread.start()
            
        TQMa7DHandler.IMG_FILE_QUEUE[self.index].put_nowait(self.processedFile)
        
        print("starting to wait for readThread")
        output = None
        try:
            output = TQMa7DHandler.READ_THREAD_QUEUE_OUT[self.index].get(timeout = self.readTimeout)
        except queue.Empty:
            print("unsuccessfully generated output")
            #pass
        print("finished waiting for readThread or timeout")
        return output
        
    def processFile(self):
        self.processedFile = self.fileProcessor.process()
        
    def doExit(self):
        print("In TQMa7DHandler doExit")
        self.processedFile.close()
        print("TQMa7DHandler exit")
        
    def handleTimeout(self):
        print("handling timeout")
        self.readThread.stopRequested = True
        print("handled timeout")
               
               
class DummyHandler(https_server.TargetHandler):
    def __init__(self, testFile, clientConfigFileName, index, targetConfig, sectionName):
        print("dummy with index: " + str(index))
        self.index = index
        self.sectionName = sectionName
        self.targetConfig = targetConfig
        print(str(self.index) + " with sectionName: " + self.sectionName)
        
    def handleTimeout(self):
        print("dummy " + str(self.index) + " Handle Timeout")
    
    def doExit(self):
        print("dummy "+ str(self.index) + " do Exit")
        
    def run(self):
        print("dummy "+ str(self.index) + " running")
        time.sleep(int(self.targetConfig.getValue(self.sectionName, "runTimeFirstHalf")))
        print("dummy " + str(self.index) + " finished first half")
        time.sleep(int(self.targetConfig.getValue(self.sectionName, "runTimeSecondHalf")))
        print("dummy " + str(self.index) + " finished running")
        return "success"

    def processFile(self):
        print("dummy " + str(self.index) + " processing file")
        
                 

        
        
