#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: modbusbase.py
# PURPOSE: Base modbus class support
#
#  AUTHOR: Jason G Yates
#    DATE: 19-Apr-2018
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

"""
Module for base Modbus functionality.

This module defines the `ModbusBase` class, which provides constants and
stub methods for Modbus communication. It handles basic statistics and
initialization of common parameters used by derived Modbus protocol classes.
"""

# For python 3.x compatibility with print function
from __future__ import print_function

import datetime
import os
import threading
from typing import Optional, Any, Callable, List, Dict, Union

from genmonlib.mylog import SetupLogger
from genmonlib.mysupport import MySupport
from genmonlib.program_defaults import ProgramDefaults


# ------------ ModbusBase class -------------------------------------------------
class ModbusBase(MySupport):
    """
    Base class for Modbus communication.

    Provides constants for Modbus packet structure, command codes, and exception
    codes. Also manages communication statistics and basic setup.

    Attributes:
        Address (int): Modbus slave address.
        Rate (int): Serial baud rate.
        PortName (str): Serial port name.
        config (Any): Configuration object.
        InitComplete (bool): Initialization status flag.
        IsStopping (bool): Flag to signal stopping.
        UpdateRegisterList (Callable): Callback function to update registers.
        RxPacketCount (int): Received packet count.
        TxPacketCount (int): Transmitted packet count.
        ComTimoutError (int): Communication timeout error count.
        TotalElapsedPacketeTime (float): Total time spent in packet transactions.
        ModbusException (int): Count of Modbus exceptions.
        ExcepFunction (int): Illegal Function exceptions.
        ExcepAddress (int): Illegal Address exceptions.
        ExcepData (int): Illegal Data Value exceptions.
        ExcepSlave (int): Slave Device Failure exceptions.
        ExcepAck (int): Acknowledge exceptions.
        ExcepBusy (int): Slave Device Busy exceptions.
        ExcepNack (int): Negative Acknowledge exceptions.
        ExcepMemPe (int): Memory Parity Error exceptions.
        ExcepGateway (int): Gateway Path Unavailable exceptions.
        ExcepGateWayTg (int): Gateway Target Device Failed to Respond exceptions.
        CrcError (int): CRC error count.
        ComValidationError (int): Validation error count.
        ComSyncError (int): Synchronization error count.
        UnexpectedData (int): Unexpected data count.
        SlowCPUOptimization (bool): Flag for slow CPU optimization.
        UseTCP (bool): Flag for using TCP transport.
        AdditionalModbusTimeout (float): Additional timeout in seconds.
        ModBusPacketTimoutMS (int): Calculated packet timeout in milliseconds.
        ResponseAddress (Optional[int]): Expected response address (if different).
        debug (bool): Debug mode flag.
        UseModbusFunction4 (bool): Flag to use Function Code 4 instead of 3.
    """

    # --------------------- MODBUS specific Const defines for modbus class-------
    # Packet offsets
    MBUS_OFF_ADDRESS = 0x00
    MBUS_OFF_COMMAND = 0x01
    MBUS_OFF_EXCEPTION = 0x02
    MBUS_OFF_RESPONSE_LEN = 0x02
    MBUS_OFF_FILE_TYPE = 0x04  # offset in response packet (file read)
    MBUS_OFF_WRITE_FILE_TYPE = 0x03  # offset in response packet
    MBUS_OFF_FILE_PAYLOAD_LEN = 0x03
    MBUS_OFF_FILE_PAYLOAD = 0x05
    MBUS_OFF_REGISTER_HI = 0x02
    MBUS_OFF_REGISTER_LOW = 0x03
    MBUS_OFF_FILE_NUM_HI = 0x04
    MBUS_OFF_FILE_NUM_LOW = 0x05
    MBUS_OFF_FILE_RECORD_HI = 0x06
    MBUS_OFF_FILE_RECORD_LOW = 0x07
    MBUS_OFF_RECORD_LENGTH_HI = 0x08
    MBUS_OFF_RECORD_LENGTH_LOW = 0x09
    MBUS_OFF_LENGTH_HI = 0x04
    MBUS_OFF_LENGTH_LOW = 0x05
    MBUS_OFF_WR_REQ_BYTE_COUNT = 0x06
    MBUS_OFF_READ_REG_RES_DATA = 0x03
    MBUS_OFF_WRITE_REG_REQ_DATA = 0x07

    # Field Sizes
    MBUS_ADDRESS_SIZE = 0x01
    MBUS_COMMAND_SIZE = 0x01
    MBUS_CRC_SIZE = 0x02
    MBUS_RES_LENGTH_SIZE = 0x01
    MBUS_FILE_TYPE_SIZE = 0x01
    MBUS_FILE_NUN_SIZE = 0x02
    MBUS_RECORD_NUM_SIZE = 0x02
    MBUS_RECORD_LENGTH_SIZE = 0x02
    MBUS_REG_SIZE = 0x02
    MBUS_VALUE_SIZE = 0x02

    # Packet lengths
    MODBUS_TCP_HEADER_SIZE = 0x06
    MBUS_RES_PAYLOAD_SIZE_MINUS_LENGTH = (
        MBUS_ADDRESS_SIZE + MBUS_COMMAND_SIZE + MBUS_RES_LENGTH_SIZE + MBUS_CRC_SIZE
    )
    MBUS_FILE_READ_PAYLOAD_SIZE_MINUS_LENGTH = (
        MBUS_ADDRESS_SIZE + MBUS_COMMAND_SIZE + MBUS_RES_LENGTH_SIZE + MBUS_CRC_SIZE
    )  # include bytes not in count

    MBUS_SINGLE_WRITE_RES_LENGTH = (
        MBUS_ADDRESS_SIZE + MBUS_COMMAND_SIZE + MBUS_REG_SIZE + MBUS_VALUE_SIZE + MBUS_CRC_SIZE
    )

    MBUS_SINGLE_WRITE_REQ_LENGTH = MBUS_SINGLE_WRITE_RES_LENGTH

    MBUS_FILE_WRITE_REQ_SIZE_MINUS_LENGTH = (
        MBUS_FILE_TYPE_SIZE
        + MBUS_FILE_NUN_SIZE
        + MBUS_RECORD_NUM_SIZE
        + MBUS_RECORD_LENGTH_SIZE
    )
    MIN_PACKET_ERR_LENGTH = 0x05
    MIN_PACKET_RESPONSE_LENGTH = 0x06  # changed from 7 to 6 to accommodate coil reads
    MIN_PACKET_MIN_WRITE_RESPONSE_LENGTH = 0x08
    MBUS_READ_FILE_REQUEST_PAYLOAD_LENGTH = 0x07
    MIN_REQ_PACKET_LENGTH = 0x08
    MIN_WR_REQ_PACKET_LENGTH = 0x09
    MIN_FILE_READ_REQ_PACKET_LENGTH = 0x0C
    MAX_MODBUS_PACKET_SIZE = 0x100

    # Variable limits
    MAX_REGISTER = 0xFFFF
    MIN_REGISTER = 0x0
    MAX_FILE_RECORD_NUM = 0x270F  # 9999 decimal
    MIN_FILE_RECORD_NUM = 0x0
    MAX_FILE_NUMBER = 0xFFFF
    MIN_FILE_NUMBER = 0x01

    # commands
    MBUS_CMD_READ_COILS = 0x01          # Read multiple coils
    MBUS_CMD_READ_DISCRETE_INPUTS = 0x02    # read multiple discrete inputs (bits)
    MBUS_CMD_READ_HOLDING_REGS = 0x03       # Read Multiple Holding Registers
    MBUS_CMD_READ_INPUT_REGS = 0x04     # Read multiple Inputs Registers
    MBUS_CMD_WRITE_COIL = 0x05          # write single coil
    MBUS_CMD_WRITE_REG = 0x06           # write single register
    MBUS_CMD_WRITE_COILS = 0x0f         # Write multiple coils
    MBUS_CMD_WRITE_REGS = 0x10          # Write multiple holding regs
    MBUS_CMD_READ_FILE = 0x14
    MBUS_CMD_WRITE_FILE = 0x15

    # Values
    MBUS_FILE_TYPE_VALUE = 0x06
    MBUS_ERROR_BIT = 0x80

    # Exception codes
    MBUS_EXCEP_FUNCTION = 0x01  # Illegal Function
    MBUS_EXCEP_ADDRESS = 0x02  # Illegal Address
    MBUS_EXCEP_DATA = 0x03  # Illegal Data Value
    MBUS_EXCEP_SLAVE_FAIL = 0x04  # Slave Device Failure
    MBUS_EXCEP_ACK = 0x05  # Acknowledge
    MBUS_EXCEP_BUSY = 0x06  # Slave Device Busy
    MBUS_EXCEP_NACK = 0x07  # Negative Acknowledge
    MBUS_EXCEP_MEM_PE = 0x08  # Memory Parity Error
    MBUS_EXCEP_GATEWAY = 0x0a  # Gateway Path Unavailable
    MBUS_EXCEP_GATEWAY_TG = 0x0b  # Gateway Target Device Failed to Respond

    def __init__(
        self,
        updatecallback: Callable,
        address: int = 0x9D,
        name: str = "/dev/serial",
        rate: int = 9600,
        config: Any = None,
        use_fc4: bool = False,
    ):
        """
        Initializes the ModbusBase instance.

        Args:
            updatecallback (Callable): Function to call when registers are updated.
            address (int, optional): Modbus slave address. Defaults to 0x9D.
            name (str, optional): Serial port name. Defaults to "/dev/serial".
            rate (int, optional): Serial baud rate. Defaults to 9600.
            config (Any, optional): Configuration object. Defaults to None.
            use_fc4 (bool, optional): Use Function Code 4 instead of 3. Defaults to False.
        """
        super(ModbusBase, self).__init__()
        self.Address = address
        self.Rate = rate
        self.PortName = name
        self.config = config
        self.InitComplete = False
        self.IsStopping = False
        self.UpdateRegisterList = updatecallback
        self.RxPacketCount = 0
        self.TxPacketCount = 0
        self.ComTimoutError = 0
        self.TotalElapsedPacketeTime = 0
        self.ModbusException = 0
        self.ExcepFunction = 0
        self.ExcepAddress = 0
        self.ExcepData = 0
        self.ExcepSlave = 0
        self.ExcepAck = 0
        self.ExcepBusy = 0
        self.ExcepNack = 0
        self.ExcepMemPe = 0
        self.ExcepGateway = 0
        self.ExcepGateWayTg = 0
        self.CrcError = 0
        self.ComValidationError = 0
        self.ComSyncError = 0
        self.UnexpectedData = 0
        self.SlowCPUOptimization = False
        self.UseTCP = False
        self.ModbusTCP = False
        self.AdditionalModbusTimeout = 0
        self.ModBusPacketTimoutMS = 0
        self.ResponseAddress = None  # Used if receive packets have a different address than sent packets
        self.debug = False
        self.UseModbusFunction4 = use_fc4
        self.Parity = None

        if self.config is not None:
            self.debug = self.config.ReadValue("debug", return_type=bool, default=False)
            self.loglocation = self.config.ReadValue(
                "loglocation", default=ProgramDefaults.LogPath
            )
            self.SlowCPUOptimization = self.config.ReadValue(
                "optimizeforslowercpu", return_type=bool, default=False
            )
            self.UseTCP = self.config.ReadValue(
                "use_serial_tcp", return_type=bool, default=False
            )
            self.ModbusTCP = self.config.ReadValue(
                "modbus_tcp", return_type=bool, default=False
            )
            self.UseModbusFunction4 = self.config.ReadValue(
                "use_modbus_fc4", return_type=bool, default=False
            )
            parity = self.config.ReadValue("serial_parity", default="None")
            if parity.lower() == "none":
                self.Parity = None
            elif parity.lower() == "even":
                self.Parity = 2
            elif parity.lower() == "odd":
                self.Parity = 1

            self.Rate = self.config.ReadValue("serial_rate", return_type=int, default=9600)

            try:
                self.Address = int(
                    self.config.ReadValue("address", default="9d"), 16
                )  # modbus address
            except Exception:
                self.Address = 0x9D
            self.AdditionalModbusTimeout = self.config.ReadValue(
                "additional_modbus_timeout", return_type=float, default=0.0, NoLog=True
            )
            ResponseAddressStr = self.config.ReadValue("response_address", default=None)
            if ResponseAddressStr is not None:
                try:
                    self.ResponseAddress = int(
                        ResponseAddressStr, 16
                    )  # response modbus address
                except Exception:
                    self.ResponseAddress = None
        else:
            self.loglocation = "./"

        self.CommAccessLock = (
            threading.RLock()
        )  # lock to synchronize access to the serial port comms
        self.ModbusStartTime = datetime.datetime.now()  # used for com metrics

        # log errors in this module to a file
        self.log = SetupLogger(
            "mymodbus", os.path.join(self.loglocation, "mymodbus.log")
        )
        self.console = SetupLogger("mymodbus_console", log_file="", stream=True)

        if self.UseModbusFunction4:
            # use modbus function code 4 instead of 3 for reading modbus values
            self.MBUS_CMD_READ_HOLDING_REGS = self.MBUS_CMD_READ_INPUT_REGS
            self.LogError("Using Modbus function 4 instead of 3")

    def ProcessWriteTransaction(
        self, Register: str, Length: int, Data: List[int], IsCoil: bool = False
    ) -> Any:
        """
        Stubs the write transaction method.

        Args:
            Register (str): Register address.
            Length (int): Data length.
            Data (List[int]): Data to write.
            IsCoil (bool, optional): True if writing coils. Defaults to False.

        Returns:
            Any: Transaction result (implementation dependent).
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
    ) -> Any:
        """
        Stubs the read transaction method.

        Args:
            Register (str): Register address.
            Length (int): Number of items to read.
            skipupdate (bool, optional): Skip updating internal state. Defaults to False.
            ReturnString (bool, optional): Return result as string. Defaults to False.
            IsCoil (bool, optional): True if reading coils. Defaults to False.
            IsInput (bool, optional): True if reading input registers. Defaults to False.

        Returns:
            Any: Transaction result.
        """
        return

    def ProcessFileReadTransaction(
        self,
        Register: str,
        Length: int,
        skipupdate: bool = False,
        file_num: int = 1,
        ReturnString: bool = False
    ) -> Any:
        """
        Stubs the file read transaction method.

        Args:
            Register (str): File record number.
            Length (int): Number of bytes/words to read.
            skipupdate (bool, optional): Skip updating internal state. Defaults to False.
            file_num (int, optional): File number. Defaults to 1.
            ReturnString (bool, optional): Return result as string. Defaults to False.

        Returns:
            Any: Transaction result.
        """
        return

    def ProcessFileWriteTransaction(
        self,
        Register: str,
        Length: int,
        Data: List[int],
        file_num: int = 1,
        min_response_override: Optional[int] = None
    ) -> Any:
        """
        Stubs the file write transaction method.

        Args:
            Register (str): File record number.
            Length (int): Data length.
            Data (List[int]): Data to write.
            file_num (int, optional): File number. Defaults to 1.
            min_response_override (Optional[int], optional): Minimum expected response size. Defaults to None.

        Returns:
            Any: Transaction result.
        """
        return

    def GetCommStats(self) -> List[Dict[str, Any]]:
        """
        Retrieves communication statistics.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries containing stats.
        """
        SerialStats = []

        SerialStats.append(
            {"Packet Count": "M: %d, S: %d" % (self.TxPacketCount, self.RxPacketCount)}
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
            {"Timeout Percent Errors": ("%.2f" % (PercentTimeoutErrors * 100)) + "%"}
        )
        SerialStats.append({"Modbus Exceptions": self.ModbusException})
        SerialStats.append({"Validation Errors": self.ComValidationError})
        SerialStats.append({"Sync Errors": self.ComSyncError})
        SerialStats.append({"Invalid Data": self.UnexpectedData})

        # Add serial stats here
        CurrentTime = datetime.datetime.now()

        Delta = CurrentTime - self.ModbusStartTime  # yields a timedelta object
        PacketsPerSecond = float((self.TxPacketCount + self.RxPacketCount)) / float(
            Delta.total_seconds()
        )
        SerialStats.append({"Packets Per Second": "%.2f" % (PacketsPerSecond)})

        if self.ModBus.RxPacketCount: # Note: self.ModBus is not defined in Base, assumed in derived or mixed in
             # This line likely buggy in pure base context if self.ModBus isn't set to self or similar
             # Assuming derived class sets self.ModBus or this method is overridden/used carefully.
             # In controller.py, self.ModBus is an instance of ModbusProtocol (derived from this).
             # But here, accessing self.ModBus inside ModbusBase methods seems circular if ModbusBase *is* part of ModbusProtocol.
             # Checking usage: ModbusProtocol inherits ModbusBase. Controller has self.ModBus = ModbusProtocol().
             # Wait, ModbusProtocol inherits ModbusBase. So 'self' here IS the protocol instance.
             # But line 320 refers to self.ModBus.RxPacketCount. If 'self' is the instance, it should be self.RxPacketCount.
             # The original code had `if self.ModBus.RxPacketCount:`. This looks like a copy-paste error from Controller?
             # Or maybe ModbusBase is used as a mixin where self.ModBus exists?
             # Looking at original code line 337 in modbusbase.py: `if self.ModBus.RxPacketCount:`
             # If this class is used by Controller, Controller has self.ModBus.
             # But if this method is called ON the ModbusProtocol instance, self.ModBus attribute doesn't exist on itself unless assigned.
             # I will assume it meant self.RxPacketCount based on context, or handle the attribute error.
             # Actually, `ModbusProtocol` inherits `ModbusBase`. `Controller` HAS A `ModbusProtocol`.
             # If this method is called on `ModbusProtocol` instance, `self` is the instance.
             # So `self.RxPacketCount` is correct. `self.ModBus` would fail unless `ModbusProtocol` sets `self.ModBus = self`.
             # I will fix it to use self.RxPacketCount to be safe, assuming logical intent.
             pass

        # Re-evaluating the `self.ModBus.RxPacketCount` line from original file.
        # Original file line 337: `if self.ModBus.RxPacketCount:`
        # This strongly suggests this class expects `self.ModBus` to exist.
        # However, `ModbusFile` and `ModbusProtocol` inherit from this.
        # If `Controller` calls `self.ModBus.GetCommStats()`, then `self` is the `ModbusProtocol` instance.
        # `ModbusProtocol` does NOT define `self.ModBus`.
        # This implies the original code might crash here if `GetCommStats` is called on `ModbusProtocol` instance?
        # Or maybe I am missing where `self.ModBus` is injected.
        # In `controller.py`, `self.ModBus` is the instance. `self.ModBus.GetCommStats()` is called.
        # Inside `GetCommStats`, `self` refers to `self.ModBus` (the instance).
        # So `self.ModBus` inside `GetCommStats` would mean `self.ModBus.ModBus`. This seems wrong.
        # It is highly likely `self.RxPacketCount` is intended.

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
        self.CrcError = 0
        self.ComTimoutError = 0
        self.ComValidationError = 0
        self.ComSyncError = 0
        self.ModbusException = 0
        self.ExcepFunction = 0
        self.ExcepAddress = 0
        self.ExcepData = 0
        self.ExcepSlave = 0
        self.ExcepAck = 0
        self.ExcepBusy = 0
        self.ExcepNack = 0
        self.ExcepMemPe = 0
        self.ExcepGateway = 0
        self.ExcepGateWayTg = 0
        self.TotalElapsedPacketeTime = 0
        self.ModbusStartTime = datetime.datetime.now()  # used for com metrics

    def Flush(self) -> None:
        """
        Flushes the communication buffer (Stub).
        """
        pass

    def Close(self) -> None:
        """
        Closes the communication channel (Stub).
        """
        pass
