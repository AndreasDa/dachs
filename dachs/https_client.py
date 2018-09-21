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

import asyncio
import websockets
import ssl
import argparse
import subprocess
import tempfile
import base64
import configparser

SERVER_TIMEOUT = 100

def getXML(exeFileName, infoFileName):
    config = configparser.ConfigParser()
    config.read(infoFileName)
    
    global xmlFile
    
    xmlString = '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n'
    xmlString += "<ExecutionRequest>\n"
    xmlString += '  <Executable encoding="Base64">'
     
    with open(exeFileName,"r+b") as byteFile:
        encodedInformation = base64.b64encode(byteFile.read())
        print(len(encodedInformation))
        
    with open(xmlFile.name, "w") as xmlF:
        xmlF.write(xmlString)
        
    with open(xmlFile.name, "a+b") as xmlF:
        xmlF.write(encodedInformation)
        
    xmlString = ""
    xmlString += "  </Executable>\n"
    xmlString += "  <Target>\n"
    xmlString += "    <Architecture>"
    xmlString += config["Target"]["architecture"]
    xmlString += "</Architecture>\n"

    xmlString += "    <Board>"
    xmlString += config["Target"]["board"]
    xmlString += "</Board>\n"
    xmlString += "  </Target>\n"

    xmlString += "  <RetryMaximum>"
    xmlString += config["Config"]["retryMaximum"]
    xmlString += "</RetryMaximum>\n"

    xmlString += "  <Timeout>"
    xmlString += config["Config"]["timeout"]
    xmlString += "</Timeout>\n"
    
    xmlString += "  <EndString>"
    xmlString += config["Config"]["endString"]
    xmlString += "</EndString>\n"
    
    xmlString += "  <SerialTimeout>"
    xmlString += config["Config"]["serialTimeout"]
    xmlString += "</SerialTimeout>\n"
    xmlString += "</ExecutionRequest>"

    with open(xmlFile.name, "a") as xmlF:
        xmlF.write(xmlString)
    
    return xmlF

@asyncio.coroutine
def on_connect():
    websocket = yield from websockets.connect(
        "wss://" + host + ":" + port, ssl = ssl_context, timeout = SERVER_TIMEOUT)

    try:
        if(args.strip):
            if(args.directory):
                strippedFile = tempfile.NamedTemporaryFile(suffix = ".exe", delete = True, dir = args.directory)
            else:
                strippedFile = tempfile.NamedTemporaryFile(suffix = ".exe", delete = True)
            with open(args.inputExe, "r+b") as inFile:
                exeFileContent = inFile.read()
                lengthBeforeStripping = len(exeFileContent)
            with open(strippedFile.name, "w+b") as stripFile:
                stripFile.write(exeFileContent)
            subprocess.call("strip " + strippedFile.name + " -g -S", shell = True)
            xFile = getXML(strippedFile.name, args.inputInfo)
            with open(strippedFile.name, "r+b") as stripFile:
                fileBinary = stripFile.read()
                lengthAfterStripping = len(fileBinary)
                print("Before stripping: " + str(lengthBeforeStripping) + "\nAfter stripping: " + str(lengthAfterStripping) + "\n\n")
        else:
            xFile = getXML(args.inputExe, args.inputInfo)
        
        with open(xFile.name, "r+b") as fileToServer:
            fileBinary = fileToServer.read()
            yield from websocket.send(fileBinary)
        
        xFile.close()
        
        output = yield from websocket.recv()
        
        if outFile == "STDOUT":
            print(output)
        else:
            with open(outFile,"w") as outputFile:
                outputFile.write(output)
            
        print("received file")
        
    finally:
        yield from websocket.close()
        print("connection closed")

if __name__ == "__main__":
    #command line params
    parser = argparse.ArgumentParser()
    parser.add_argument("inputExe", help = "Input file (executable)")
    parser.add_argument("inputInfo", help = "Input file (information in .ini file)")
    parser.add_argument("--strip","-s", help = "Enable strip", action="store_true")
    parser.add_argument("--cert", "-c", help = "Used certificate")
    parser.add_argument("--output", "-o", help = "Output file, default is STDOUT") 
    parser.add_argument("--host", help = "Hostname, default is localhost")
    parser.add_argument("--port", "-p", help = "Portnumber, default is 4443", type = int)
    parser.add_argument("--directory", "-d", help = "Directory the tempfile is stored in, default is ./")
    args = parser.parse_args()
    
    
    cert = "localhost.pem"
    outFile = "STDOUT"
    host = "localhost"
    port = "4443"
    if args.output:
        outFile = args.output
        
    if args.host:
        host = str(args.host)
    
    if args.port:
        port = str(args.port)
        
    if args.cert:
        cert = str(args.cert)
        
        
    if(args.directory):
        xmlFile = tempfile.NamedTemporaryFile(suffix = ".xml", delete = True, dir = args.directory)
    else:
        xmlFile = tempfile.NamedTemporaryFile(suffix = ".xml", delete = True)
    
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
    ssl_context.load_cert_chain(cert)
    ssl_context.verify_mode = ssl.CERT_NONE
    asyncio.get_event_loop().run_until_complete(on_connect())
