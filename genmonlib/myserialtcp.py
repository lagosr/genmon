#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: myserialtcp.py
# PURPOSE: Base serial over TCP comms for modbus
#
#  AUTHOR: Jason G Yates
#    DATE: 19-Apr-2018
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

"""
Module for TCP-based serial communication management.

This module defines the `SerialTCPDevice` class, which allows communication
over a TCP socket as if it were a serial port. This enables Modbus communication
over a network (Modbus RTU over TCP).
"""

# For python 3.x compatibility with print function
from __future__ import print_function

import datetime
import os
import socket
import sys
import threading
from typing import Optional, Union, List, Any

from genmonlib.mylog import SetupLogger
from genmonlib.mysupport import MySupport
from genmonlib.mythread import MyThread
from genmonlib.program_defaults import ProgramDefaults


# ------------ SerialTCPDevice class --------------------------------------------
class SerialTCPDevice(MySupport):
    """
    A class for managing serial communication over TCP.

    Attributes:
        config (MyConfig): Configuration object.
        DeviceName (str): Name of the device (fixed as 'serialTCP').
        Buffer (List[Union[int, str]]): Buffer for incoming data.
        BufferLock (threading.Lock): Lock for thread-safe buffer access.
        DiscardedBytes (int): Counter for discarded bytes.
        Restarts (int): Counter for connection restarts.
        SerialStartTime (datetime.datetime): Time when stats were last reset.
        rxdatasize (int): Size of the receive buffer.
        SocketTimeout (int): Timeout for socket operations in seconds.
        host (str): TCP host address.
        port (int): TCP port number.
        loglocation (str): Path to log directory.
        console (logging.Logger): Console logger.
        log (logging.Logger): File logger.
        Socket (socket.socket): The TCP socket object.
        IsOpen (bool): Flag indicating connection status.
    """

    def __init__(
        self,
        log: Any = None,
        host: str = ProgramDefaults.LocalHost,
        port: int = 8899,
        config: Any = None,
    ):
        """
        Initializes the SerialTCPDevice.

        Args:
            log (Any, optional): Logger instance. Defaults to None.
            host (str, optional): TCP host address. Defaults to ProgramDefaults.LocalHost.
            port (int, optional): TCP port number. Defaults to 8899.
            config (Any, optional): Configuration object. Defaults to None.
        """
        super(SerialTCPDevice, self).__init__()
        self.DeviceName = "serialTCP"
        self.config = config
        self.Buffer = []
        self.BufferLock = threading.Lock()
        self.DiscardedBytes = 0
        self.Restarts = 0
        self.SerialStartTime = datetime.datetime.now()  # used for com metrics
        self.rxdatasize = 2000
        self.SocketTimeout = 1

        self.host = host
        self.port = port
        self.Socket = None
        self.IsOpen = False

        if self.config is not None:
            self.loglocation = self.config.ReadValue("loglocation", default="/var/log/")
            self.host = self.config.ReadValue(
                "serial_tcp_address", return_type=str, default=None
            )
            self.port = self.config.ReadValue(
                "serial_tcp_port", return_type=int, default=None, NoLog=True
            )
        else:
            self.loglocation = "./"

        # log errors in this module to a file
        self.console = SetupLogger("myserialtcp_console", log_file="", stream=True)
        if log is None:
            self.log = SetupLogger(
                "myserialtcp", os.path.join(self.loglocation, "myserialtcp.log")
            )
        else:
            self.log = log

        if self.host is None or self.port is None:
            self.LogError("Invalid setting for host or port in myserialtcp")

        # Starting tcp connection
        self.Connect()

        self.IsOpen = True
        self.StartReadThread()

    def Connect(self) -> bool:
        """
        Establishes the TCP connection.

        Returns:
            bool: True if connection successful, False otherwise.
        """
        try:
            # create an INET, STREAMing socket
            self.Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.Socket.settimeout(self.SocketTimeout)
            # now connect to the server on our port
            self.Socket.connect((self.host, self.port))
            self.Flush()
            return True
        except Exception as e1:
            self.LogError("Error: Connect : " + str(e1))
            self.console.error("Unable to make TCP connection.")
            self.Socket = None
            return False

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
        self.Threads["SerialTCPReadThread"] = MyThread(
            self.ReadThread, Name="SerialTCPReadThread"
        )

        return self.Threads["SerialTCPReadThread"]

    def ReadThread(self) -> None:
        """
        The main loop for the read thread.

        Continuously reads data from the socket and handles connection restarts.
        """
        while True:
            try:
                self.Flush()
                while True:

                    if self.Socket is None:
                        self.Restarts += 1
                        if not self.Connect():
                            if self.WaitForExit(
                                "SerialTCPReadThread", 10
                            ):  # 10 seconds
                                return
                            continue

                    # read available bytes
                    data_read = self.Read()
                    # Process each byte/char
                    # The Read method returns bytes or str depending on py version and socket handling
                    # Original implementation iterates over return of Read()
                    for c in data_read:
                        with self.BufferLock:
                            if sys.version_info[0] < 3:
                                self.Buffer.append(ord(c))  # PYTHON2
                            else:
                                self.Buffer.append(c)  # PYTHON3
                        # first check for SignalStopped is when we are receiving
                        if self.IsStopSignaled("SerialTCPReadThread"):
                            return

                    # second check for SignalStopped is when we are not receiving
                    if self.IsStopSignaled("SerialTCPReadThread"):
                        return

            except Exception as e1:
                self.LogErrorLine(
                    "Resetting SerialTCPDevice:ReadThread Error: "
                    + self.DeviceName
                    + ":"
                    + str(e1)
                )
                # reset device
                if self.Socket is not None:
                    self.Socket.close()
                    self.Socket = None
                self.Connect()

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
        Closes the connection and stops the read thread.
        """
        try:
            if self.IsOpen:
                self.KillThread("SerialTCPReadThread")
                # close socket
                if self.Socket is not None:
                    self.Socket.close()
                    self.Socket = None
                self.IsOpen = False
        except Exception as e1:
            self.LogErrorLine("Error in SerialTCPDevice:Close : " + str(e1))

    def Flush(self) -> None:
        """
        Clears the internal receive buffer.
        """
        try:
            # Flush internal buffer
            with self.BufferLock:  # will block if lock is already held
                del self.Buffer[:]

        except Exception as e1:
            self.LogErrorLine("Error in SerialTCPDevice:Flush : " + str(e1))

    def Read(self) -> Union[bytes, str]:
        """
        Reads data from the socket.

        Returns:
            Union[bytes, str]: Data read from the socket. Empty string/bytes on error/timeout.
        """
        try:
            if self.Socket is None:
                return ""
            data = self.Socket.recv(self.rxdatasize)
            if data is None:
                return ""
            return data
        except socket.timeout:
            return ""
        except socket.error as err:
            self.LogErrorLine("Error in SerialTCPDevice:Read socket error: " + str(err))
            if self.Socket is not None:
                self.Socket.close()
                self.Socket = None
            return ""
        except Exception as e1:
            self.LogErrorLine("Error in SerialTCPDevice:Read : " + str(e1))
            if self.Socket is not None:
                self.Socket.close()
                self.Socket = None
            return ""

    def Write(self, data: Union[bytes, str]) -> Union[int, None]:
        """
        Writes data to the socket.

        Args:
            data (Union[bytes, str]): Data to write.

        Returns:
            Union[int, None]: Number of bytes sent, or None/0 on error.
        """
        try:
            if self.Socket is None:
                return None
            # sendall returns None on success
            self.Socket.sendall(data)
            return len(data)
        except Exception as e1:
            if self.Socket is not None:
                self.Socket.close()
                self.Socket = None
            self.LogErrorLine("Error in SerialTCPDevice:Write : " + str(e1))
            return 0

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
            self.LogErrorLine(
                "Error in SerialTCPDevice:GetRxBufferAsString: " + str(e1)
            )
            return ""
