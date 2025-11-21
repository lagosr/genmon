#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: mysupport.py
# PURPOSE: support functions in major classes
#
#  AUTHOR: Jason G Yates
#    DATE: 21-Apr-2018
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

"""
Module containing the `MySupport` class which provides utility functions
including file operations, network status, thread management, and
regular expression validation.
"""

import collections
import getopt
import os
import socket
import sys
import threading
import time
import re
from typing import Optional, List, Dict, Union, Any, Tuple

from genmonlib.mycommon import MyCommon
from genmonlib.myconfig import MyConfig
from genmonlib.mylog import SetupLogger
from genmonlib.myplatform import MyPlatform
from genmonlib.program_defaults import ProgramDefaults

# Fix Python 2.x. unicode type
if sys.version_info[0] >= 3:  # PYTHON 3
    unicode = str


class MySupport(MyCommon):
    """
    A support class providing miscellaneous utility methods.

    Inherits from `MyCommon`.

    Attributes:
        Simulation (bool): Flag to indicate if running in simulation mode.
        CriticalLock (threading.Lock): A lock for critical operations.
    """

    def __init__(self, simulation: bool = False):
        """
        Initializes the MySupport instance.

        Args:
            simulation (bool, optional): Simulation mode flag. Defaults to False.
        """
        super(MySupport, self).__init__()
        self.Simulation: bool = simulation
        self.CriticalLock: threading.Lock = threading.Lock()  # Critical Lock (writing conf file)

    def LogToFile(self, File: str, *argv: str) -> str:
        """
        Logs arguments to a specified CSV-style file.

        Args:
            File (str): The path to the log file.
            *argv (str): Variable number of string arguments to log.

        Returns:
            str: Empty string.
        """
        if self.Simulation:
            return ""
        if not len(File):
            return ""

        if not len(argv):
            return ""
        try:
            modarg = []
            # remove any non printable chars
            for arg in argv:
                arg = self.removeNonPrintable(arg)
                if len(arg):
                    modarg.append(arg)
            outdata = ","
            outdata = outdata.join(modarg) + "\n"
            with open(File, "a") as LogFile:  # opens file
                LogFile.write(outdata)
                LogFile.flush()
        except Exception as e1:
            self.LogError("Error in  LogToFile : File: %s: %s " % (File, str(e1)))
        return ""

    @staticmethod
    def CopyFile(
        source: str, destination: str, move: bool = False, log: Any = None
    ) -> bool:
        """
        Copies or moves a file from source to destination.

        Args:
            source (str): Source file path.
            destination (str): Destination file path.
            move (bool, optional): If True, removes source after copy.
                Defaults to False.
            log (Any, optional): Logger instance for error reporting.

        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            if not os.path.isfile(source):
                if log is not None:
                    log.error("Error in CopyFile : source file not found.")
                return False

            path = os.path.dirname(destination)
            if not os.path.isdir(path):
                if log is not None:
                    log.error("Creating " + path)
                os.mkdir(path)
            with os.fdopen(os.open(source, os.O_RDONLY), "r") as source_fd:
                data = source_fd.read()
                with os.fdopen(
                    os.open(destination, os.O_CREAT | os.O_RDWR), "w"
                ) as dest_fd:
                    dest_fd.write(data)
                    dest_fd.flush()
                    os.fsync(dest_fd)

            if move:
                os.remove(source)
            return True
        except Exception as e1:
            if log is not None:
                log.error("Error in CopyFile : " + str(source) + " : " + str(e1))
            return False

    def GetSiteName(self) -> str:
        """
        Retrieves the site name (assumed to be set elsewhere in subclass).

        Returns:
            str: The site name.
        """
        return self.SiteName

    def IsLoaded(self) -> bool:
        """
        Checks if the program is already loaded by checking the server port.

        Returns:
            bool: True if the port is in use, False otherwise.
        """
        Socket = None

        try:
            # create an INET, STREAMing socket
            Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # now connect to the server on our port
            Socket.connect((ProgramDefaults.LocalHost, self.ServerSocketPort))
            Socket.close()
            return True
        except Exception:
            if Socket is not None:
                Socket.close()
            return False

    def GetPlatformStats(
        self, usemetric: Optional[bool] = None, JSONNum: bool = False
    ) -> List[Dict]:
        """
        Retrieves platform statistics (CPU temp, etc.).

        Args:
            usemetric (bool, optional): Override default metric setting.
            JSONNum (bool, optional): Unused in current implementation.

        Returns:
            List[Dict]: List of platform info dictionaries.
        """
        if usemetric is not None:
            bMetric = usemetric
        else:
            bMetric = self.UseMetric
        Platform = MyPlatform(self.log, bMetric)

        return Platform.GetInfo(JSONNum=JSONNum)

    def RegExIsValid(self, input_str: str) -> bool:
        """
        Validates if a string is a valid regular expression.

        Args:
            input_str (str): The regex string to check.

        Returns:
            bool: True if valid, False otherwise.
        """
        try:
            re.compile(input_str)
            return True
        except Exception:
            return False

    def InternetConnected(self) -> str:
        """
        Checks for internet connectivity.

        Returns:
            str: "OK" if connected, "Disconnected" or error message otherwise.
        """
        try:
            if MyPlatform.InternetConnected():
                Status = "OK"
            else:
                Status = "Disconnected"

            return Status
        except Exception as e1:
            return "Unknown" + ":" + str(e1)

    def GetDeadThreadName(self) -> str:
        """
        Returns a string listing threads that are not alive.

        Returns:
            str: Names of dead threads or a success message.
        """
        RetStr = ""
        ThreadNames = ""
        for Name, MyThreadObj in self.Threads.items():
            ThreadNames += Name + " "
            if not MyThreadObj.IsAlive():
                RetStr += MyThreadObj.Name() + " "

        if RetStr == "":
            RetStr = "All threads alive: " + ThreadNames

        return RetStr

    def KillThread(self, Name: str, CleanupSelf: bool = False) -> Union[bool, None]:
        """
        Stops and waits for a thread to finish.

        Args:
            Name (str): The name of the thread to kill.
            CleanupSelf (bool, optional): If True, skips stop/wait. Defaults to False.

        Returns:
            Union[bool, None]: False if thread not found, None on success.
        """
        try:
            MyThreadObj = self.Threads.get(Name, None)
            if MyThreadObj is None:
                self.LogError("Error getting thread name in KillThread: " + Name)
                return False

            if not CleanupSelf:
                MyThreadObj.Stop()
                MyThreadObj.WaitForThreadToEnd()
        except Exception as e1:
            self.LogError("Error in KillThread ( " + Name + "): " + str(e1))
            return

    def StartAllThreads(self) -> None:
        """Starts all managed threads."""
        for key, ThreadInfo in self.Threads.items():
            ThreadInfo.Start()

    def AreThreadsAlive(self) -> bool:
        """
        Checks if all managed threads are alive.

        Returns:
            bool: True if all threads are alive, False otherwise.
        """
        for Name, MyThreadObj in self.Threads.items():
            if not MyThreadObj.IsAlive():
                return False

        return True

    def IsStopSignaled(self, Name: str) -> bool:
        """
        Checks if a specific thread has been signaled to stop.

        Args:
            Name (str): The name of the thread.

        Returns:
            bool: True if signaled to stop, False otherwise.
        """
        Thread = self.Threads.get(Name, None)
        if Thread is None:
            self.LogError("Error getting thread name in IsStopSignaled: " + Name)
            return False

        return Thread.StopSignaled()

    def WaitForExit(self, Name: str, timeout: Optional[float] = None) -> bool:
        """
        Waits for a thread's stop event.

        Args:
            Name (str): The name of the thread.
            timeout (float, optional): Wait timeout in seconds.

        Returns:
            bool: True if stop signal received, False if timed out.
        """
        Thread = self.Threads.get(Name, None)
        if Thread is None:
            self.LogError("Error getting thread name in WaitForExit: " + Name)
            return False

        return Thread.Wait(timeout)

    def UnitsOut(
        self, input: str, type: Optional[type] = None, NoString: bool = False
    ) -> Union[str, Dict[str, Any]]:
        """
        Parses a string with units (e.g., "5 kW") and formats it.

        Args:
            input (str): The input string with value and units.
            type (type, optional): The type to cast the value to (int or float).
            NoString (bool, optional): If True, returns a dictionary structure.

        Returns:
            Union[str, Dict]: Formatted string or dictionary.
        """
        try:
            if not NoString:
                return input
            InputArray = input.strip().split(" ")
            if len(InputArray) == 1:
                return input
            if len(InputArray) == 2 or len(InputArray) == 3:
                if (
                    len(InputArray) == 3
                ):  # this handles two word untis like 'cubic feet'
                    InputArray[1] = InputArray[1] + " " + InputArray[2]
                if type == int:
                    InputArray[0] = int(InputArray[0])
                elif type == float:
                    InputArray[0] = float(InputArray[0])
                else:
                    self.LogError("Invalid type for UnitsOut: " + input)
                    return input
                return self.ValueOut(
                    value=InputArray[0], unit=InputArray[1], NoString=NoString
                )
            else:
                self.LogError("Invalid input for UnitsOut: " + input)
                return input
        except Exception as e1:
            self.LogErrorLine("Error in SplitUnits: " + str(e1))
            return input

    def ValueOut(
        self, value: Any, unit: str, NoString: bool = False
    ) -> Union[str, Dict[str, Any]]:
        """
        Formats a value and unit.

        Args:
            value (Any): The numeric value.
            unit (str): The unit string.
            NoString (bool, optional): If True, returns a dict instead of a string.

        Returns:
            Union[str, Dict]: Formatted string "val unit" or dict representation.
        """
        try:
            if NoString:
                ReturnDict = collections.OrderedDict()
                ReturnDict["unit"] = unit
                DefaultReturn = ReturnDict
            else:
                DefaultReturn = ""
            if isinstance(value, int):
                if not NoString:
                    return "%d %s" % (int(value), str(unit))
                else:
                    ReturnDict["type"] = "int"
                    ReturnDict["value"] = value
                    return ReturnDict
            elif isinstance(value, float):
                if not NoString:
                    return "%.2f %s" % (float(value), str(unit))
                else:
                    ReturnDict["type"] = "float"
                    ReturnDict["value"] = round(value, 2)
                    return ReturnDict
            elif sys.version_info[0] < 3 and isinstance(value, long):
                if not NoString:
                    return "%d %s" % (int(value), str(unit))
                else:
                    ReturnDict["type"] = "long"
                    ReturnDict["value"] = value
                    return ReturnDict
            else:
                self.LogError(
                    "Unsupported type in ValueOut: "
                    + str(type(value))
                    + " : "
                    + str(unit)
                    + " : "
                    + str(value)
                )
                return DefaultReturn
        except Exception as e1:
            self.LogErrorLine("Error in ValueOut: " + str(e1))
            return DefaultReturn

    def GetIntFromString(
        self, input_string: str, byte_offset: int, length: int = 1, decimal: bool = False
    ) -> int:
        """
        Parses an integer from a hex string at a specific offset.

        Args:
            input_string (str): The hex string.
            byte_offset (int): The byte offset (2 hex chars per byte).
            length (int, optional): Number of bytes to read. Defaults to 1.
            decimal (bool, optional): If True, treats the substring as a decimal
                digit (uncommon usage). Defaults to False.

        Returns:
            int: The parsed integer.
        """
        try:
            if len(input_string) < byte_offset + length:
                self.LogError(
                    "Invalid length in GetIntFromString: " + str(input_string)
                )
                return 0
            StringOffset = byte_offset * 2
            StringOffsetEnd = StringOffset + (length * 2)
            if StringOffset == StringOffsetEnd:
                if decimal:
                    return int(input_string[StringOffset])
                return int(input_string[StringOffset], 16)
            else:
                if decimal:
                    return int(input_string[StringOffset:StringOffsetEnd])
                return int(input_string[StringOffset:StringOffsetEnd], 16)
        except Exception as e1:
            self.LogErrorLine("Error in GetIntFromString: " + str(e1))
            return 0

    def HexStringToString(self, input: str) -> str:
        """
        Converts a hex string to an ASCII string.

        Args:
            input (str): The hex string.

        Returns:
            str: The decoded ASCII string.
        """
        try:
            if not len(input):
                return ""
            if not self.StringIsHex(input):
                return ""
            ByteArray = bytearray.fromhex(input)
            if ByteArray[0] == 0:
                return ""
            End = ByteArray.find(b"\0")
            if End != -1:
                ByteArray = ByteArray[:End]
            return str(ByteArray.decode("ascii"))
        except Exception as e1:
            if self.debug:
                self.LogErrorLine("Error in HexStringToString: " + str(e1))
            return ""

    def StringIsHex(self, input: str) -> bool:
        """
        Checks if a string contains valid hex characters.

        Args:
            input (str): The string to check.

        Returns:
            bool: True if valid hex, False otherwise.
        """
        try:
            if " " in input:
                return False
            int(input, 16)
            return True
        except Exception:
            return False

    def GetDispatchItem(self, item: Any, key: Optional[str] = None) -> str:
        """
        Resolves a dispatch item to a string.

        If the item is callable, it is executed and the result converted to string.

        Args:
            item (Any): The item to resolve.
            key (str, optional): The key associated with the item (for logging).

        Returns:
            str: The resolved string value.
        """
        NoneType = type(None)

        if isinstance(item, str):
            return item
        if sys.version_info[0] < 3 and isinstance(item, unicode):
            return str(item)
        elif callable(item):
            return item()
        elif isinstance(item, int):
            return str(item)
        elif sys.version_info[0] < 3 and isinstance(item, (int, long)):
            return str(item)
        elif isinstance(item, float):
            return str(item)
        elif sys.version_info[0] >= 3 and isinstance(item, (bytes)):
            return str(item)
        elif isinstance(item, NoneType):
            return "None"
        else:
            self.LogError(
                "Unable to convert type %s in GetDispatchItem" % str(type(item))
            )
            self.LogError("Item: " + str(key) + ":" + str(item))
            return ""

    def IsString(self, inputvalue: Any) -> bool:
        """
        Checks if a value behaves like a string (has .lower()).

        Args:
            inputvalue (Any): The value to check.

        Returns:
            bool: True if string-like, False otherwise.
        """
        try:
            inputvalue.lower()
            return True
        except AttributeError:
            return False

    def ProcessDispatch(
        self, node: Union[Dict, List], InputBuffer: Any, indent: int = 0
    ) -> Any:
        """
        Recursively processes a dictionary structure, resolving callable values.

        If InputBuffer is a string, `ProcessDispatchToString` is called.

        Args:
            node (Union[Dict, List]): The data structure to process.
            InputBuffer (Any): The output buffer (Dict or String).
            indent (int, optional): Indentation level. Defaults to 0.

        Returns:
            Any: The processed structure or string.
        """
        if isinstance(InputBuffer, str):
            return self.ProcessDispatchToString(node, InputBuffer, indent)

        if isinstance(node, dict):
            for key, item in node.items():
                if isinstance(item, dict):
                    NewDict = collections.OrderedDict()
                    InputBuffer[key] = self.ProcessDispatch(item, NewDict)
                elif isinstance(item, list):
                    InputBuffer[key] = []
                    for listitem in item:
                        if isinstance(listitem, dict):
                            NewDict2 = collections.OrderedDict()
                            InputBuffer[key].append(
                                self.ProcessDispatch(listitem, NewDict2)
                            )
                        else:
                            self.LogError(
                                "Invalid type in ProcessDispatch %s " % str(type(node))
                            )
                else:
                    InputBuffer[key] = self.GetDispatchItem(item, key=key)
        else:
            self.LogError("Invalid type in ProcessDispatch %s " % str(type(node)))

        return InputBuffer

    def ProcessDispatchToString(
        self, node: Union[Dict, List], InputBuffer: str, indent: int = 0
    ) -> str:
        """
        Recursively processes a dictionary structure into a formatted string.

        Args:
            node (Union[Dict, List]): The data structure.
            InputBuffer (str): The accumulating string buffer.
            indent (int, optional): Indentation level. Defaults to 0.

        Returns:
            str: The formatted string.
        """
        if not isinstance(InputBuffer, str):
            return ""

        if isinstance(node, dict):
            for key, item in node.items():
                if isinstance(item, dict):
                    InputBuffer += "\n" + ("    " * indent) + str(key) + " : \n"
                    InputBuffer = self.ProcessDispatchToString(
                        item, InputBuffer, indent + 1
                    )
                elif isinstance(item, list):
                    InputBuffer += "\n" + ("    " * indent) + str(key) + " : \n"
                    for listitem in item:
                        if isinstance(listitem, dict):
                            InputBuffer = self.ProcessDispatchToString(
                                listitem, InputBuffer, indent + 1
                            )
                        elif isinstance(listitem, str) or isinstance(listitem, unicode):
                            InputBuffer += (
                                ("    " * (indent + 1))
                                + self.GetDispatchItem(listitem, key=key)
                                + "\n"
                            )
                        else:
                            self.LogError(
                                "Invalid type in ProcessDispatchToString %s %s (2)"
                                % (key, str(type(listitem)))
                            )
                    if len(item) > 1:
                        InputBuffer += "\n"
                else:
                    InputBuffer += (
                        ("    " * indent)
                        + str(key)
                        + " : "
                        + self.GetDispatchItem(item, key=key)
                        + "\n"
                    )
        else:
            self.LogError(
                "Invalid type in ProcessDispatchToString %s " % str(type(node))
            )
        return InputBuffer

    def GetNumBitsChanged(self, FromValue: str, ToValue: str) -> Tuple[int, int]:
        """
        Calculates the number of bits changed between two hex values.

        Args:
            FromValue (str): Original hex value.
            ToValue (str): New hex value.

        Returns:
            Tuple[int, int]: (Number of bits changed, The mask of changed bits).
        """
        if not len(FromValue) or not len(ToValue):
            return 0, 0
        MaskBitsChanged = int(FromValue, 16) ^ int(ToValue, 16)
        NumBitsChanged = MaskBitsChanged
        count = 0
        while NumBitsChanged:
            count += NumBitsChanged & 1
            NumBitsChanged >>= 1

        return count, MaskBitsChanged

    def GetDeltaTimeMinutes(self, DeltaTime: datetime.timedelta) -> int:
        """
        Calculates the difference in minutes from a timedelta object.

        Args:
            DeltaTime (datetime.timedelta): The time delta.

        Returns:
            int: Total minutes.
        """
        try:
            total_sec = DeltaTime.total_seconds()
            return int(total_sec / 60)
        except Exception:
            days, seconds = float(DeltaTime.days), float(DeltaTime.seconds)
            delta_hours = days * 24.0 + seconds // 3600.0
            delta_minutes = (seconds % 3600.0) // 60.0

            return int(delta_hours * 60.0 + delta_minutes)

    def ReadCSVFile(self, FileName: str) -> List[List[str]]:
        """
        Reads a CSV file into a list of lists.

        Ignores lines starting with '#'.

        Args:
            FileName (str): Path to the CSV file.

        Returns:
            List[List[str]]: List of rows, where each row is a list of fields.
        """
        try:
            ReturnedList = []
            with open(FileName, "r") as CSVFile:
                for line in CSVFile:
                    line = (
                        line.strip()
                    )  # remove newline at beginning / end and trailing whitespace
                    if not len(line):
                        continue
                    if line[0] == "#":  # comment?
                        continue
                    Items = line.split(",")
                    ReturnedList.append(Items)

            return ReturnedList
        except Exception as e1:
            self.LogErrorLine("Error in ReadCSVFile: " + FileName + " : " + str(e1))
            return []

    def GetWANIp(self) -> str:
        """
        Retrieves the WAN IP address using an external service.

        Returns:
            str: The WAN IP address or "Unknown" on error.
        """
        try:
            import requests

            ip = requests.get("http://ipinfo.io/json").json()["ip"]
            return ip.strip()
        except Exception as e1:
            self.LogErrorLine("Error getting WAN IP: " + str(e1))
            return "Unknown"

    def GetNetworkIp(self) -> str:
        """
        Retrieves the local network IP address.

        Returns:
            str: The local IP address.
        """
        try:
            return str(
                (
                    (
                        [
                            ip
                            for ip in socket.gethostbyname_ex(socket.gethostname())[2]
                            if not ip.startswith("127.")
                        ]
                        or [
                            [
                                (
                                    s.connect(("8.8.8.8", 53)),
                                    s.getsockname()[0],
                                    s.close(),
                                )
                                for s in [
                                    socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                                ]
                            ][0][1]
                        ]
                    )
                    + ["no IP found"]
                )[0]
            )
        except Exception:
            return "Unknown"

    @staticmethod
    def IsRunning(
        prog_name: str, log: Any = None, multi_instance: bool = False
    ) -> bool:
        """
        Checks if a process with the given name is currently running.

        Args:
            prog_name (str): The program name (e.g., "genmon.py").
            log (Any, optional): Logger instance.
            multi_instance (bool, optional): If True, always returns False to
                allow multiple instances. Defaults to False.

        Returns:
            bool: True if running, False otherwise.
        """
        if multi_instance:  # do we allow multiple instances
            return False  # return False so the program will load anyway
        try:
            import psutil
        except ImportError:
            return False  # incase psutil is not installed load anyway
        try:
            prog_name = os.path.basename(prog_name)
            for q in psutil.process_iter():
                if q.name().lower().startswith("python"):
                    if len(q.cmdline()) > 1:
                        script_name = os.path.basename(q.cmdline()[1])
                        if (
                            len(q.cmdline()) > 1
                            and prog_name == script_name
                            and q.pid != os.getpid()
                        ):
                            return True
        except Exception as e1:
            if log is not None:
                log.error(
                    "Error in IsRunning: " + str(e1) + ": " + MySupport.GetErrorLine()
                )
                return True
        return False

    @staticmethod
    def GetErrorLine() -> str:
        """
        Static wrapper for fetching exception line info.

        Returns:
            str: "filename:lineno" or empty string.
        """
        exc_type, exc_obj, exc_tb = sys.exc_info()
        if exc_tb is None:
            return ""
        else:
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            lineno = exc_tb.tb_lineno
            return fname + ":" + str(lineno)

    @staticmethod
    def SetupAddOnProgram(
        prog_name: str,
    ) -> Tuple[Any, str, str, int, str, Any]:
        """
        Performs standard setup for an add-on program (logging, permissions, args).

        Args:
            prog_name (str): The name of the program.

        Returns:
            Tuple: (console_logger, config_file_path, address, port, log_location, file_logger)
        """
        console = SetupLogger(prog_name + "_console", log_file="", stream=True)

        if not MySupport.PermissionsOK():
            console.error(
                "\nYou need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting.\n"
            )
            sys.exit(2)

        HelpStr = (
            "\nsudo python "
            + prog_name
            + ".py -a <IP Address or localhost> -c <path to "
            + prog_name
            + " config file>\n"
        )

        ConfigFilePath = ProgramDefaults.ConfPath
        address = ProgramDefaults.LocalHost

        try:
            opts, args = getopt.getopt(
                sys.argv[1:], "hc:a:", ["help", "configpath=", "address="]
            )
        except getopt.GetoptError:
            console.error("Invalid command line argument.")
            sys.exit(2)

        for opt, arg in opts:
            if opt == "-h":
                console.error(HelpStr)
                sys.exit()
            elif opt in ("-a", "--address"):
                address = arg
            elif opt in ("-c", "--configpath"):
                ConfigFilePath = arg.strip()

        try:
            port, loglocation, multi_instance = MySupport.GetGenmonInitInfo(
                ConfigFilePath, log=console
            )
            log = SetupLogger(
                "client_" + prog_name, os.path.join(loglocation, prog_name + ".log")
            )

            if not prog_name.lower().endswith(".py"):
                prog_name += ".py"

            attempts = 0
            while True:
                if MySupport.IsRunning(
                    prog_name=prog_name, log=log, multi_instance=multi_instance
                ):
                    if attempts >= 4:
                        raise Exception("The program %s is already loaded" % prog_name)
                    else:
                        attempts += 1
                        time.sleep(1)
                else:
                    break

        except Exception as e1:
            console.error("Error : " + str(e1))
            log.error("Error : " + str(e1) + ": " + MySupport.GetErrorLine())
            sys.exit(1)

        return console, ConfigFilePath, address, port, loglocation, log

    @staticmethod
    def GetGenmonInitInfo(
        configfilepath: str = MyCommon.DefaultConfPath, log: Any = None
    ) -> Tuple[int, str, bool]:
        """
        Reads initialization info from genmon.conf.

        Args:
            configfilepath (str, optional): Path to config directory.
                Defaults to MyCommon.DefaultConfPath.
            log (Any, optional): Logger instance.

        Returns:
            Tuple[int, str, bool]: (server_port, log_path, multi_instance_flag)
        """
        if configfilepath is None or configfilepath == "":
            configfilepath = MyCommon.DefaultConfPath

        config = MyConfig(
            os.path.join(configfilepath, "genmon.conf"), section="GenMon", log=log
        )
        loglocation = config.ReadValue("loglocation", default=ProgramDefaults.LogPath)
        port = config.ReadValue(
            "server_port", return_type=int, default=ProgramDefaults.ServerPort
        )
        multi_instance = config.ReadValue(
            "multi_instance", return_type=bool, default=False
        )
        return port, loglocation, multi_instance

    @staticmethod
    def PermissionsOK() -> bool:
        """
        Checks if the process has sufficient permissions (e.g., root on Linux).

        Returns:
            bool: True if permissions are sufficient, False otherwise.
        """
        if MyPlatform.IsOSLinux() and os.geteuid() == 0:
            return True
        if MyPlatform.IsOSWindows():
            return True
        else:
            return False
