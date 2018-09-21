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

import datetime
import pexpect
import threading
import time

import https_server

class primitiveTimerThread(threading.Thread):
    def __init__(self, time, switch, doseID):
        threading.Thread.__init__(self)
        self.time = time
        self.stopRequested = False
        self.mySwitch = switch
        self.doseID = doseID
        
    def run(self):
        for i in range(self.time):
            if self.stopRequested:
                break
            #print(str(self.time - i))
            time.sleep(1)
        
        if not self.stopRequested:
            self.mySwitch.switchOff(doseID)


class Netio230BSwitch(https_server.Switch):
    def __init__(self, sectionName):
        self.restarts = [[],[],[],[]]
        self.connection = None
        self.primitiveTimer = [None, None, None, None]
        self.name = sectionName
        self.myLock = threading.Lock()
        
    def configure(self, targetConfiguration):
        self.ipAddress = targetConfiguration.getValue(self.name, "ipAddress")
        self.port = int(targetConfiguration.getValue(self.name, "port"))
        self.maxNumRestarts = int(targetConfiguration.getValue(self.name, "maxNumRestarts"))
        self.timeoutAfterTest = int(targetConfiguration.getValue(self.name, "timer"))
        self.timeForRestarts = int(targetConfiguration.getValue(self.name, "timeForRestarts"))
    
    def _spawnConnection(self):
        with self.myLock:
            if (not self.connection) or (not self.connection.isalive()):
                self.connection = pexpect.spawn("telnet " + self.ipAddress+ " " + str(self.port))
                self.connection.expect(r"100 HELLO")
                self.connection.send("login admin admin\n")
                self.connection.expect(r"250 OK")
            
    def switchOn(self, doseID):
        self._spawnConnection()
        with self.myLock:
            if doseID == 1:
                self.connection.send("port list 1uuu\n")
            elif doseID == 2:
                self.connection.send("port list u1uu\n")
            elif doseID == 3:
                self.connection.send("port list uu1u\n")
            elif doseID == 4:
                self.connection.send("port list uuu1\n")
            else:
                raise https_server.FatalException("This dose ID does not exist")
            
            self.connection.expect(r"250 OK")
        print("Successfully switched on dose: " + str(doseID))
    
    def switchOff(self, doseID):
        self._spawnConnection()
        with self.myLock:
            if doseID == 1:
                self.connection.send("port list 0uuu\n")
            elif doseID == 2:
                self.connection.send("port list u0uu\n")
            elif doseID == 3:
                self.connection.send("port list uu0u\n")
            elif doseID == 4:
                self.connection.send("port list uuu0\n")
            else:
                raise https_server.FatalException("This dose ID does not exist")
            
            self.connection.expect(r"250 OK")
        print("Successfully switched off dose: " + str(doseID))
    
    def restart(self, doseID):
        currentTime = datetime.datetime.now()
        removeList = []
        for t in self.restarts[doseID]:
            if (t + datetime.timedelta(hours = 1)) < currentTime:
                removeList.append(t)
       
        for removeItem in removeList:
            self.restarts[doseID].remove(removeItem)
        
        if len(self.restarts[doseID]) < self.maxNumRestarts:
            self.switchOff(doseID)
            time.sleep(self.timeForRestarts)
            self.switchOn(doseID)
            self.restarts[doseID].append(currentTime)
        else:
            raise https_server.FatalException("Cannot restart, might damage device!\nNumber of restarts in the last hour exceeds number of restarts allowed")
        
    def startTimer(self, doseID):
        if not self.primitiveTimer[doseID]:
            self.primitiveTimer[doseID] = primitiveTimerThread(self.timeoutAfterTest, self, doseID)
            self.primitiveTimer[doseID].start()
        
    def stopTimer(self, doseID):
        if self.primitiveTimer[doseID]:
            self.primitiveTimer[doseID].stopRequested = True
            self.primitiveTimer[doseID] = None
            
            
class DummySwitch(https_server.Switch):
    def __init__(self, sectionName):
        print("did init dummySwitch")
        
    def configure(self, targetConfiguration):  
        print("did configure dummySwitch")
        
    def switchOn(self, doseID):
        print("did switchOn dummySwitch, doseID: " + str(doseID))
        
    def switchOff(self, doseID):  
        print("did switchOff dummySwitch, doseID: " + str(doseID))
        
    def restart(self, doseID):
        print("did restart dummySwitch, doseID: " + str(doseID))
        
    def startTimer(self, doseID):
        print("did startTimer dummySwitch, doseID: " + str(doseID))
        
    def stopTimer(self, doseID):
        print("did stopTimer dummySwitch, doseID: " + str(doseID))
