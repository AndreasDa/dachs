[comment]: #  (SPDX-License-Identifier: CC-BY-SA-4.0)
None as tftproot?)

# dachs- a pure python Test Server

<img src="https://raw.githubusercontent.com/AndreasDa/dachs/master/images/badger.png" width="640">

## Overview

The dachs Test Server is a tool that provides an interface to run any 
executable on supported hardware remotely. Once the server is started, clients 
can connect to the server over https and send execution requests. The server 
distributes the requests to the available hardware and sends the output back to 
the client.

## Server

#### Overview

The server needs a configuration file to set up the available hardware 
correctly. The option `--cfg` is used to specify the name of said file. If no 
option is given, the default configuration, the file *serverConfig.ini* is 
used.

A certificate is required for the server. A good tutorial on how to generate self
signed certificates with openssl can be found here (only the .pem file is needed):
[tutorial](http://pankajmalhotra.com/Simple-HTTPS-Server-In-Python-Using-Self-Signed-Certs)

#### Configuration

The content of the file is required to have the following structure:

```INI
[httpsServer]
certName=
port=
maxSize=
pathToDir=
httpsServerTimeout=
targets= t1, t2...
switches= s1, s2...

[t1]
board=
architecture=
target=
switch=
--additional configuration options--

[t2]
...

[s1]
switchHandler=
maxNumRestarts=
--additional configuration options--

[s2]
...
```

In the **httpsServer** section, the *certName* specifies the certificate used 
for authentication in the https protocol. It can specify an absolute path or a 
path relative to the server's *pathToDir* value. The pathToDir value also 
determines where temporary files may be generated on the host machine. If such 
files are generated, it is ensured that no existing files in the directory are 
deleted. The *port* attribute sets the server's port to listen to, this port 
might need to be unlocked by the firewall. The *httpsServerTimeout* establishes 
a timeout for the server socket.

The value of the *targets* key is a list of all devices that are available. 
In the configuration file, there has to be one section per device, named 
exactly like the name given in this list.

The value of the *switches* key is a list of all switches for the available 
boards. These devices govern the boards power supply. For each device in this 
list there must be one section named accordingly in the configuration file. The 
sections for the targets and the switches can be placed in any order.

In every target section, e.g. **t1**, there must be the keys *board*, 
*architecture*, *target*, and *switch*. The *board* is the name of 
the target device, the *architecture* is the name of the matching ISA. 
*target* is the class handling this device. It has to be given in the 
form **moduleName.className**. *switch* is the name of the switch for 
this board. This value is required to match up exactly with one of the names 
of a switch section. Any number of additional configuration options is 
allowed in the device sections, the required options only establish a minimum 
of information.

In every switch section, e.g. **s1**, there must be the keys *switchHandler*, 
and *maxNumRestarts*.The *switchHandler* is the class handling the specific 
switch. It has to be given in the form **moduleName.className**. The 
*maxNumRestarts* sets the maximum of restarts for this device in one hour. This 
is a security feature to prevent the device from damage because of too many 
restarts. Any number of additional configuration options is allowed in the 
switch sections, the required options only establish a minimum of 
information.


    
    
## Client

#### Overview

The client is used to send execution requests to the server. The client 
requires a test executable, a suitably formated configuration file and supports 
multiple command line arguments.

#### Command line arguments

Usage:

```
httpsClient.py [--help] [--strip] [--cert CERT] [--output OUTPUT]
            [--host HOST] [--port PORT] [--directory DIR]
            inputExe inputInfo
```

| Syntax                           | Meaning                                   |
| ------                           | -------                                   |
| [\-\-help]/ [-h]                 | show help message and exit                |
| [\-\-strip]/ [-s]                | Enable stripping off debug information    | 
| [\-\-cert CERT]/ [-c CERT]       | the used certificate for the server       |
| [\-\-output OUTPUT]/ [-o OUTPUT] | output file, default is STDOUT            |
| [\-\-host HOST]                  | host ip address, default is localhost     |
| [\-\-port PORT]/ [-p PORT]       | portnumber, default is 4443               |
| [\-\-directory DIR]/ [-d DIR]    | directory the tempfiles are stored in     |
| inputExe                         | the executable to execute on the target   |
| inputInfo                        | the configuration file for the execution  |

It is highly recommended to use the `--strip / -s` option, as it greatly 
reduces the amount of data having to be sent. 
It is ensured that no files in the directory specified by `--directory / -d` 
get deleted.
The two files *inputExe* and *inputInfo* are two mandatory, positional 
arguments. *inputExe* is the executable. *inputInfo* is the configuration file 
for the execution. It must be in the .ini format and have the structure 
specified by the following section.

#### Configuration

The content of the file is required to have the following structure:

```INI
[Target]
architecture=
board=

[Config]
retryMaximum=
timeout=
endString=
serialTimeout=
```

In the **Target** section, the *board* and the *architecture* properties 
describe on which hardware the executable is supposed to run. 

In the **Config** section, the *retryMaximum* sets the maximum number of 
timeouts the executable is allowed to face before giving up and returning an 
error message to the client. If a timeout occurs, the server will try running 
the executable again if the number of timeouts does not exceed the maximum 
number of timeouts.The *timeout* determines how long the execution is allowed 
to take for this executable. After a timeout, a retry is initiated. The 
*endString* property of the client configuration specifies the String the 
server uses to determine when the execution is finished. The *serialTimeout* 
sets the timeout for one read cycle for the interface of the device. The 
recommended value is 1 (second). This value should not be changed, because 
execution time may increase immensely.

## Supported Hardware

Currently, only the TQMa7D board with arm architecture is supported. new 
hardware can be added by coding a Target class, subclass of the abstract 
class TargetHandler, and a Switch class, subclass of the abstract class 
Switch. These classes must implement all methods specified by the abstract 
classes with the exact API as specified.

#### TargetHandler

The TargetHandler must provide the following methods:

* \_\_init__(self, testFile, clientCfgFileName, index, targetCfg, sectionName)
* processFile(self)
* run(self)
* doExit(self)
* handleTimeout(self)

##### \_\_init__(self, testFile, clientCfgFileName, index, targetCfg, sectionName)
*testFile* is the executable, *clientCfgFileName* is the name of the configuration
file sent by the client. The *index* specifies the index of the device in the set 
of devices of the same type as this (where both *architecture* and *board* values
are equal). The *targetCfg* has access to all the data from the server's config file.
The deviceHandler is supposed to retrieve all necessary data from the targetCfg.
The *sectionName* specifies the name of the device, so that the deviceHandler is
able to extract the according information from the targetCfg

##### processFile(self)
Process the testFile so that it can be transmitted to the target and executed.

##### run(self)
Transmit the processed file to the target and start execution.
Return the output of the target, or None if a timeout occurs

##### doExit(self)
Do follow up operations that are needed after the execution, e.g. close open 
files, delete data that is no longer needed, etc.

##### handleTimeout(self)
Do follow up operations that are needed if a timeout occurs, e.g. close open 
files, stop reading the output of the device etc.

#### Switch

The Switch must provide the following methods:

* \_\_init\_\_(self, sectionName)
* configure(self, cfgFile)
* restart(self, doseID)
* switchOn(self, doseID)
* switchOff(self, doseID)
* startTimer(self, doseID)
* stopTimer(self, doseID)

##### \_\_init\_\_(self, sectionName)
The parameter for this method, *sectionName*, is the name of the section in the 
server's configuration file corresponding to this instance of switch handler.

##### configure(self, targetConfiguration)
This method configures the device so that it can be used later. The device is 
supposed to retrieve all required information from the *targetConfiguration*. 
The targetConfiguration has access to all the data from the server's 
configuration file. This method is always called after creation and before any 
other method of the switch is executed (besides `__init__`, of course)

##### restart(self, doseID)
Restart the socket with ID = doseID of the switch if the number of restarts 
does not exceed the maximum number of restarts. If the number of restarts 
exceeds the limit, throw a `ConcreteImplementationException`, preferably with a 
helpful error message. Whether the maximum number of restarts is assumed to be 
a total amount or a maximum for a specific time period is up to the 
implementation. For example, the project's Netio230BSwitch counts the 
number of restarts in the last hour.

##### switchOn(self, doseID)
Switch on the socket with ID = doseID of the switch.
In the case of a restart, always call `restart(self, doseID)` instead of calling
`switchOff(self, doseID)`
`switchOn(self, doseID)`
This is because `restart(self, doseID)` implements a maximum number of 
restarts, which `switchOn(self, doseID)` is not required to. Therefore, calling
`restart(self, doseID`) is safer.

##### switchOff(self, doseID)
Switch off the socket with ID = doseID of the switch.
In the case of a restart, always call `restart(self, doseID)` instead of calling
`switchOff(self, doseID)`
`switchOn(self, doseID)`
This is because `restart(self, doseID)` implements a maximum number of 
restarts, which `switchOff(self, doseID)` is not required to. Therefore, calling
`restart(self, doseID`) is safer.

##### startTimer(self, doseID)
This method is called when the execution finished and the device is not 
occupied. It implements the switch's behaviour in this idle state.
For example, the project's Netio230BSwitch starts a timer after which the 
device 
is shut off to save power.

##### stopTimer(self, doseID)
This method is called when a device is about to be used by an executable. It 
implements the switch device's behaviour upon starting to use the device. 
However, this method does not have to start the switch device if it is shut 
off. 

## Host Requirements

The dachs Test Server requires >= python 3.4.
Additionally, the following python modules are necessary:

* abc
* argparse
* asyncio
* base64
* collections
* concurrent.futures
* configparser
* datetime
* functools
* importlib
* libxml2
* pexpect
* queue
* re
* serial
* ssl
* subprocess
* sys
* tempfile
* tftpy
* threading
* time
* websockets

SPDX-License-Identifier: CC-BY-SA-4.0
Copyright (c) 2018 Andreas Dachsberger
All rights reserved.
