#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: myserial.py
# PURPOSE: Base serial comms for modbus
#
#  AUTHOR: Jason G Yates
#    DATE: 19-Apr-2018
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

"""
Module for serial communication management.

This module defines the `SerialDevice` class, which handles low-level serial
communication tasks such as opening/closing ports, reading/writing data,
and managing a thread for continuous reading.
"""

# For python 3.x compatibility with print function
from __future__ import print_function

import datetime
import os
import sys
import threading
from typing import Optional, Union, List, Any

import serial

from genmonlib.mylog import SetupLogger
from genmonlib.mysupport import MySupport
from genmonlib.mythread import MyThread
from genmonlib.program_defaults import ProgramDefaults


# ------------ SerialDevice class -----------------------------------------------
class SerialDevice(MySupport):
    """
    A class for managing serial device communication.

    Attributes:
        config (MyConfig): Configuration object.
        DeviceName (str): Name of the serial device (e.g., '/dev/serial0').
        BaudRate (int): Communication speed.
        Buffer (List[Union[int, str]]): Buffer for incoming data.
        BufferLock (threading.Lock): Lock for thread-safe buffer access.
        DiscardedBytes (int): Counter for discarded bytes.
        Restarts (int): Counter for serial connection restarts.
        SerialStartTime (datetime.datetime): Time when serial stats were last reset.
        loglocation (str): Path to the log directory.
        log (logging.Logger): Logger instance.
        console (logging.Logger): Console logger instance.
        SerialDevice (serial.Serial): The underlying pySerial object.
        IsOpen (bool): Flag indicating if the port is open.
        ForceSerialUse (bool): Flag to force serial port usage even if errors occur.
    """

    def __init__(
        self,
        name: str = "/dev/serial0",
        rate: int = 9600,
        log: Any = None,
        Parity: Optional[Union[int, str]] = None,
        OnePointFiveStopBits: Optional[bool] = None,
        sevendatabits: bool = False,
        RtsCts: bool = False,
        config: Any = None,
        loglocation: str = ProgramDefaults.LogPath,
    ):
        """
        Initializes the SerialDevice.

        Args:
            name (str, optional): Serial port name. Defaults to "/dev/serial0".
            rate (int, optional): Baud rate. Defaults to 9600.
            log (Any, optional): Logger instance. Defaults to None.
            Parity (Union[int, str], optional): Parity setting (None, 0=None, 1=Odd, 2=Even).
                Can also be string "None", "Odd", "Even". Defaults to None.
            OnePointFiveStopBits (bool, optional): Use 1.5 stop bits. Defaults to None.
            sevendatabits (bool, optional): Use 7 data bits instead of 8. Defaults to False.
            RtsCts (bool, optional): Enable hardware flow control. Defaults to False.
            config (Any, optional): Configuration object. Defaults to None.
            loglocation (str, optional): Path for logs. Defaults to ProgramDefaults.LogPath.
        """
        super(SerialDevice, self).__init__()

        self.config = config
        self.DeviceName = name
        self.BaudRate = rate
        self.Buffer = []
        self.BufferLock = threading.Lock()
        self.DiscardedBytes = 0
        self.Restarts = 0
        self.SerialStartTime = datetime.datetime.now()  # used for com metrics
        self.loglocation = loglocation
        self.IsOpen = False
        self.ForceSerialUse = False

        # This supports getting this info from genmon.conf
        if self.config is not None:
            self.loglocation = self.config.ReadValue("loglocation", default="/var/log/")
            self.DeviceName = self.config.ReadValue("port", default="/dev/serial0")
            self.ForceSerialUse = self.config.ReadValue("forceserialuse", default=False)

        # log errors in this module to a file
        if log is None:
            self.log = SetupLogger(
                "myserial", os.path.join(self.loglocation, "myserial.log")
            )
        else:
            self.log = log
        self.console = SetupLogger("myserial_console", log_file="", stream=True)

        try:
            # Starting serial connection
            if self.VersionTuple(serial.__version__) < self.VersionTuple("3.3"):
                self.SerialDevice = serial.Serial()
            else:
                # exclusive access for newer pySerial versions
                # Note: The original code instantiated serial.Serial twice in the else block.
                # Keeping logic but cleaning up potential double init if intended.
                # Actually, looking at original code:
                # self.SerialDevice = serial.Serial(exclusive=True)
                # self.SerialDevice = serial.Serial()
                # The second line overwrites the first. Assuming intention was to use exclusive if available.
                # However, serial.Serial() constructor doesn't take exclusive as kwarg in all versions?
                # Let's try to be safe.
                try:
                    self.SerialDevice = serial.Serial(exclusive=True)
                except TypeError:
                    self.SerialDevice = serial.Serial()

            self.SerialDevice.port = self.DeviceName
            self.SerialDevice.baudrate = rate
            # number of bits per bytes
            if sevendatabits:
                self.SerialDevice.bytesize = serial.SEVENBITS
            else:
                self.SerialDevice.bytesize = serial.EIGHTBITS

            if isinstance(Parity, str):
                if Parity.lower() == "none":
                    Parity = 0
                elif Parity.lower() == "odd":
                    Parity = 1
                else:
                    Parity = 2
            
            if Parity is None or Parity == 0:
                # set parity check: no parity
                self.SerialDevice.parity = serial.PARITY_NONE
            elif Parity == 1:
                # set parity check: use odd parity
                self.SerialDevice.parity = serial.PARITY_ODD
                self.LogError("Serial: Setting ODD parity")
            else:
                # set parity check: use even parity
                self.SerialDevice.parity = serial.PARITY_EVEN
                self.LogError("Serial: Setting EVEN parity")

            if OnePointFiveStopBits is None:
                self.SerialDevice.stopbits = serial.STOPBITS_ONE  # number of stop bits
            elif OnePointFiveStopBits:
                # number of stop bits
                self.SerialDevice.stopbits = serial.STOPBITS_ONE_POINT_FIVE
            else:
                self.SerialDevice.stopbits = serial.STOPBITS_ONE  # number of stop bits

            # small timeout so we can check if the thread should exit
            self.SerialDevice.timeout = 0.05
            self.SerialDevice.xonxoff = False  # disable software flow control
            self.SerialDevice.rtscts = RtsCts  # disable hardware (RTS/CTS) flow control
            self.SerialDevice.dsrdtr = False  # disable hardware (DSR/DTR) flow control
            # timeout for write, return when packet sent
            self.SerialDevice.writeTimeout = None

            # Check if port failed to open
            if not self.SerialDevice.isOpen():
                try:
                    self.SerialDevice.open()
                except Exception as e:
                    if not self.ForceSerialUse:
                        self.FatalError(
                            "Error on open serial port %s: " % self.DeviceName + str(e)
                        )
                        return None
                    else:
                        self.LogErrorLine(
                            "Error on open serial port %s: " % self.DeviceName + str(e)
                        )
            else:
                if not self.ForceSerialUse:
                    self.FatalError("Serial port already open: %s" % self.DeviceName)
                return None
            self.IsOpen = True
            self.Flush()
            self.StartReadThread()
        except Exception as e1:
            self.LogErrorLine("Error in init: " + str(e1))
            if not self.ForceSerialUse:
                self.FatalError("Error on serial port init!")

    def ResetSerialStats(self) -> None:
        """
        Resets serial statistics that are time-based.
        """
        self.SerialStartTime = datetime.datetime.now()  # used for com metrics

    def StartReadThread(self) -> Any:
        """
        Starts the read thread to monitor incoming data.

        Returns:
            MyThread: The started thread object.
        """
        # start read thread to monitor incoming data commands
        self.Threads["SerialReadThread"] = MyThread(
            self.ReadThread, Name="SerialReadThread"
        )

        return self.Threads["SerialReadThread"]

    def ReadThread(self) -> None:
        """
        The main loop for the read thread.

        Continuously reads data from the serial port and appends it to the buffer.
        Handles serial port restarts on errors.
        """
        while True:
            try:
                self.Flush()
                while True:
                    for c in self.Read():
                        with self.BufferLock:
                            if sys.version_info[0] < 3:
                                self.Buffer.append(ord(c))  # PYTHON2
                            else:
                                self.Buffer.append(c)  # PYTHON3
                        # first check for SignalStopped is when we are receiving
                        if self.IsStopSignaled("SerialReadThread"):
                            return
                    # second check for SignalStopped is when we are not receiving
                    if self.IsStopSignaled("SerialReadThread"):
                        return

            except Exception as e1:
                self.LogErrorLine(
                    "Resetting SerialDevice:ReadThread Error: "
                    + self.DeviceName
                    + ":"
                    + str(e1)
                )
                # if we get here then this is likely due to the following exception:
                #  "device reports readiness to read but returned no data (device disconnected?)"
                #  This is believed to be a kernel issue so let's just reset the device and hope
                #  for the best (actually this works)
                self.RestartSerial()

    def RestartSerial(self) -> None:
        """
        Attempts to close and reopen the serial port.
        """
        try:
            self.Restarts += 1
            try:
                self.SerialDevice.close()
            except Exception as e1:
                self.LogErrorLine("Error closing in RestartSerial:" + str(e1))
            try:
                self.SerialDevice.open()
            except Exception as e1:
                self.LogErrorLine("Error opening in RestartSerial:" + str(e1))
        except Exception as e1:
            self.LogErrorLine("Error in RestartSerial: " + str(e1))

    def DiscardByte(self) -> Optional[Union[int, str]]:
        """
        Removes and returns the first byte from the buffer.

        Returns:
            Optional[Union[int, str]]: The discarded byte or None if buffer empty.
        """
        if len(self.Buffer):
            discard = self.Buffer.pop(0)
            self.DiscardedBytes += 1
            return discard
        return None

    def Close(self) -> None:
        """
        Closes the serial port and stops the read thread.
        """
        try:
            if self.SerialDevice.isOpen():
                self.KillThread("SerialReadThread")
                self.SerialDevice.close()
                self.IsOpen = False
        except Exception as e1:
            self.LogErrorLine("Error in Close: " + str(e1))

    def Flush(self) -> None:
        """
        Flushes input and output buffers and clears the internal software buffer.
        """
        try:
            self.SerialDevice.flushInput()  # flush input buffer, discarding all its contents
            self.SerialDevice.flushOutput()  # flush output buffer, aborting current output
            with self.BufferLock:  # will block if lock is already held
                del self.Buffer[:]

        except Exception as e1:
            self.LogErrorLine(
                "Error in SerialDevice:Flush : " + self.DeviceName + ":" + str(e1)
            )
            self.RestartSerial()

    def Read(self) -> bytes:
        """
        Reads available bytes from the serial port.

        Returns:
            bytes: Data read from the port.
        """
        # self.SerialDevice.inWaiting returns number of bytes ready (logic handled by pySerial read)
        # In standard pySerial read(size=1) blocks based on timeout.
        # However, if size is not specified, it might read 1 byte by default or based on config.
        # Original code: return (self.SerialDevice.read())
        return self.SerialDevice.read()

    def Write(self, data: Union[bytes, str]) -> Union[int, bool]:
        """
        Writes data to the serial port.

        Args:
            data (Union[bytes, str]): Data to write.

        Returns:
            Union[int, bool]: Number of bytes written or False on error.
        """
        try:
            return self.SerialDevice.write(data)
        except Exception as e1:
            self.LogErrorLine(
                "Error in SerialDevice:Write : " + self.DeviceName + ":" + str(e1)
            )
            self.RestartSerial()
            return False

    def GetRxBufferAsString(self) -> str:
        """
        Returns the current buffer content as a string.

        Returns:
            str: Buffer contents converted to string.
        """
        try:
            if not len(self.Buffer):
                return ""
            with self.BufferLock:
                str1 = "".join(chr(e) for e in self.Buffer)
            return str1
        except Exception as e1:
            self.LogErrorLine("Error in GetRxBufferAsString: " + str(e1))
            return ""
