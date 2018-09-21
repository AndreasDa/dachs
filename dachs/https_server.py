#!/usr/bin/env python3

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
import argparse
import asyncio
import base64
import concurrent.futures
import configparser
import functools
import importlib
import libxml2
import ssl
import sys
import tempfile
import threading
import websockets

CLIENT_HANDLER = None

class StateMachine:
    IDLE = 0
    RECEIVED_FILE = 1
    DEVICE_SELECTED = 2
    FILE_PROCESSED = 3
    TEST_RUNNING = 4
    OUTPUT_RECEIVED = 5
    DEVICE_NOT_RESPONDING = 6
    FINISHED = 7
    RECONFIGURE_DEVICE = 8
    ERROR_STATE = 9
    
    def __init__(self, targetConfig, deviceHandler, maxNumTimeouts, switch, powerPort):
        self.state = self.DEVICE_SELECTED
        self.inEndState = False
        self.numTimeouts = 0 
        self.targetConfig = targetConfig
        self.switch = switch
        self.powerPort = powerPort
        self.deviceHandler = deviceHandler
        self.maxNumTimeouts = maxNumTimeouts
        
    def run(self):
        while not self.inEndState:
            self._handleState()
            
        if self.wasSuccessfull:
            return self.output
        else:
            return None
        
    def _handleState(self):
        if self.state == self.IDLE:
            raise StateMachineException("Error, handleState(IDLE)")
        elif self.state == self.RECEIVED_FILE:
            raise StateMachineException("Error handleState(RECEIVED_FILE)")
        elif self.state == self.DEVICE_SELECTED:
            self._processFile()
        elif self.state == self.FILE_PROCESSED:
            self._transmitToDevice()
        elif self.state == self.OUTPUT_RECEIVED:
            self._sendOutputToClient(True)
        elif self.state == self.DEVICE_NOT_RESPONDING:
            self._reconfigureDevice()
        elif self.state == self.FINISHED:
            self._doOnExit()
        elif self.state == self.RECONFIGURE_DEVICE:
            self._reconfigureDevice()
        elif self.state == self.ERROR_STATE:
            raise StateMachinException("Errorstate reached, something went wrong!")
        else:
            raise StateMachineException("Error, unknown state")
        
    def _processFile(self):
        self.deviceHandler.processFile()
        self.state = self.FILE_PROCESSED
        
    def _transmitToDevice(self):
        self.output = self.deviceHandler.run()
        #run responds None in case the device timed out more times than allowed
        if self.output:
            self.state = self.OUTPUT_RECEIVED
        else:
            self.state = self.DEVICE_NOT_RESPONDING
    
    def _sendOutputToClient(self, wasSuccessfull):
        self.wasSuccessfull = True
        self.state = self.FINISHED
        
    def _reconfigureDevice(self):
        self.numTimeouts += 1
        if self.numTimeouts > self.maxNumTimeouts:
            self.wasSuccessfull = False
            self.state = self.FINISHED
            self.deviceHandler.handleTimeout()
            self.switch.restart(self.powerPort)
        else:
            self.switch.restart(self.powerPort)
            self.deviceHandler.handleTimeout()
            self.state = self.FILE_PROCESSED
        
    def _doOnExit(self):
        self.deviceHandler.doExit()
        self.inEndState = True
        #if handleState is invoked another time, error is raised
        self.state = self.ERROR_STATE
        
        
            
class StateMachineException(Exception):
    def __init__(self, *args, **kwargs):
        Exception.__init__(self, *args, **kwargs)
        

class FatalException(Exception):
    def __init__(self, *args, **kwargs):
        Exception.__init__(self, *args, **kwargs)
        

class TargetHandler(abc.ABC):
    @abc.abstractmethod
    def __init__(self, testFile, clientConfigFileName, index, targetConfig, sectionName):
        pass
    
    @abc.abstractmethod
    def processFile(self):
        pass
    
    @abc.abstractmethod
    def run(self):
        pass
        
    @abc.abstractmethod
    def doExit(self):
        pass
    
    @abc.abstractmethod
    def handleTimeout(self):
        pass
    
class Switch(abc.ABC):
    @abc.abstractmethod
    def __init__(self, sectionName):
        pass
    
    @abc.abstractmethod
    def restart(self, doseID):
        pass
    
    @abc.abstractmethod
    def switchOff(self, doseID):
        pass
    
    @abc.abstractmethod
    def switchOn(self, doseID):
        pass
    
    @abc.abstractmethod
    def startTimer(self, doseID):
        pass
    
    @abc.abstractmethod
    def stopTimer(self, doseID):
        pass  
    
    @abc.abstractmethod
    def configure(self, cfgFile):
        pass
    
    
class TargetHandlerGroup():
    def __init__(self, targetConfig, handlerClassName):
        self.sectionNames = []
        self.lockList = []
        self.handlerClassName = handlerClassName
        self.targetConfig = targetConfig
        self.sema = None
        
    def addTargetHandler(self, sectionName):
        self.lockList.append(threading.Lock())
        self.sectionNames.append(sectionName)
        
    def handle(self, fileInput, clientConfigFile):
        if self.sema == None:
            self.sema = threading.BoundedSemaphore(len(self.lockList))
        
        print("now: acquire")
        self.sema.acquire()
        
        boardID = -1
        for i in range(len(self.lockList)):
            if self.lockList[i].acquire(blocking = False):
                boardID = i
                break
            
        if boardID == -1:
            raise IndexError("boardID out of range")
        
        config = configparser.ConfigParser()
        config.read(clientConfigFile)
        
        switchName = self.targetConfig.getValue(self.sectionNames[boardID], "switch")
        switch = self.targetConfig.getSwitch(switchName)
        powerPort = int(self.targetConfig.getValue(self.sectionNames[boardID], "powerport"))
        
        deviceHandler = self.handlerClassName(fileInput, clientConfigFile, boardID, self.targetConfig, self.sectionNames[boardID])
        myStateMachine = StateMachine(self.targetConfig, deviceHandler, config["Config"].getint("retryMaximum"), switch, powerPort)
        
        switch.stopTimer(powerPort)
        switch.switchOn(powerPort)
        
        try:
            print("started the test")
            output = myStateMachine.run()
        finally:
            self.lockList[boardID].release()
            self.sema.release()
            switch.startTimer(powerPort)
            
        print("release")
        
        if output:
            return output
        else:
            return "The test timed out too often"
    
class TargetConfiguration:
    def __init__(self, cfgFileName):
        self.cfgFileName = cfgFileName
        self.targetHandlerGroupDict = self._generateTargetHandlerGroupDict()
        self.switches = None
        
    def getValue(self, section, attributeName):
        cfg = configparser.ConfigParser()
        cfg.read(self.cfgFileName)
        return cfg[section][attributeName]
            
    def _generateTargetHandlerGroupDict(self):
        targetString = self.getValue("httpsServer", "targets")
        targets = targetString.split(",")
        
        targetDict = {}
        for t in targets:
            t = t.strip(" ")
            board = self.getValue(t, "board")
            arch = self.getValue(t, "architecture")
            try:
                targetHandlerGroup = targetDict[(arch, board)]
            except KeyError:
                moduleClassString = self.getValue(t, "target")
                moduleClassList = moduleClassString.split(".")
                module = importlib.import_module(moduleClassList[0])
                className = getattr(module, moduleClassList[1])
                print(str(t) + " : (" + str(arch) + ", " + str(board) + ") = " + str(TargetHandlerGroup(self, className))) 
                targetDict[(arch, board)] = TargetHandlerGroup(self, className)
                targetHandlerGroup = targetDict[(arch, board)]
                
            targetHandlerGroup.addTargetHandler(t)
            
        return targetDict
        
    def getTargetHandlerGroup(self, key):
        return self.targetHandlerGroupDict[key]
        
    def setSwitches(self, switches):
        self.switches = switches
        
    def getSwitch(self, switchName):
        return self.switches[switchName]
   
    
class ClientHandlerException(Exception):
    def __init__(self, *args, **kwargs):
        Exception.__init__(self, *args, **kwargs)
    
class ClientHandler:
    def __init__(self, targetConfig):
        self.targetConfig = targetConfig
        self.counter = 0
        
    def handleClient(self, fileInput, clientConfigFile):
        config = configparser.ConfigParser()
        config.read(clientConfigFile)
        
        try:
            thGroup = self.targetConfig.getTargetHandlerGroup((config["Target"]["architecture"], config["Target"]["board"]))
        except KeyError:
            raise ClientHandlerException("This (architecture, board) tuple does not exist")
                
        return thGroup.handle(fileInput, clientConfigFile)
            
            
def parseXML(xmlFile, pathForTmp):
    doc = libxml2.parseFile(xmlFile.name)
    context = doc.xpathNewContext()
    
    exeMap = map(libxml2.xmlNode.getContent, context.xpathEval("/ExecutionRequest/Executable"))
    architectureMap = map(libxml2.xmlNode.getContent, context.xpathEval("/ExecutionRequest/Target/Architecture"))
    boardMap = map(libxml2.xmlNode.getContent, context.xpathEval("/ExecutionRequest/Target/Board"))
    retryMaximumMap = map(libxml2.xmlNode.getContent, context.xpathEval("/ExecutionRequest/RetryMaximum"))
    timeoutMap = map(libxml2.xmlNode.getContent, context.xpathEval("/ExecutionRequest/Timeout"))
    endStringMap = map(libxml2.xmlNode.getContent, context.xpathEval("/ExecutionRequest/EndString"))
    serialTimeoutMap = map(libxml2.xmlNode.getContent, context.xpathEval("/ExecutionRequest/SerialTimeout"))
    
    exeFile = tempfile.NamedTemporaryFile(suffix = ".exe", delete = True, dir = pathForTmp)
    cfgFile = tempfile.NamedTemporaryFile(suffix = ".ini", delete = True, dir = pathForTmp)
    
    with open(exeFile.name, "w+b") as exeF:
        exeF.write(base64.b64decode(str(list(exeMap))))
                   
    with open(cfgFile.name, "w") as cfgF:
        cfgF.write("[Target]\narchitecture=")
        cfgF.write(str(list(architectureMap)[0]))
        cfgF.write("\nboard=")
        cfgF.write(str(list(boardMap)[0]))
        cfgF.write("\n[Config]\nretryMaximum=")
        cfgF.write(str(list(retryMaximumMap)[0]))
        cfgF.write("\ntimeout=")
        cfgF.write(str(list(timeoutMap)[0]))
        cfgF.write("\nendString=")
        cfgF.write(str(list(endStringMap)[0]))
        cfgF.write("\nserialTimeout=")
        cfgF.write(str(list(serialTimeoutMap)[0]))
        cfgF.write("\n")
        
    return (exeFile, cfgFile)

def initializeSwitch(targetConfig):
    switchString = targetConfig.getValue("httpsServer", "switches")
    switchList = switchString.split(",")
    
    switchDict = {}
    for s in switchList:
        s  = s.strip()
        switchHandlerString = targetConfig.getValue(s, "switchHandler")
        moduleClass = switchHandlerString.split(".")
        module = importlib.import_module(moduleClass[0])
        className = getattr(module, moduleClass[1])
        switchObject = className(s)
        switchObject.configure(targetConfig)
        switchDict[s] = switchObject 
    return switchDict
    
    
@asyncio.coroutine 
def handleClient(websocket, path):
    
    print("Starting")
    inputStream = yield from websocket.recv()
    print("received file")
    
    global CLIENT_HANDLER
    global TARGET_CONFIG
    
    pathToDir = TARGET_CONFIG.getValue("httpsServer", "pathToDir")
    
    inputTmpFile = tempfile.NamedTemporaryFile(suffix = ".xml", delete = True, dir = pathToDir)
    with open(inputTmpFile.name, "w+b") as iFile:
        iFile.write(inputStream)
    
    resultList = parseXML(inputTmpFile, pathToDir)
    executable = resultList[0]
    clientCfg = resultList[1]
    
    executor = concurrent.futures.ThreadPoolExecutor()
    output = None
    

    try:
        #add param for configFileName, input, let's see if syntactically correct
        output = yield from asyncio.get_event_loop().run_in_executor(executor, functools.partial(CLIENT_HANDLER.handleClient, executable, clientCfg.name))
    except FatalException as CIException:
        print(type(CIException))
        print(CIException)
        output = str(type(CIException)) + "\n" + str(CIException) + "\n\nFatal Exception\nSwitching off device\nDisable server"
        yield from websocket.send(str(output))
        print("Exiting")
        #TODO switch off all switches
        #whether everything should be switched off needs consideration
        #should failure of one boards cause everything to shut down?
        print("Unnexcpected failure, shutting down server. Currently, no switches are shut down. Consider changing this implementation.")
        sys.exit(1)
    except StateMachineException as SME:
        print(type(SME))
        print(SME)
        output = str(type(SME)) + "\n" + str(SME) + "\n\n\nStatemachine failed"
    except ClientHandlerException as CHE:
        print(type(CHE))
        print(CHE)
        output = str(type(CHE)) + "\n" + str(CHE) + "\nrequest terminated"
    finally:
        executable.close()
        clientCfg.close()
    
    yield from websocket.send(str(output))
    
    print("\n\nFinished handling client!\n\n")
    
    
if __name__ == "__main__":
    #command line args:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cfg", "-c", help = "Name of config file, default is serverConfig.ini")
    args = parser.parse_args()
    
    configFileName = "config/serverConfig.ini"
    if args.cfg:
        configFileName = args.cfg
        
    config = configparser.ConfigParser()
    config.read(configFileName)
    
    TARGET_CONFIG = TargetConfiguration(configFileName)
    
    switches = initializeSwitch(TARGET_CONFIG)
    TARGET_CONFIG.setSwitches(switches)
    
    CLIENT_HANDLER = ClientHandler(TARGET_CONFIG)
    
    certificate = TARGET_CONFIG.getValue("httpsServer", "certName")
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
    ssl_context.load_cert_chain(certificate)
    
    myPort = int(TARGET_CONFIG.getValue("httpsServer", "port"))
    maxSize = int(TARGET_CONFIG.getValue("httpsServer","maxSize"))
    serverTimeout = int(TARGET_CONFIG.getValue("httpsServer", "httpsServerTimeout"))
    start_server = websockets.serve(handleClient, port = myPort, ssl = ssl_context, max_size = maxSize, timeout = serverTimeout)

    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()
    


