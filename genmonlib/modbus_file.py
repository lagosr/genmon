#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: modbus_file.py
# PURPOSE: simulate modbus, registers backed by text file
#
#  AUTHOR: Jason G Yates
#    DATE: 19-Apr-2018
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

"""
Module for simulating Modbus communication.

This module defines the `ModbusFile` class, which mimics a Modbus device
by reading and writing register values from a text/JSON file. It is useful
for testing and simulation without actual hardware.
"""

# For python 3.x compatibility with print function
from __future__ import print_function

import collections
import datetime
import json
import os
import threading
import time
from typing import Optional, Any, Callable, List, Dict, Union

from genmonlib.modbusbase import ModbusBase
from genmonlib.mythread import MyThread


# ------------ ModbusFile class -------------------------------------------------
class ModbusFile(ModbusBase):
    """
    Simulates a Modbus device using a file as the data source.

    Attributes:
        InputFile (str): Path to the file containing register data.
        Registers (Dict): Cache of holding registers.
        Strings (Dict): Cache of string registers.
        FileData (Dict): Cache of file record data.
        Coils (Dict): Cache of coils.
        Inputs (Dict): Cache of input registers.
        SimulateTime (bool): Flag to inject artificial delays.
        CommAccessLock (threading.RLock): Lock for thread safety.
        Threads (Dict): Dictionary of active threads.
    """

    def __init__(
        self,
        updatecallback: Callable,
        address: int = 0x9D,
        name: str = "/dev/serial",
        rate: int = 9600,
        config: Any = None,
        inputfile: Optional[str] = None,
    ):
        """
        Initializes the ModbusFile instance.

        Args:
            updatecallback (Callable): Callback to update register values.
            address (int, optional): Modbus address. Defaults to 0x9D.
            name (str, optional): Device name (unused in simulation). Defaults to "/dev/serial".
            rate (int, optional): Baud rate (unused in simulation). Defaults to 9600.
            config (Any, optional): Configuration object. Defaults to None.
            inputfile (str, optional): Path to the simulation data file. Defaults to None.
        """
        super(ModbusFile, self).__init__(
            updatecallback=updatecallback,
            address=address,
            name=name,
            rate=rate,
            config=config,
        )

        self.Address = address
        self.Rate = rate
        self.PortName = name
        self.InputFile = inputfile
        self.InitComplete = False
        self.UpdateRegisterList = updatecallback
        self.RxPacketCount = 0
        self.TxPacketCount = 0
        self.ComTimoutError = 0
        self.TotalElapsedPacketeTime = 0
        self.CrcError = 0
        self.SimulateTime = True

        self.ModbusStartTime = datetime.datetime.now()  # used for com metrics
        self.Registers: Dict[str, str] = {}
        self.Strings: Dict[str, str] = {}
        self.FileData: Dict[str, str] = {}
        self.Coils: Dict[str, str] = {}
        self.Inputs: Dict[str, str] = {}

        if self.InputFile is None:
            self.InputFile = os.path.join(
                os.path.dirname(os.path.realpath(__file__)), "modbusregs.txt"
            )

        if not os.path.isfile(self.InputFile):
            self.LogError("Error: File not present: " + self.InputFile)
        self.CommAccessLock = (
            threading.RLock()
        )  # lock to synchronize access to the serial port comms
        self.UpdateRegisterList = updatecallback

        if not self.ReadInputFile(self.InputFile):
            self.LogError(
                "ModusFile Init(): Error loading input file: " + self.InputFile
            )
        else:
            if not self.AdjustInputData():
                self.LogInfo("Error parsing input data")

            self.Threads["ReadInputFileThread"] = MyThread(
                self.ReadInputFileThread, Name="ReadInputFileThread", start=False
            )
            self.Threads["ReadInputFileThread"].Start()
        self.InitComplete = False

    def ReadInputFileThread(self) -> None:
        """
        Periodically re-reads the input file to update simulation data.
        """
        while True:
            if self.IsStopSignaled("ReadInputFileThread"):
                break
            self.ReadInputFile(self.InputFile)
            if not self.AdjustInputData():
                self.LogInfo("Error parsing input data")
            time.sleep(5)

    def ProcessWriteTransaction(
        self, Register: str, Length: int, Data: List[int], IsCoil: bool = False
    ) -> None:
        """
        Stub for processing write transactions.

        Currently does not update the internal state or file.

        Args:
            Register (str): Register address.
            Length (int): Data length.
            Data (List[int]): Data payload.
            IsCoil (bool, optional): True if coil write. Defaults to False.
        """
        return

    def ProcessTransaction(
        self,
        Register: str,
        Length: int,
        skipupdate: bool = False,
        ReturnString: bool = False,
        IsCoil: bool = False,
        IsInput: bool = False
    ) -> str:
        """
        Simulates a read transaction by fetching data from internal caches.

        Args:
            Register (str): Register address.
            Length (int): Read length.
            skipupdate (bool, optional): Skip callback update. Defaults to False.
            ReturnString (bool, optional): Return data as string. Defaults to False.
            IsCoil (bool, optional): Read coil. Defaults to False.
            IsInput (bool, optional): Read input register. Defaults to False.

        Returns:
            str: The register value.
        """
        # TODO need more validation

        if ReturnString:
            RegValue = self.Strings.get(Register, "")
        else:
            RegValue = self.Strings.get(Register, None)

            if RegValue is None:
                if IsCoil:
                    RegValue = self.Coils.get(Register, "")
                elif IsInput:
                    RegValue = self.Inputs.get(Register, "")
                else:
                    RegValue = self.Registers.get(Register, "")

                if len(RegValue):
                    while len(RegValue) != Length * 4:

                        if len(RegValue) < Length * 4:
                            RegValue = "0" + RegValue
                        elif len(RegValue) > Length * 4:
                            RegValue = RegValue[1:]

        self.TxPacketCount += 1
        self.RxPacketCount += 1
        if self.SimulateTime:
            time.sleep(0.02)

        if not skipupdate:
            if self.UpdateRegisterList is not None:
                self.UpdateRegisterList(
                    Register, RegValue, IsFile=False, IsString=ReturnString
                )

        return RegValue

    def ProcessFileReadTransaction(
        self,
        Register: str,
        Length: int,
        skipupdate: bool = False,
        file_num: int = 1,
        ReturnString: bool = False
    ) -> str:
        """
        Simulates a file read transaction.

        Args:
            Register (str): File record number.
            Length (int): Length to read.
            skipupdate (bool, optional): Skip callback update. Defaults to False.
            file_num (int, optional): File number. Defaults to 1.
            ReturnString (bool, optional): Return as string. Defaults to False.

        Returns:
            str: The file data.
        """
        RegValue = self.FileData.get(Register, "")

        self.TxPacketCount += 1
        self.RxPacketCount += 1
        if self.SimulateTime:
            time.sleep(0.02)

        RegValue = self.FileData.get(Register, "")
        if not skipupdate:
            if self.UpdateRegisterList is not None:
                self.UpdateRegisterList(
                    Register, RegValue, IsFile=True, IsString=ReturnString
                )

        return RegValue

    def AdjustInputData(self) -> bool:
        """
        Ensures register data is correctly formatted (padded/converted).

        Returns:
            bool: True if successful, False otherwise.
        """
        if not len(self.Registers):
            self.LogError("Error in AdjustInputData, no data.")
            return False
        #  No need to adjust data for registers, move on to strings and File data
        for Reg, Value in self.Strings.items():
            RegInt = int(Reg, 16)
            if not len(Value):
                self.Registers["%04x" % (RegInt)] = "0000"
                continue
            if self.StringIsHex(Value):
                # Not a string, just hex data in a string format
                for i in range(0, len(Value), 4):
                    self.Registers["%04x" % (RegInt + int(i / 4))] = Value[i : i + 4]
            else:
                for i in range(0, len(Value), 2):
                    HiByte = ord(Value[i])
                    if i + 1 >= len(Value):
                        LowByte = 0
                    else:
                        LowByte = ord(Value[i + 1])
                    self.Registers["%04x" % (RegInt + int(i / 2))] = "%02x%02x" % (
                        HiByte,
                        LowByte,
                    )
        return True

    def ReadJSONFile(self, FileName: str) -> bool:
        """
        Reads simulation data from a JSON file.

        Args:
            FileName (str): Path to JSON file.

        Returns:
            bool: True if successful, False otherwise.
        """
        if not len(FileName):
            self.LogError("Error in  ReadJSONFile: No Input File")
            return False
        try:
            with open(FileName) as f:
                data = json.load(f, object_pairs_hook=collections.OrderedDict)
                self.Registers = data["Registers"]
                self.Strings = data["Strings"]
                self.FileData = data["FileData"]
                if "Coils" in data:
                    self.Coils = data["Coils"]
                else:
                    self.Coils = {}
                if "Inputs" in data:
                    self.Inputs = data["Inputs"]
                else:
                    self.Inputs = {}
            return True
        except Exception:
            # self.LogErrorLine("Error in ReadJSONFile: " + str(e1))
            return False

    def ReadInputFile(self, FileName: str) -> bool:
        """
        Reads simulation data from a text or JSON file.

        Args:
            FileName (str): Path to the input file.

        Returns:
            bool: True if successful, False otherwise.
        """
        REGISTERS = 0
        STRINGS = 1
        FILE_DATA = 2

        Section = REGISTERS
        if not len(FileName):
            self.LogError("Error in  ReadInputFile: No Input File")
            return False

        if self.ReadJSONFile(FileName):
            return True

        try:

            with open(FileName, "r") as InputFile:  # opens file

                for line in InputFile:
                    line = line.strip()  # remove beginning and ending whitespace

                    if not len(line):
                        continue
                    if line[0] == "#":  # comment?
                        continue
                    if "Strings :" in line:
                        Section = STRINGS
                    elif "FileData :" in line:
                        Section = FILE_DATA
                    if Section == REGISTERS:
                        line = line.replace("\t", " ")
                        line = line.replace(" : ", ":")
                        Items = line.split(" ")
                        for entry in Items:
                            RegEntry = entry.split(":")
                            if len(RegEntry) == 2:
                                if len(RegEntry[0]) and len(RegEntry[1]):
                                    try:
                                        if Section == REGISTERS:
                                            # Just validation
                                            int(RegEntry[0], 16)
                                            int(RegEntry[1], 16)
                                            self.Registers[RegEntry[0]] = RegEntry[1]

                                    except Exception:
                                        continue
                    elif Section == STRINGS:
                        Items = line.split(" : ")
                        if len(Items) == 2:
                            self.Strings[Items[0]] = Items[1]
                        else:
                            pass
                    elif Section == FILE_DATA:
                        Items = line.split(" : ")
                        if len(Items) == 2:
                            self.FileData[Items[0]] = Items[1]
                        else:
                            pass

            return True

        except Exception as e1:
            self.LogErrorLine("Error in  ReadInputFile: " + str(e1))
            return False

    def GetCommStats(self) -> List[Dict[str, Any]]:
        """
        Retrieves communication statistics (simulated).

        Returns:
            List[Dict[str, Any]]: List of stats dictionaries.
        """
        SerialStats = []

        SerialStats.append(
            {"Packet Count": "M: %d, S: %d" % (self.TxPacketCount, self.RxPacketCount)}
        )

        if self.CrcError == 0 or self.RxPacketCount == 0:
            PercentErrors = 0.0
        else:
            PercentErrors = float(self.CrcError) / float(self.RxPacketCount)

        SerialStats.append({"CRC Errors": "%d " % self.CrcError})
        SerialStats.append({"CRC Percent Errors": "%.2f" % PercentErrors})
        SerialStats.append({"Timeouts Errors": "%d" % self.ComTimoutError})
        # Add serial stats here

        CurrentTime = datetime.datetime.now()

        #
        Delta = CurrentTime - self.ModbusStartTime  # yields a timedelta object
        PacketsPerSecond = float((self.TxPacketCount + self.RxPacketCount)) / float(
            Delta.total_seconds()
        )
        SerialStats.append({"Packets Per Second": "%.2f" % (PacketsPerSecond)})

        if self.RxPacketCount:
            AvgTransactionTime = float(
                self.TotalElapsedPacketeTime / self.RxPacketCount
            )
            SerialStats.append(
                {"Average Transaction Time": "%.4f sec" % (AvgTransactionTime)}
            )

        return SerialStats

    def ResetCommStats(self) -> None:
        """
        Resets communication statistics.
        """
        self.RxPacketCount = 0
        self.TxPacketCount = 0
        self.TotalElapsedPacketeTime = 0
        self.ModbusStartTime = datetime.datetime.now()  # used for com metrics
        pass

    def Flush(self) -> None:
        """
        Flushes buffers (Stub).
        """
        pass

    def Close(self) -> None:
        """
        Closes the simulation (Stub).
        """
        pass
