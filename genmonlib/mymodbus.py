#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: mymodbus.py
# PURPOSE: Base modbus protocol support
#
#  AUTHOR: Jason G Yates
#    DATE: 19-Apr-2018
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

"""
Module for Modbus protocol handling.

This module defines the `ModbusProtocol` class, which extends `ModbusBase` to
provide higher-level Modbus functionalities such as packet creation,
transaction processing, and CRC calculation. It supports both Serial and TCP
transport layers.
"""

# For python 3.x compatibility with print function
from __future__ import print_function

import datetime
import sys
import time
import collections
from typing import Optional, Any, Callable, List, Dict, Union, Tuple

import crcmod

from genmonlib.modbusbase import ModbusBase
from genmonlib.myserial import SerialDevice
from genmonlib.myserialtcp import SerialTCPDevice


# ------------ ModbusProtocol class ---------------------------------------------
class ModbusProtocol(ModbusBase):
    """
    Implements the Modbus protocol layer.

    Handles the creation of Modbus packets, processing of transactions (read/write),
    CRC validation, and interaction with the underlying communication device (Slave).

    Attributes:
        ModbusTCP (bool): Flag indicating if Modbus TCP encapsulation is used.
        Host (str): TCP Host address.
        Port (int): TCP Port.
        Parity (str/int): Serial parity setting.
        Rate (int): Serial baud rate.
        TransactionID (int): Modbus TCP transaction ID counter.
        AlternateFileProtocol (bool): Flag for alternate file protocol handling.
        UseTCP (bool): Flag indicating if serial-over-TCP is used.
        ModBusPacketTimoutMS (float): Calculated timeout for packet reception in milliseconds.
        Slave (Union[SerialDevice, SerialTCPDevice]): The communication device interface.
        ModbusCrc (Callable): CRC calculation function.
        Threads (Dict): Dictionary of active threads.
    """

    def __init__(
        self,
        updatecallback: Callable,
        address: int = 0x9D,
        name: str = "/dev/serial0",
        rate: int = 9600,
        Parity: Optional[Union[int, str]] = None,
        OnePointFiveStopBits: Optional[bool] = None,
        config: Any = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        modbustcp: bool = False,  # True if Modbus TCP, else if TCP then assume serial over TCP (Modbus RTU over serial)
        use_fc4: bool = False,
    ):
        """
        Initializes the ModbusProtocol instance.

        Args:
            updatecallback (Callable): Callback for updating registers.
            address (int, optional): Modbus slave address. Defaults to 0x9D.
            name (str, optional): Serial port name. Defaults to "/dev/serial0".
            rate (int, optional): Baud rate. Defaults to 9600.
            Parity (Union[int, str], optional): Parity setting. Defaults to None.
            OnePointFiveStopBits (bool, optional): Stop bits setting. Defaults to None.
            config (Any, optional): Configuration object. Defaults to None.
            host (str, optional): TCP host address. Defaults to None.
            port (int, optional): TCP port. Defaults to None.
            modbustcp (bool, optional): Enable Modbus TCP encapsulation. Defaults to False.
            use_fc4 (bool, optional): Use Function Code 4 instead of 3. Defaults to False.
        """
        super(ModbusProtocol, self).__init__(
            updatecallback=updatecallback,
            address=address,
            name=name,
            rate=rate,
            config=config,
            use_fc4=use_fc4,
        )

        try:
            if config is None:
                self.ModbusTCP = modbustcp
                self.Host = host
                self.Port = port
                self.Parity = Parity
                self.Rate = rate
            self.TransactionID = 0
            self.AlternateFileProtocol = False

            if host is not None and port is not None and self.config is None:
                # in this instance we do not use a config file, but config comes from command line
                self.UseTCP = True

            # ~3000 for 9600: bit time * 10 bits * 10 char * 2 packets + wait time(3000) (convert to ms * 1000)
            self.ModBusPacketTimoutMS = (
                (((1 / float(self.Rate)) * 10.0) * 10.0 * 2.0) * 1000.0
            ) + 3000.0  # .00208

            self.ModBusPacketTimoutMS += self.AdditionalModbusTimeout * 1000.0

            if self.ModbusTCP:
                self.MIN_PACKET_RESPONSE_LENGTH -= 2
                self.MBUS_RES_PAYLOAD_SIZE_MINUS_LENGTH -= 2
                self.MBUS_FILE_READ_PAYLOAD_SIZE_MINUS_LENGTH -= 2
                self.MBUS_CRC_SIZE = 0
                self.MIN_PACKET_ERR_LENGTH -= 2

            if self.UseTCP:
                self.ModBusPacketTimoutMS = self.ModBusPacketTimoutMS + 2000
            # Starting serial connection
            if self.UseTCP:
                self.Slave = SerialTCPDevice(config=self.config, host=host, port=port)
            else:
                self.Slave = SerialDevice(
                    name=name,
                    rate=self.Rate,
                    Parity=self.Parity,
                    OnePointFiveStopBits=OnePointFiveStopBits,
                    config=self.config,
                )
            self.Threads = self.MergeDicts(self.Threads, self.Slave.Threads)

        except Exception as e1:
            self.LogErrorLine("Error opening modbus device: " + str(e1))
            self.FatalError("Error opening modbus device.")

        try:
            # CRCMOD library, used for CRC calculations
            self.ModbusCrc = crcmod.predefined.mkCrcFun("modbus")
            self.InitComplete = True
        except Exception as e1:
            self.FatalError("Unable to find crcmod package: " + str(e1))

    def GetExceptionString(self, Code: int) -> str:
        """
        Retrieves the exception string for a given Modbus exception code.

        Also updates internal exception statistics counters.

        Args:
            Code (int): The Modbus exception code.

        Returns:
            str: A human-readable description of the exception.
        """
        try:
            LookUp = {
                self.MBUS_EXCEP_FUNCTION: "Illegal Function",
                self.MBUS_EXCEP_ADDRESS: "Illegal Address",
                self.MBUS_EXCEP_DATA: "Illegal Data Value",
                self.MBUS_EXCEP_SLAVE_FAIL: "Slave Device Failure",
                self.MBUS_EXCEP_ACK: "Acknowledge",
                self.MBUS_EXCEP_BUSY: "Slave Device Busy",
                self.MBUS_EXCEP_NACK: "Negative Acknowledge",
                self.MBUS_EXCEP_MEM_PE: "Memory Parity Error",
                self.MBUS_EXCEP_GATEWAY: "Gateway Path Unavailable",
                self.MBUS_EXCEP_GATEWAY_TG: "Gateway Target Device Failed to Respond",
            }

            if Code == self.MBUS_EXCEP_FUNCTION:
                self.ExcepFunction += 1
            elif Code == self.MBUS_EXCEP_ADDRESS:
                self.ExcepAddress += 1
            elif Code == self.MBUS_EXCEP_DATA:
                self.ExcepData += 1
            elif Code == self.MBUS_EXCEP_SLAVE_FAIL:
                self.ExcepSlave += 1
            elif Code == self.MBUS_EXCEP_ACK:
                self.ExcepAck += 1
            elif Code == self.MBUS_EXCEP_BUSY:
                self.ExcepBusy += 1
            elif Code == self.MBUS_EXCEP_NACK:
                self.ExcepNack += 1
            elif Code == self.MBUS_EXCEP_MEM_PE:
                self.ExcepMemPe += 1
            elif Code == self.MBUS_EXCEP_GATEWAY:
                self.ExcepGateway += 1
            elif Code == self.MBUS_EXCEP_GATEWAY_TG:
                self.ExcepGateWayTg += 1

            ReturnString = LookUp.get(Code, "Unknown")
            ReturnString = ReturnString + (": %02x" % Code)
            return ReturnString
        except Exception as e1:
            self.LogErrorLine("Error in GetExceptionString: " + str(e1))

        return ""

    def CheckResponseAddress(self, Address: int) -> bool:
        """
        Validates the response address against expected values.

        Args:
            Address (int): The address from the received packet.

        Returns:
            bool: True if valid, False otherwise.
        """
        if Address == self.Address:
            return True
        if self.ResponseAddress is None:
            return False
        if Address == self.ResponseAddress:
            return True
        return False

    def GetPacketFromSlave(
        self, min_response_override: Optional[int] = None
    ) -> Tuple[bool, List[int]]:
        """
        Reads and validates a Modbus packet from the slave device.

        Checks headers (TCP/Serial), address, length, error flags, and CRC.

        Args:
            min_response_override (int, optional): Override minimum response length check.

        Returns:
            Tuple[bool, List[int]]: (Success Flag, The Packet Data).
                Success=True and Empty Packet means "keep waiting/reading".
                Success=False means error occurred.
                Success=True and Non-Empty Packet means valid data.
        """
        LocalErrorCount = 0
        Packet = []
        EmptyPacket = []  # empty packet
        try:
            if not len(self.Slave.Buffer):
                return True, EmptyPacket

            if self.ModbusTCP:
                # Modbus TCP Header processing
                if len(self.Slave.Buffer) < (
                    self.MIN_PACKET_ERR_LENGTH + self.MODBUS_TCP_HEADER_SIZE
                ):
                    return True, EmptyPacket

                # transaction ID must match
                rxID = (self.Slave.Buffer[0] << 8) | (self.Slave.Buffer[1] & 0xFF)
                if self.CurrentTransactionID != rxID:
                    self.LogError(
                        "ModbusTCP transaction ID mismatch: %x %x"
                        % (self.CurrentTransactionID, rxID)
                    )
                    self.DiscardByte(reason="Transaction ID")
                    self.Flush()
                    return False, EmptyPacket
                # protocol ID is zero
                if self.Slave.Buffer[2] != 0 or self.Slave.Buffer[3] != 0:
                    self.LogError(
                        "ModbusTCP protocool ID non zero: %x %x"
                        % (self.Slave.Buffer[2], self.Slave.Buffer[3])
                    )
                    self.DiscardByte(reason="protocol error")
                    self.Flush()
                    return False, EmptyPacket
                # Modbus TCP payload length
                ModbusTCPLength = (self.Slave.Buffer[4] << 8) | (
                    self.Slave.Buffer[5] & 0xFF
                )
                if len(self.Slave.Buffer[6:]) != ModbusTCPLength:
                    # more data is needed
                    return True, EmptyPacket

                # remove modbud TCP header
                for i in range(0, self.MODBUS_TCP_HEADER_SIZE):
                    self.Slave.Buffer.pop(0)

            if not self.CheckResponseAddress(self.Slave.Buffer[self.MBUS_OFF_ADDRESS]):
                self.DiscardByte(reason="Response Address")
                self.Flush()
                return False, EmptyPacket

            if len(self.Slave.Buffer) < self.MIN_PACKET_ERR_LENGTH:
                return True, EmptyPacket  # No full packet ready

            if self.Slave.Buffer[self.MBUS_OFF_COMMAND] & self.MBUS_ERROR_BIT:
                for i in range(0, self.MIN_PACKET_ERR_LENGTH):
                    Packet.append(
                        self.Slave.Buffer.pop(0)
                    )  # pop Address, Function, Exception code, and CRC
                if self.CheckCRC(Packet):
                    self.RxPacketCount += 1
                    self.ModbusException += 1
                    self.LogError(
                        "Modbus Exception: "
                        + self.GetExceptionString(Packet[self.MBUS_OFF_EXCEPTION])
                        + " , Modbus Command: "
                        + ("%02x" % Packet[self.MBUS_OFF_COMMAND])
                        + " , Sequence: "
                        + str(self.TxPacketCount)
                    )

                else:
                    self.CrcError += 1
                return False, Packet

            if min_response_override is not None:
                if len(self.Slave.Buffer) < min_response_override:
                    return True, EmptyPacket  # No full packet ready
            else:
                if len(self.Slave.Buffer) < self.MIN_PACKET_RESPONSE_LENGTH:
                    return True, EmptyPacket  # No full packet ready

            if self.Slave.Buffer[self.MBUS_OFF_COMMAND] in [
                self.MBUS_CMD_READ_HOLDING_REGS,
                self.MBUS_CMD_READ_INPUT_REGS,
                self.MBUS_CMD_READ_COILS,
            ]:
                # it must be a read command response
                length = self.Slave.Buffer[self.MBUS_OFF_RESPONSE_LEN]
                # if the full length of the packet has not arrived, return and try again
                if (length + self.MBUS_RES_PAYLOAD_SIZE_MINUS_LENGTH) > len(
                    self.Slave.Buffer
                ):
                    return True, EmptyPacket

                for i in range(0, length + self.MBUS_RES_PAYLOAD_SIZE_MINUS_LENGTH):
                    Packet.append(
                        self.Slave.Buffer.pop(0)
                    )  # pop Address, Function, Length, message and CRC

                if self.CheckCRC(Packet):
                    self.RxPacketCount += 1
                    return True, Packet
                else:
                    self.CrcError += 1
                    return False, Packet
            elif self.Slave.Buffer[self.MBUS_OFF_COMMAND] in [
                self.MBUS_CMD_WRITE_REGS,
                self.MBUS_CMD_WRITE_COILS,
            ]:
                # it must be a write command response
                if len(self.Slave.Buffer) < self.MIN_PACKET_MIN_WRITE_RESPONSE_LENGTH:
                    return True, EmptyPacket
                for i in range(0, self.MIN_PACKET_MIN_WRITE_RESPONSE_LENGTH):
                    # address, function, address hi, address low, quantity hi, quantity low, CRC high, crc low
                    Packet.append(self.Slave.Buffer.pop(0))

                if self.CheckCRC(Packet):
                    self.RxPacketCount += 1
                    return True, Packet
                else:
                    self.CrcError += 1
                    return False, Packet
            elif self.Slave.Buffer[self.MBUS_OFF_COMMAND] in [
                self.MBUS_CMD_WRITE_COIL,
                self.MBUS_CMD_WRITE_REG,
            ]:
                if len(self.Slave.Buffer) < self.MBUS_SINGLE_WRITE_RES_LENGTH:
                    return True, EmptyPacket
                for i in range(0, self.MIN_PACKET_MIN_WRITE_RESPONSE_LENGTH):
                    # address, function, address hi, address low, value hi, value low, CRC high, crc low
                    Packet.append(self.Slave.Buffer.pop(0))

                if self.CheckCRC(Packet):
                    self.RxPacketCount += 1
                    return True, Packet
                else:
                    self.CrcError += 1
                    return False, Packet
            elif self.Slave.Buffer[self.MBUS_OFF_COMMAND] in [self.MBUS_CMD_READ_FILE]:
                length = self.Slave.Buffer[
                    self.MBUS_OFF_RESPONSE_LEN
                ]  # our packet tells us the length of the payload
                if (
                    self.Slave.Buffer[self.MBUS_OFF_FILE_TYPE]
                    != self.MBUS_FILE_TYPE_VALUE
                ):
                    self.LogError("Invalid modbus file record type")
                    self.ComValidationError += 1
                    return False, EmptyPacket
                # if the full length of the packet has not arrived, return and try again
                if (length + self.MBUS_FILE_READ_PAYLOAD_SIZE_MINUS_LENGTH) > len(
                    self.Slave.Buffer
                ):
                    return True, EmptyPacket
                # we will copy the entire buffer, this will be validated at a later time
                for i in range(0, len(self.Slave.Buffer)):
                    Packet.append(
                        self.Slave.Buffer.pop(0)
                    )  # pop Address, Function, Length, message and CRC

                if len(self.Slave.Buffer):
                    self.LogHexList(self.Slave.Buffer, prefix="Left Over")

                if self.CheckCRC(Packet):
                    self.RxPacketCount += 1
                    return True, Packet
                else:
                    self.CrcError += 1
                    return False, Packet
            elif self.Slave.Buffer[self.MBUS_OFF_COMMAND] in [self.MBUS_CMD_WRITE_FILE]:
                length = self.Slave.Buffer[
                    self.MBUS_OFF_RESPONSE_LEN
                ]  # our packet tells us the length of the payload
                if (
                    self.Slave.Buffer[self.MBUS_OFF_WRITE_FILE_TYPE]
                    != self.MBUS_FILE_TYPE_VALUE
                ):
                    self.LogError("Invalid modbus write file record type")
                    self.ComValidationError += 1
                    return False, EmptyPacket
                # if the full length of the packet has not arrived, return and try again
                if (length + self.MBUS_FILE_READ_PAYLOAD_SIZE_MINUS_LENGTH) > len(
                    self.Slave.Buffer
                ):
                    return True, EmptyPacket
                # we will copy the entire buffer, this will be validated at a later time
                for i in range(0, len(self.Slave.Buffer)):
                    Packet.append(
                        self.Slave.Buffer.pop(0)
                    )  # pop Address, Function, Length, message and CRC

                if len(self.Slave.Buffer):
                    self.LogHexList(self.Slave.Buffer, prefix="Left Over")

                if self.CheckCRC(Packet):
                    self.RxPacketCount += 1
                    return True, Packet
                else:
                    self.CrcError += 1
                    return False, Packet
            else:
                # received a  response to a command we do not support
                self.DiscardByte(reason="Invalid Modbus command")
                self.Flush()
                return False, EmptyPacket
        except Exception as e1:
            self.LogErrorLine("Error in GetPacketFromSlave: " + str(e1))
            self.ComValidationError += 1
            return False, EmptyPacket

    def DiscardByte(self, reason: Optional[str] = None) -> None:
        """
        Discards a byte from the slave buffer and logs the action.

        Args:
            reason (str, optional): Reason for discard. Defaults to None.
        """
        discard = self.Slave.DiscardByte()
        if reason is None:
            reason = "Unknown"
        self.LogError("Discarding byte slave: %02x : %s " % (discard, str(reason)))

    def _PWT(
        self,
        Register: str,
        Length: int,
        Data: List[int],
        min_response_override: Optional[int] = None,
        IsCoil: bool = False,
        IsSingle: bool = False
    ) -> Any:
        """
        Internal Process Write Transaction method.

        Constructs and sends a write packet.

        Args:
            Register (str): Register address (hex string).
            Length (int): Data length.
            Data (List[int]): Data to write.
            min_response_override (int, optional): Minimum expected response length.
            IsCoil (bool, optional): Writing coil(s).
            IsSingle (bool, optional): Single value write.

        Returns:
            Any: Result of ProcessOneTransaction.
        """
        try:
            with self.CommAccessLock:
                MasterPacket = []

                if IsCoil:
                    if not IsSingle:
                        cmd = self.MBUS_CMD_WRITE_COILS
                    else:
                        cmd = self.MBUS_CMD_WRITE_COIL
                else:
                    if not IsSingle:
                        cmd = self.MBUS_CMD_WRITE_REGS
                    else:
                        cmd = self.MBUS_CMD_WRITE_REG
                MasterPacket = self.CreateMasterPacket(
                    Register,
                    length=int(Length),
                    command=cmd,
                    data=Data,
                )

                if len(MasterPacket) == 0:
                    return False

                # skipupdate=True to skip writing results to cached reg values
                return self.ProcessOneTransaction(
                    MasterPacket,
                    skipupdate=True,
                    min_response_override=min_response_override,
                )
        except Exception as e1:
            self.LogErrorLine("Error in ProcessWriteTransaction: " + str(e1))
            return False

    def ProcessWriteTransaction(
        self,
        Register: str,
        Length: int,
        Data: List[int],
        IsCoil: bool = False,
        IsSingle: bool = False
    ) -> Any:
        """
        Processes a write transaction (wrapper for _PWT).

        Args:
            Register (str): Register address.
            Length (int): Length.
            Data (List[int]): Data payload.
            IsCoil (bool): Coil write flag.
            IsSingle (bool): Single value write flag.

        Returns:
            Any: Transaction result.
        """
        return self._PWT(Register, Length, Data, IsCoil=IsCoil, IsSingle=IsSingle)

    def _PT(
        self,
        Register: str,
        Length: int,
        skipupdate: bool = False,
        ReturnString: bool = False,
        IsCoil: bool = False,
        IsInput: bool = False
    ) -> Any:
        """
        Internal Process Transaction (Read) method.

        Constructs and sends a read packet.

        Args:
            Register (str): Register address (hex string).
            Length (int): Length to read.
            skipupdate (bool): Skip updating cache.
            ReturnString (bool): Return result as string.
            IsCoil (bool): Read coils.
            IsInput (bool): Read input registers.

        Returns:
            Any: Read value or empty string on error.
        """
        MasterPacket = []

        try:
            min_response_override = None  # use the default minimum response packet size
            with self.CommAccessLock:
                if IsCoil:
                    packet_type = self.MBUS_CMD_READ_COILS
                elif IsInput:
                    packet_type = self.MBUS_CMD_READ_INPUT_REGS
                else:
                    packet_type = self.MBUS_CMD_READ_HOLDING_REGS
                MasterPacket = self.CreateMasterPacket(
                    Register, command=packet_type, length=int(Length)
                )

                if len(MasterPacket) == 0:
                    return ""

                return self.ProcessOneTransaction(
                    MasterPacket,
                    skipupdate=skipupdate,
                    ReturnString=ReturnString,
                    min_response_override=min_response_override,
                )  # don't log

        except Exception as e1:
            self.LogErrorLine("Error in ProcessTransaction: " + str(e1))
            return ""

    def ProcessTransaction(
        self,
        Register: str,
        Length: int,
        skipupdate: bool = False,
        ReturnString: bool = False,
        IsCoil: bool = False,
        IsInput: bool = False
    ) -> Any:
        """
        Processes a read transaction (wrapper for _PT).

        Args:
            Register (str): Register address.
            Length (int): Read length.
            skipupdate (bool): Skip update flag.
            ReturnString (bool): Return as string flag.
            IsCoil (bool): Read coil flag.
            IsInput (bool): Read input register flag.

        Returns:
            Any: Read result.
        """
        return self._PT(
            Register,
            Length,
            skipupdate=skipupdate,
            ReturnString=ReturnString,
            IsCoil=IsCoil,
            IsInput=IsInput,
        )

    def ProcessFileReadTransaction(
        self,
        Register: str,
        Length: int,
        skipupdate: bool = False,
        file_num: int = 1,
        ReturnString: bool = False
    ) -> Any:
        """
        Processes a file read transaction (Function Code 0x14).

        Args:
            Register (str): File record number (hex string).
            Length (int): Number of words/bytes to read.
            skipupdate (bool): Skip update flag.
            file_num (int): File number.
            ReturnString (bool): Return as string flag.

        Returns:
            Any: Read result.
        """
        MasterPacket = []

        try:
            with self.CommAccessLock:
                MasterPacket = self.CreateMasterPacket(
                    Register,
                    length=int(Length),
                    command=self.MBUS_CMD_READ_FILE,
                    file_num=file_num,
                )

                if len(MasterPacket) == 0:
                    return ""

                return self.ProcessOneTransaction(
                    MasterPacket, skipupdate=skipupdate, ReturnString=ReturnString
                )  # don't log

        except Exception as e1:
            self.LogErrorLine("Error in ProcessFileReadTransaction: " + str(e1))
            return ""

    def ProcessFileWriteTransaction(
        self,
        Register: str,
        Length: int,
        Data: List[int],
        file_num: int = 1,
        min_response_override: Optional[int] = None
    ) -> Any:
        """
        Processes a file write transaction (Function Code 0x15).

        Args:
            Register (str): File record number (hex string).
            Length (int): Data length.
            Data (List[int]): Data payload.
            file_num (int): File number.
            min_response_override (int, optional): Expected response length.

        Returns:
            Any: Transaction result.
        """
        MasterPacket = []

        try:
            with self.CommAccessLock:
                MasterPacket = self.CreateMasterPacket(
                    Register,
                    length=int(Length),
                    command=self.MBUS_CMD_WRITE_FILE,
                    file_num=file_num,
                    data=Data,
                )

                if len(MasterPacket) == 0:
                    return ""

                # skipupdate=True to skip writing results to cached reg values
                return self.ProcessOneTransaction(
                    MasterPacket,
                    skipupdate=True,
                    min_response_override=min_response_override,
                )

        except Exception as e1:
            self.LogErrorLine("Error in ProcessFileWriteTransaction: " + str(e1))
            return ""

    def ProcessOneTransaction(
        self,
        MasterPacket: List[int],
        skipupdate: bool = False,
        ReturnString: bool = False,
        min_response_override: Optional[int] = None,
    ) -> str:
        """
        Executes a single Modbus transaction (Send/Receive).

        Args:
            MasterPacket (List[int]): The packet to send.
            skipupdate (bool): If True, don't update internal register cache.
            ReturnString (bool): If True, return value as ASCII string.
            min_response_override (int, optional): Minimum expected response length.

        Returns:
            str: Register value string (hex or ASCII), or empty string on error.
        """
        try:
            if self.ModbusTCP:
                PacketOffset = self.MODBUS_TCP_HEADER_SIZE
            else:
                PacketOffset = 0

            with self.CommAccessLock:  # this lock should allow calls from multiple threads

                if len(self.Slave.Buffer):
                    self.UnexpectedData += 1
                    self.LogError("Flushing, unexpected data. Likely timeout.")
                    self.Flush()
                self.SendPacketAsMaster(MasterPacket)

                SentTime = datetime.datetime.now()
                while True:
                    # be kind to other processes
                    if self.SlowCPUOptimization:
                        time.sleep(0.03)
                    else:
                        time.sleep(0.01)

                    if self.IsStopping:
                        return ""
                    RetVal, SlavePacket = self.GetPacketFromSlave(
                        min_response_override=min_response_override
                    )

                    if RetVal is True and len(SlavePacket) != 0:  # we receive a packet
                        self.TotalElapsedPacketeTime += (
                            self.MillisecondsElapsed(SentTime) / 1000
                        )
                        break
                    if RetVal is False:
                        self.LogError(
                            "Error Receiving slave packet for register %04x"
                            % (
                                self.GetRegisterFromPacket(
                                    MasterPacket, offset=PacketOffset
                                )
                            )
                        )
                        # Errors returned here are logged in GetPacketFromSlave
                        time.sleep(1)
                        self.Flush()
                        return ""

                    msElapsed = self.MillisecondsElapsed(SentTime)
                    if msElapsed > self.ModBusPacketTimoutMS:
                        self.ComTimoutError += 1
                        self.LogError(
                            "Error: timeout receiving slave packet for register %04x Buffer: %d, sequence %d"
                            % (
                                self.GetRegisterFromPacket(
                                    MasterPacket, offset=PacketOffset
                                ),
                                len(self.Slave.Buffer),
                                self.TxPacketCount,
                            )
                        )
                        if len(self.Slave.Buffer):
                            self.LogHexList(self.Slave.Buffer, prefix="Buffer")
                        self.Flush()
                        return ""

                # update our cached register dict
                ReturnRegValue = self.UpdateRegistersFromPacket(
                    MasterPacket,
                    SlavePacket,
                    SkipUpdate=skipupdate,
                    ReturnString=ReturnString,
                )
                if ReturnRegValue == "Error":
                    self.LogHexList(MasterPacket, prefix="Master")
                    self.LogHexList(SlavePacket, prefix="Slave")
                    self.ComValidationError += 1
                    self.Flush()
                    ReturnRegValue = ""

            return ReturnRegValue

        except Exception as e1:
            self.LogErrorLine("Error in ProcessOneTransaction: " + str(e1))
            return ""

    def MillisecondsElapsed(self, ReferenceTime: datetime.datetime) -> float:
        """
        Calculates milliseconds elapsed since ReferenceTime.

        Args:
            ReferenceTime (datetime.datetime): Start time.

        Returns:
            float: Elapsed milliseconds.
        """
        CurrentTime = datetime.datetime.now()
        Delta = CurrentTime - ReferenceTime
        return Delta.total_seconds() * 1000

    def GetRegisterFromPacket(self, Packet: List[int], offset: int = 0) -> int:
        """
        Extracts the register address from a Modbus packet.

        Args:
            Packet (List[int]): The packet data.
            offset (int): Offset index (e.g. for TCP header).

        Returns:
            int: The extracted register address.
        """
        try:
            Register = 0

            if Packet[self.MBUS_OFF_COMMAND + offset] in [
                self.MBUS_CMD_READ_FILE,
                self.MBUS_CMD_WRITE_FILE,
            ]:
                Register = (
                    Packet[self.MBUS_OFF_FILE_RECORD_HI + offset] << 8
                    | Packet[self.MBUS_OFF_FILE_RECORD_LOW + offset] & 0x00FF
                )
            else:
                Register = (
                    Packet[self.MBUS_OFF_REGISTER_HI + offset] << 8
                    | Packet[self.MBUS_OFF_REGISTER_LOW + offset] & 0x00FF
                )
            return Register
        except Exception as e1:
            self.LogErrorLine("Error in GetRegisterFromPacket: " + str(e1))
            return Register

    def CreateMasterPacket(
        self,
        register: str,
        length: int = 1,
        command: Optional[int] = None,
        data: List[int] = [],
        file_num: int = 1,
    ) -> List[int]:
        """
        Constructs a Modbus master request packet.

        Args:
            register (str): Register address (hex string).
            length (int): Length of data/registers.
            command (int, optional): Modbus function code.
            data (List[int]): Data payload for writes.
            file_num (int): File number for file operations.

        Returns:
            List[int]: The constructed packet with CRC/Header.
        """
        Packet = []
        try:
            if command is None:
                command = self.MBUS_CMD_READ_HOLDING_REGS

            RegisterInt = int(register, 16)

            if RegisterInt < self.MIN_REGISTER or RegisterInt > self.MAX_REGISTER:
                self.ComValidationError += 1
                self.LogError(
                    "Validation Error: CreateMasterPacket maximum regiseter value exceeded: "
                    + str(register)
                )
                return []

            if file_num < self.MIN_FILE_NUMBER or file_num > self.MAX_FILE_NUMBER:
                self.ComValidationError += 1
                self.LogError("Validation Error: CreateMasterPacket maximum file number value exceeded: "+ str(file_num))
                return []

            if command in [self.MBUS_CMD_READ_FILE, self.MBUS_CMD_WRITE_FILE]:
                if (RegisterInt < self.MIN_FILE_RECORD_NUM
                    or RegisterInt > self.MAX_FILE_RECORD_NUM
                ):
                    self.ComValidationError += 1
                    self.LogError("Validation Error: CreateMasterPacket maximum regiseter (record number) value exceeded: " + str(register))
                    return []
                
            if command in [self.MBUS_CMD_WRITE_REGS, self.MBUS_CMD_WRITE_COILS, self.MBUS_CMD_WRITE_FILE]:
                if len(data) == 0:
                    self.LogError("Validation Error: CreateMasterPacket invalid length (1) %x %x"% (len(data), length))
                    self.ComValidationError += 1
                    return []
                if len(data) / 2 != length:
                    self.LogError("Validation Error: CreateMasterPacket invalid length (2) %x %x" % (len(data), length))
                    self.ComValidationError += 1
                    return []

            if command in [self.MBUS_CMD_WRITE_COIL, self.MBUS_CMD_WRITE_REG]:
                # must be only one word (2 bytes)
                if length != 1 or len(data) != 2:
                    self.LogError("Validation Error: CreateMasterPacket invalid length (3) %x %x"% (len(data), length))
                    self.ComValidationError += 1
                    return []

            if command == self.MBUS_CMD_READ_HOLDING_REGS or command == self.MBUS_CMD_READ_COILS or command == self.MBUS_CMD_READ_INPUT_REGS:
                Packet.append(self.Address)  # address
                Packet.append(command)  # command
                Packet.append(RegisterInt >> 8)  # reg high
                Packet.append(RegisterInt & 0x00FF)  # reg low
                Packet.append(length >> 8)  # length / num coils high 
                Packet.append(length & 0x00FF)  # length / num coils low
                CRCValue = self.GetCRC(Packet)
                if CRCValue is not None:
                    Packet.append(CRCValue & 0x00FF)  # CRC low
                    Packet.append(CRCValue >> 8)  # CRC high

            elif command == self.MBUS_CMD_WRITE_REGS:
                Packet.append(self.Address)  # address
                Packet.append(command)  # command
                Packet.append(RegisterInt >> 8)  # reg high
                Packet.append(RegisterInt & 0x00FF)  # reg low
                Packet.append(length >> 8)  # Num of Reg high
                Packet.append(length & 0x00FF)  # Num of Reg low
                Packet.append(len(data))  # byte count
                for b in range(0, len(data)):
                    Packet.append(data[b])  # data
                CRCValue = self.GetCRC(Packet)
                if CRCValue is not None:
                    Packet.append(CRCValue & 0x00FF)  # CRC low
                    Packet.append(CRCValue >> 8)  # CRC high

            elif command == self.MBUS_CMD_WRITE_COILS:
                Packet.append(self.Address)  # address
                Packet.append(command)  # command
                Packet.append(RegisterInt >> 8)  # reg high
                Packet.append(RegisterInt & 0x00FF)  # reg low
                Packet.append(length >> 8)  # Num of Reg high
                Packet.append(length & 0x00FF)  # Num of Reg low
                ByteCount = int(length / 8)
                if (length % 8 > 0):
                    ByteCount += 1
                Packet.append(ByteCount)  # byte count

                # Pack data bits
                ByteValue = 0
                bitindex = 0
                for byteindex in range(0, ByteCount):
                    odd_data = data[1::2]   # extract every other odd value from list to another list
                    even_data = data[::2]   # every other even value from list
                    BitValue = 1
                    # Logic seems to be checking pairs of bytes for 0?
                    if byteindex < len(even_data) and byteindex < len(odd_data):
                        if even_data[byteindex] == 0 and odd_data[byteindex] == 0:
                            BitValue = 0
                    ByteValue |= (BitValue << bitindex)
                    bitindex += 1
                    if bitindex < 7: # Should this reset per byte? This looks like a bug in original logic if coils > 8?
                        # Assuming standard modbus logic here is simplified or specific use case
                        # Original code: bitindex = 0 if < 7 ? No, it resets if bitindex reaches 8
                        pass # Logic preserved from original
                    if bitindex > 7:
                        bitindex = 0
                    Packet.append(ByteValue)  # data - Wait, append inside loop? ByteValue only appended when full?
                    # Original code logic: Packet.append(ByteValue) inside the loop.
                    # If ByteCount > 1, this loop runs ByteCount times.
                    # But bitindex is incremented. ByteValue accumulates.
                    # Packet append is inside loop. This implies ByteValue is appended ByteCount times?
                    # This looks suspicious but preserving logic as per instructions.

                CRCValue = self.GetCRC(Packet)
                if CRCValue is not None:
                    Packet.append(CRCValue & 0x00FF)  # CRC low
                    Packet.append(CRCValue >> 8)  # CRC high

            elif command in [self.MBUS_CMD_WRITE_COIL, self.MBUS_CMD_WRITE_REG]: # write single coil and write single holding 
                Packet.append(self.Address)  # address
                Packet.append(command)  # command
                Packet.append(RegisterInt >> 8)  # reg high
                Packet.append(RegisterInt & 0x00FF)  # reg low
                if command == self.MBUS_CMD_WRITE_COIL:
                    if data[0] != 0 or data[1] != 0:
                        # on
                        Packet.append(0xFF)
                        Packet.append(0x00)
                    else:
                        # off
                        Packet.append(0x00)
                        Packet.append(0x00)
                else:
                    Packet.append(data[0])
                    Packet.append(data[1])
                CRCValue = self.GetCRC(Packet)
                if CRCValue is not None:
                    Packet.append(CRCValue & 0x00FF)  # CRC low
                    Packet.append(CRCValue >> 8)  # CRC high

            elif command == self.MBUS_CMD_READ_FILE:
                # Note, we only support one sub request at at time
                Packet.append(self.Address)  # address
                Packet.append(command)  # command
                Packet.append(self.MBUS_READ_FILE_REQUEST_PAYLOAD_LENGTH)  # Byte count
                Packet.append(self.MBUS_FILE_TYPE_VALUE)  # always same value
                Packet.append(file_num >> 8)  # File Number hi
                Packet.append(file_num & 0x00FF)  # File Number low
                Packet.append(RegisterInt >> 8)  # register (file record number) high
                Packet.append(RegisterInt & 0x00FF)  # register (file record number) low
                Packet.append(length >> 8)  # Length to return hi
                Packet.append(length & 0x00FF)  # Length to return lo
                CRCValue = self.GetCRC(Packet)
                if CRCValue is not None:
                    Packet.append(CRCValue & 0x00FF)  # CRC low
                    Packet.append(CRCValue >> 8)  # CRC high
            elif command == self.MBUS_CMD_WRITE_FILE:
                # Note, we only support one sub request at at time
                Packet.append(self.Address)  # address
                Packet.append(command)  # command
                Packet.append(
                    length * 2 + self.MBUS_FILE_WRITE_REQ_SIZE_MINUS_LENGTH
                )  # packet payload size from here
                Packet.append(self.MBUS_FILE_TYPE_VALUE)  # always same value
                Packet.append(file_num >> 8)  # File Number hi
                Packet.append(file_num & 0x00FF)  # File Number low
                Packet.append(RegisterInt >> 8)  # register (file record number) high
                Packet.append(RegisterInt & 0x00FF)  # register (file record number) low
                Packet.append(length >> 8)  # Length to return hi
                Packet.append(length & 0x00FF)  # Length to return lo
                for b in range(0, len(data)):
                    Packet.append(data[b])  # data
                CRCValue = self.GetCRC(Packet)
                if CRCValue is not None:
                    Packet.append(CRCValue & 0x00FF)  # CRC low
                    Packet.append(CRCValue >> 8)  # CRC high

            else:
                self.LogError("Validation Error: Invalid command in CreateMasterPacket!")
                self.ComValidationError += 1
                return []
        except Exception as e1:
            self.LogErrorLine("Error in CreateMasterPacket: " + str(e1))

        if len(Packet) > self.MAX_MODBUS_PACKET_SIZE:
            self.LogError(
                "Validation Error: CreateMasterPacket: Packet size exceeds max size"
            )
            self.ComValidationError += 1
            return []

        if self.ModbusTCP:
            return self.ConvertToModbusModbusTCP(Packet)
        return Packet

    def GetTransactionID(self) -> int:
        """
        Generates a new Transaction ID for Modbus TCP.

        Returns:
            int: The new Transaction ID.
        """
        ID = self.TransactionID
        self.CurrentTransactionID = ID
        self.TransactionID += 1
        if self.TransactionID > 0xFFFF:
            self.TransactionID = 0

        return ID

    def ConvertToModbusModbusTCP(self, Packet: List[int]) -> List[int]:
        """
        Wraps a Modbus RTU packet in a Modbus TCP Header.

        Args:
            Packet (List[int]): The RTU packet.

        Returns:
            List[int]: The TCP packet.
        """
        # byte 0:   transaction identifier - copied by server - usually 0
        # byte 1:   transaction identifier - copied by server - usually 0
        # byte 2:   protocol identifier = 0
        # byte 3:   protocol identifier = 0
        # byte 4:   length field (upper byte) = 0 (since all messages are smaller than 256)
        # byte 5:   length field (lower byte) = number of bytes following
        # byte 6:   unit identifier (previously 'slave address')
        # byte 7:   MODBUS function code
        # byte 8 on:    data as needed
        try:
            if not self.ModbusTCP:
                return Packet
            # remove last two bytes of CRC
            if len(Packet) >= 2:
                Packet.pop()
                Packet.pop()

            length = len(Packet)
            # byte 6 (slave address) is already provided in the Packet argument (it's the first byte of remaining packet)

            # TCP Header insertion
            Packet.insert(
                0, length & 0xFF
            )  # byte 5:   length field (lower byte) = number of bytes following
            Packet.insert(
                0, (length & 0xFF00) >> 8
            )  # byte 4:   length field (upper byte) = 0 (since all messages are smaller than 256)
            Packet.insert(0, 0)  # byte 3:   protocol identifier = 0
            Packet.insert(0, 0)  # byte 2:   protocol identifier = 0
            TransactionID = self.GetTransactionID()
            Packet.insert(
                0, TransactionID & 0xFF
            )  # byte 1:   transaction identifier (low)- copied by server - usually 0
            Packet.insert(
                0, (TransactionID & 0xFF00) >> 8
            )  # byte 0:   transaction identifier (high)- copied by server - usually 0
            return Packet
        except Exception as e1:
            self.LogErrorLine("Error in CreateModbusTCPHeader: " + str(e1))
            return []

    def SendPacketAsMaster(self, Packet: List[int]) -> None:
        """
        Sends a packet via the slave interface.

        Args:
            Packet (List[int]): Packet data.
        """
        try:
            ByteArray = bytearray(Packet)
            self.TxPacketCount += 1
            self.Slave.Write(ByteArray)
        except Exception as e1:
            self.LogErrorLine("Error in SendPacketAsMaster: " + str(e1))
            self.LogHexList(Packet, prefix="Packet")

    def UpdateRegistersFromPacket(
        self,
        MasterPacket: List[int],
        SlavePacket: List[int],
        SkipUpdate: bool = False,
        ReturnString: bool = False,
    ) -> str:
        """
        Updates the internal register cache based on a completed transaction.

        Wrapper for _URFP.

        Args:
            MasterPacket (List[int]): The request packet.
            SlavePacket (List[int]): The response packet.
            SkipUpdate (bool): Skip cache update.
            ReturnString (bool): Return as string.

        Returns:
            str: Register value.
        """
        return self._URFP(MasterPacket, SlavePacket, SkipUpdate, ReturnString)

    def _URFP(
        self,
        MasterPacket: List[int],
        SlavePacket: List[int],
        SkipUpdate: bool = False,
        ReturnString: bool = False,
    ) -> str:
        """
        Internal implementation of UpdateRegistersFromPacket.

        Validates packet matching and extracts data.

        Args:
            MasterPacket (List[int]): Request packet.
            SlavePacket (List[int]): Response packet.
            SkipUpdate (bool): Skip update.
            ReturnString (bool): Return string format.

        Returns:
            str: The extracted value or "Error".
        """
        try:

            if (
                len(MasterPacket) < self.MIN_PACKET_RESPONSE_LENGTH
                or len(SlavePacket) < self.MIN_PACKET_RESPONSE_LENGTH
            ):
                self.LogError(
                    "Validation Error, length: Master "
                    + str(len(MasterPacket))
                    + " Slave: "
                    + str(len(SlavePacket))
                )
                return "Error"

            if self.ModbusTCP:
                PacketOffset = self.MODBUS_TCP_HEADER_SIZE
            else:
                PacketOffset = 0

            if MasterPacket[self.MBUS_OFF_ADDRESS + PacketOffset] != self.Address:
                self.LogError(
                    "Validation Error: Invalid address in UpdateRegistersFromPacket (Master)"
                )
                return "Error"
            if not self.CheckResponseAddress(SlavePacket[self.MBUS_OFF_ADDRESS]):
                self.LogError(
                    "Validation Error: Invalid address in UpdateRegistersFromPacket (Slave)"
                )
                return "Error"

            ValidCommands = [
                self.MBUS_CMD_READ_COILS,
                self.MBUS_CMD_READ_INPUT_REGS,
                self.MBUS_CMD_READ_HOLDING_REGS,
                self.MBUS_CMD_WRITE_REGS,
                self.MBUS_CMD_WRITE_COILS,
                self.MBUS_CMD_READ_FILE,
                self.MBUS_CMD_WRITE_FILE,
                self.MBUS_CMD_WRITE_COIL,
                self.MBUS_CMD_WRITE_REG
            ]

            if SlavePacket[self.MBUS_OFF_COMMAND] not in ValidCommands:
                self.LogError(
                    "Validation Error: Unknown Function slave %02x %02x"
                    % (
                        SlavePacket[self.MBUS_OFF_ADDRESS],
                        SlavePacket[self.MBUS_OFF_COMMAND],
                    )
                )
                return "Error"

            if MasterPacket[self.MBUS_OFF_COMMAND + PacketOffset] not in ValidCommands:
                self.LogError(
                    "Validation Error: Unknown Function master %02x %02x"
                    % (
                        MasterPacket[self.MBUS_OFF_ADDRESS],
                        MasterPacket[self.MBUS_OFF_COMMAND],
                    )
                )
                return "Error"

            if (
                MasterPacket[self.MBUS_OFF_COMMAND + PacketOffset]
                != SlavePacket[self.MBUS_OFF_COMMAND]
            ):
                self.LogError(
                    "Validation Error: Command Mismatch :"
                    + str(MasterPacket[self.MBUS_OFF_COMMAND])
                    + ":"
                    + str(SlavePacket[self.MBUS_OFF_COMMAND])
                )
                return "Error"

            # get register from master packet
            Register = "%04x" % (
                self.GetRegisterFromPacket(MasterPacket, offset=PacketOffset)
            )

            if MasterPacket[self.MBUS_OFF_COMMAND + PacketOffset] in [
                self.MBUS_CMD_WRITE_REGS,
                self.MBUS_CMD_WRITE_FILE,
            ]:
                # get register from slave packet
                SlaveRegister = "%04x" % (self.GetRegisterFromPacket(SlavePacket))
                if SlaveRegister != Register:
                    self.LogError(
                        "Validation Error: Master Slave Register Mismatch : "
                        + Register
                        + ":"
                        + SlaveRegister
                    )
                    return "Error"

            RegisterValue = ""
            RegisterStringValue = ""
            if (MasterPacket[self.MBUS_OFF_COMMAND + PacketOffset] == self.MBUS_CMD_READ_HOLDING_REGS or
                MasterPacket[self.MBUS_OFF_COMMAND + PacketOffset] == self.MBUS_CMD_READ_INPUT_REGS or
                MasterPacket[self.MBUS_OFF_COMMAND + PacketOffset] == self.MBUS_CMD_READ_COILS
            ):
                IsCoil = False      # Mobus funciton 01
                IsInput = False     # Modubs function 04
                # get value from slave packet
                length = SlavePacket[self.MBUS_OFF_RESPONSE_LEN]
                if MasterPacket[self.MBUS_OFF_COMMAND + PacketOffset] == self.MBUS_CMD_READ_COILS:
                    IsCoil = True
                elif MasterPacket[self.MBUS_OFF_COMMAND + PacketOffset] == self.MBUS_CMD_READ_INPUT_REGS:
                    IsInput = True
                if (length + self.MBUS_RES_PAYLOAD_SIZE_MINUS_LENGTH) > len(
                    SlavePacket
                ):
                    self.LogError(
                        "Validation Error: Slave Length : "
                        + str(length)
                        + ":"
                        + str(len(SlavePacket))
                    )
                    return "Error"

                for i in range(3, length + 3):
                    RegisterValue += "%02x" % SlavePacket[i]
                    if ReturnString:
                        if SlavePacket[i]:
                            RegisterStringValue += chr(SlavePacket[i])
                # update register list
                if not SkipUpdate:
                    if self.UpdateRegisterList is not None:
                        if not ReturnString:
                            if not self.UpdateRegisterList(Register, RegisterValue, IsCoil = IsCoil, IsInput = IsInput):
                                self.ComSyncError += 1
                                return "Error"
                        else:
                            if not self.UpdateRegisterList(Register, RegisterStringValue, IsString=True, IsCoil = IsCoil, IsInput = IsInput):
                                self.ComSyncError += 1
                                return "Error"

            if (
                MasterPacket[self.MBUS_OFF_COMMAND + PacketOffset]
                == self.MBUS_CMD_READ_FILE
            ):
                payloadLen = SlavePacket[self.MBUS_OFF_FILE_PAYLOAD_LEN]
                if not self.AlternateFileProtocol:
                    # TODO This is emperical
                    payloadLen -= 1
                for i in range(
                    self.MBUS_OFF_FILE_PAYLOAD,
                    (self.MBUS_OFF_FILE_PAYLOAD + payloadLen),
                ):
                    RegisterValue += "%02x" % SlavePacket[i]
                    if ReturnString:
                        if SlavePacket[i]:
                            RegisterStringValue += chr(SlavePacket[i])

                if not SkipUpdate:
                    if not ReturnString:
                        if not self.UpdateRegisterList(
                            Register, RegisterValue, IsFile=True
                        ):
                            self.ComSyncError += 1
                            return "Error"
                    else:
                        if not self.UpdateRegisterList(
                            Register, RegisterStringValue, IsString=True, IsFile=True
                        ):
                            self.ComSyncError += 1
                            return "Error"

            if ReturnString:
                return str(RegisterStringValue)
            return str(RegisterValue)
        except Exception as e1:
            self.LogErrorLine("Error in UpdateRegistersFromPacket: " + str(e1))
            return "Error"

    def CheckCRC(self, Packet: List[int]) -> bool:
        """
        Verifies the CRC of a packet.

        Args:
            Packet (List[int]): The packet data including CRC.

        Returns:
            bool: True if CRC is valid, False otherwise.
        """
        try:
            if self.ModbusTCP:
                return True

            if len(Packet) == 0:
                return False
            ByteArray = bytearray(Packet[: len(Packet) - 2])

            if sys.version_info[0] < 3:
                results = self.ModbusCrc(str(ByteArray))
            else:  # PYTHON3
                results = self.ModbusCrc(ByteArray)

            CRCValue = ((Packet[-1] & 0xFF) << 8) | (Packet[-2] & 0xFF)
            if results != CRCValue:
                self.LogError(
                    "Data Error: CRC check failed: %04x  %04x" % (results, CRCValue)
                )
                return False
            return True
        except Exception as e1:
            self.LogErrorLine("Error in CheckCRC: " + str(e1))
            self.LogHexList(Packet, prefix="Packet")
            return False

    def GetCRC(self, Packet: List[int]) -> Optional[int]:
        """
        Calculates CRC for a packet.

        Args:
            Packet (List[int]): Packet data.

        Returns:
            Optional[int]: Calculated CRC value or None on error.
        """
        try:
            if len(Packet) == 0:
                return None
            ByteArray = bytearray(Packet)

            if sys.version_info[0] < 3:
                results = self.ModbusCrc(str(ByteArray))
            else:  # PYTHON3
                results = self.ModbusCrc(ByteArray)

            return results
        except Exception as e1:
            self.LogErrorLine("Error in GetCRC: " + str(e1))
            self.LogHexList(Packet, prefix="Packet")
            return None

    def GetCommStats(self) -> List[Dict[str, Any]]:
        """
        Retrieves communication statistics.

        Returns:
            List[Dict[str, Any]]: List of statistics dictionaries.
        """
        SerialStats = []

        try:
            SerialStats.append(
                {
                    "Packet Count": "M: %d, S: %d"
                    % (self.TxPacketCount, self.RxPacketCount)
                }
            )

            if self.CrcError == 0 or self.TxPacketCount == 0:
                PercentErrors = 0.0
            else:
                PercentErrors = float(self.CrcError) / float(self.TxPacketCount)

            if self.ComTimoutError == 0 or self.TxPacketCount == 0:
                PercentTimeoutErrors = 0.0
            else:
                PercentTimeoutErrors = float(self.ComTimoutError) / float(
                    self.TxPacketCount
                )

            SerialStats.append({"CRC Errors": "%d " % self.CrcError})
            SerialStats.append(
                {"CRC Percent Errors": ("%.2f" % (PercentErrors * 100)) + "%"}
            )
            SerialStats.append({"Timeout Errors": "%d" % self.ComTimoutError})
            SerialStats.append(
                {
                    "Timeout Percent Errors": ("%.2f" % (PercentTimeoutErrors * 100))
                    + "%"
                }
            )
            SerialStats.append({"Modbus Exceptions": self.ModbusException})
            SerialStats.append({"Validation Errors": self.ComValidationError})
            SerialStats.append({"Sync Errors": self.ComSyncError})
            SerialStats.append({"Invalid Data": self.UnexpectedData})
            # add serial stats
            SerialStats.append({"Discarded Bytes": "%d" % self.Slave.DiscardedBytes})
            SerialStats.append({"Comm Restarts": "%d" % self.Slave.Restarts})

            CurrentTime = datetime.datetime.now()

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
            if not self.UseTCP:
                SerialStats.append({"Modbus Transport": "Serial"})
                SerialStats.append({"Serial Data Rate": "%d" % (self.Slave.BaudRate)})
            else:
                SerialStats.append({"Modbus Transport": "TCP"})
        except Exception as e1:
            self.LogErrorLine("Error in GetCommStats: " + str(e1))
        return SerialStats

    def ResetCommStats(self) -> None:
        """
        Resets communication statistics.
        """
        try:
            self.RxPacketCount = 0
            self.TxPacketCount = 0
            self.TotalElapsedPacketeTime = 0
            self.ModbusStartTime = datetime.datetime.now()  # used for com metrics
            self.Slave.ResetSerialStats()
        except Exception as e1:
            self.LogErrorLine("Error in ResetCommStats: " + str(e1))

    def Flush(self) -> None:
        """
        Flushes the underlying communication device.
        """
        with self.CommAccessLock:
            self.Slave.Flush()

    def Close(self) -> None:
        """
        Closes the Modbus protocol handler and slave device.
        """
        self.IsStopping = True
        with self.CommAccessLock:
            self.Slave.Close()
