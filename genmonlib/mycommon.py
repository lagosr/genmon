#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: mycommon.py
# PURPOSE: common functions in all classes
#
#  AUTHOR: Jason G Yates
#    DATE: 21-Apr-2018
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

"""
Module containing common functions used across all classes in the application.

This module defines the `MyCommon` class, which serves as a base class providing
utility methods for type conversion, dictionary manipulation, logging helpers,
and system environment checks.
"""

import json
import os
import re
import sys
from typing import Optional, Any, Dict, Tuple, List, Union, Type

from genmonlib.program_defaults import ProgramDefaults


# ------------ MyCommon class -----------------------------------------------------
class MyCommon(object):
    """
    Base class providing common utility functions.

    Attributes:
        DefaultConfPath (str): Default path for configuration files.
        log (logging.Logger): Logger instance.
        console (logging.Logger): Console logger instance.
        Threads (Dict): Dictionary to store thread objects.
        debug (bool): Flag to enable debug logging.
        MaintainerAddress (str): Email address of the software maintainer.
    """
    DefaultConfPath: str = ProgramDefaults.ConfPath

    def __init__(self):
        """Initializes the MyCommon instance."""
        self.log: Optional[Any] = None
        self.console: Optional[Any] = None
        self.Threads: Dict[str, Any] = {}  # Dict of mythread objects
        self.debug: bool = False
        self.MaintainerAddress: str = "generatormonitor.software@gmail.com"

    def InVirtualEnvironment(self) -> bool:
        """
        Checks if the application is running in a virtual environment.

        Returns:
            bool: True if running in a virtual environment, False otherwise.
        """
        try:
            return (hasattr(sys, 'real_prefix') or
                    (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix))
        except Exception:
            return False

    def ManagedLibariesEnabled(self) -> bool:
        """
        Checks if managed libraries (EXTERNALLY-MANAGED) are enabled.

        This is relevant for newer Python environments (PEP 668).

        Returns:
            bool: True if the EXTERNALLY-MANAGED file exists, False otherwise.
        """
        try:
            #  /usr/lib/python3.11/EXTERNALLY-MANAGED
            # to support python 3.5 not use formatted strings
            managedfile = ("/usr/lib/python" + str(sys.version_info.major) +
                           "." + str(sys.version_info.minor) +
                           "/EXTERNALLY-MANAGED")
            if os.path.isfile(managedfile):
                return True
            else:
                return False
        except Exception:
            return False

    def VersionTuple(self, value: str) -> Tuple[int, ...]:
        """
        Converts a version string to a tuple of integers.

        Args:
            value (str): The version string (e.g., "1.2.3").

        Returns:
            Tuple[int, ...]: A tuple of version components (e.g., (1, 2, 3)).
        """
        value = self.removeAlpha(value)
        return tuple(map(int, (value.split("."))))

    def StringIsInt(self, value: Any) -> bool:
        """
        Checks if a value can be converted to an integer.

        Args:
            value (Any): The value to check.

        Returns:
            bool: True if the value represents an integer, False otherwise.
        """
        try:
            int(value)
            return True
        except Exception:
            return False

    def StringIsFloat(self, value: Any) -> bool:
        """
        Checks if a value can be converted to a float.

        Args:
            value (Any): The value to check.

        Returns:
            bool: True if the value represents a float, False otherwise.
        """
        try:
            float(value)
            return True
        except Exception:
            return False

    def ConvertCelsiusToFahrenheit(self, Celsius: float) -> float:
        """
        Converts temperature from Celsius to Fahrenheit.

        Args:
            Celsius (float): Temperature in Celsius.

        Returns:
            float: Temperature in Fahrenheit.
        """
        return (Celsius * 9.0 / 5.0) + 32.0

    def ConvertFahrenheitToCelsius(self, Fahrenheit: float) -> float:
        """
        Converts temperature from Fahrenheit to Celsius.

        Args:
            Fahrenheit (float): Temperature in Fahrenheit.

        Returns:
            float: Temperature in Celsius.
        """
        return (Fahrenheit - 32.0) * 5.0 / 9.0

    def StripJson(self, InputString: str) -> str:
        """
        Removes JSON syntax characters ({, }, [, ], ") from a string.

        Args:
            InputString (str): The input JSON string.

        Returns:
            str: The cleaned string.
        """
        for char in '{}[]"':
            InputString = InputString.replace(char, "")
        return InputString

    def DictToString(self, InputDict: Optional[Dict], ExtraStrip: bool = False) -> str:
        """
        Converts a dictionary to a formatted string.

        Args:
            InputDict (Optional[Dict]): The dictionary to convert.
            ExtraStrip (bool, optional): If True, performs additional stripping.
                Defaults to False.

        Returns:
            str: The formatted string representation of the dictionary.
        """
        if InputDict is None:
            return ""
        ReturnString = json.dumps(
            InputDict, sort_keys=False, indent=4, separators=(" ", ": ")
        )
        if ExtraStrip:
            ReturnString = ReturnString.replace("} \n", "")
        return self.StripJson(ReturnString)

    def BitIsEqual(self, value: int, mask: int, bits: int) -> bool:
        """
        Checks if specific bits in a value match a pattern.

        Args:
            value (int): The value to check.
            mask (int): The bitmask to apply.
            bits (int): The expected bit pattern after masking.

        Returns:
            bool: True if (value & mask) == bits, False otherwise.
        """
        newval = value & mask
        if newval == bits:
            return True
        else:
            return False

    def printToString(
        self, msgstr: str, nonewline: bool = False, spacer: bool = False
    ) -> str:
        """
        Formats a message string.

        Args:
            msgstr (str): The message string.
            nonewline (bool, optional): If False, appends a newline. Defaults to False.
            spacer (bool, optional): If True, adds leading spaces. Defaults to False.

        Returns:
            str: The formatted string.
        """
        if spacer:
            MessageStr = "    {0}"
        else:
            MessageStr = "{0}"

        if not nonewline:
            MessageStr += "\n"

        # print (MessageStr.format(msgstr), end='')
        newtpl = (MessageStr.format(msgstr),)
        return newtpl[0]

    def FindDictValueInListByKey(self, key: str, listname: List[Any]) -> Any:
        """
        Searches for a key in a list of dictionaries and returns its value.

        Args:
            key (str): The key to search for (case-insensitive).
            listname (List[Any]): The list containing dictionaries.

        Returns:
            Any: The value associated with the key, or None if not found.
        """
        try:
            for item in listname:
                if isinstance(item, dict):
                    for dictkey, value in item.items():
                        if dictkey.lower() == key.lower():
                            return value
        except Exception as e1:
            self.LogErrorLine("Error in FindDictInList: " + str(e1))
        return None

    def removeNonPrintable(self, inputStr: str) -> str:
        """
        Removes non-printable characters from a string.

        Args:
            inputStr (str): The input string.

        Returns:
            str: The cleaned string.
        """
        try:
            # remove any non printable chars
            inputStr = re.sub(r"[^\x20-\x7f]", r"", inputStr)
            return inputStr
        except Exception:
            return inputStr

    def removeAlpha(self, inputStr: str) -> str:
        """
        Removes alphabetic characters from a string, keeping numbers and special chars.

        Args:
            inputStr (str): The input string.

        Returns:
            str: The string with alphabetic characters removed.
        """
        answer = ""
        for char in inputStr:
            if not char.isalpha() and char != " " and char != "%":
                answer += char

        return answer.strip()

    def ConvertToNumber(self, value: str) -> Union[int, float]:
        """
        Converts a string to a number (int or float), removing non-numeric characters.

        Args:
            value (str): The string to convert.

        Returns:
            Union[int, float]: The converted number, or 0 on error.
        """
        try:
            return_value = re.sub('[^0-9.\\-]', '', value)
            try:
                result = int(return_value)
            except ValueError:
                result = float(return_value)
            return result
        except Exception as e1:
            self.LogErrorLine("Error in ConvertToNumber: " + str(e1) +
                              ": " + str(value))
            return 0

    def MergeDicts(self, x: Dict, y: Dict) -> Dict:
        """
        Merges two dictionaries into a new dictionary (shallow copy).

        Args:
            x (Dict): The first dictionary.
            y (Dict): The second dictionary (updates x).

        Returns:
            Dict: The merged dictionary.
        """
        z = x.copy()
        z.update(y)
        return z

    def urljoin(self, *parts: Any) -> str:
        """
        Joins URL parts into a single URL string.

        Args:
            *parts: Variable number of URL parts.

        Returns:
            str: The joined URL.
        """
        # first strip extra forward slashes (except http:// and the likes) and
        # create list
        part_list = []
        for part in parts:
            p = str(part)
            if p.endswith("//"):
                p = p[0:-1]
            else:
                p = p.strip("/")
            part_list.append(p)
        # join everything together
        url = "/".join(part_list)
        return url

    def LogHexList(
        self, listname: List[int], prefix: Optional[str] = None, nolog: bool = False
    ) -> str:
        """
        Formats a list of integers as a hex string list and optionally logs it.

        Args:
            listname (List[int]): The list of integers.
            prefix (Optional[str], optional): Prefix for the log message.
            nolog (bool, optional): If True, does not log the message. Defaults to False.

        Returns:
            str: The formatted hex string.
        """
        try:
            outstr = ""
            outstr = "[" + ",".join("0x{:02x}".format(num) for num in listname) + "]"
            if prefix is not None:
                outstr = prefix + " = " + outstr

            if nolog is False:
                self.LogError(outstr)
            return outstr
        except Exception as e1:
            self.LogErrorLine("Error in LogHexList: " + str(e1))
            return ""

    def LogInfo(self, message: str, LogLine: bool = False) -> None:
        """
        Logs an informational message to both the log file and the console.

        Args:
            message (str): The message to log.
            LogLine (bool, optional): If True, includes line number info in the log file.
                Defaults to False.
        """
        if not LogLine:
            self.LogError(message)
        else:
            self.LogErrorLine(message)
        self.LogConsole(message)

    def LogConsole(self, Message: str, Error: Optional[Exception] = None) -> None:
        """
        Logs a message to the console.

        Args:
            Message (str): The message to log.
            Error (Optional[Exception], optional): An exception to append to the message.
        """
        if self.console is not None:
            self.console.error(Message)

    def LogError(self, Message: str, Error: Optional[Exception] = None) -> None:
        """
        Logs an error message to the log file.

        Args:
            Message (str): The message to log.
            Error (Optional[Exception], optional): An exception to append.
        """
        if self.log is not None:
            if Error is not None:
                Message = Message + " : " + self.GetErrorString(Error)
            self.log.error(Message)

    def FatalError(self, Message: str, Error: Optional[Exception] = None) -> None:
        """
        Logs a fatal error message and raises an exception.

        Args:
            Message (str): The message to log.
            Error (Optional[Exception], optional): An exception to append.

        Raises:
            Exception: The formatted error message.
        """
        if Error is not None:
            Message = Message + " : " + self.GetErrorString(Error)
        if self.log is not None:
            self.log.error(Message)
        if self.console is not None:
            self.console.error(Message)
        raise Exception(Message)

    def LogErrorLine(self, Message: str, Error: Optional[Exception] = None) -> None:
        """
        Logs an error message with the source file and line number.

        Args:
            Message (str): The message to log.
            Error (Optional[Exception], optional): An exception to append.
        """
        if self.log is not None:
            if Error is not None:
                Message = Message + " : " + self.GetErrorString(Error)
            self.log.error(Message + " : " + self.GetErrorLine())

    def LogDebug(self, Message: str, Error: Optional[Exception] = None) -> None:
        """
        Logs a debug message if debug mode is enabled.

        Args:
            Message (str): The message to log.
            Error (Optional[Exception], optional): An exception to append.
        """
        if self.debug:
            self.LogError(Message, Error)

    def GetErrorLine(self) -> str:
        """
        Retrieves the filename and line number of the current exception.

        Returns:
            str: "filename:lineno" or empty string if no exception info.
        """
        exc_type, exc_obj, exc_tb = sys.exc_info()
        if exc_tb is None:
            return ""
        else:
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            lineno = exc_tb.tb_lineno
            return fname + ":" + str(lineno)

    def GetErrorString(self, Error: Any) -> str:
        """
        Converts an error object to a string.

        Args:
            Error (Any): The error object.

        Returns:
            str: The string representation of the error.
        """
        try:
            return str(Error)
        except Exception:
            return str(Error)

    def getSignedNumber(self, number: int, bitLength: int) -> int:
        """
        Converts an unsigned integer to a signed integer based on bit length.

        Args:
            number (int): The unsigned number.
            bitLength (int): The number of bits (e.g., 16, 32).

        Returns:
            int: The signed number.
        """
        try:
            if isinstance(number, int) and isinstance(bitLength, int):
                mask = (2 ** bitLength) - 1
                if number & (1 << (bitLength - 1)):
                    return number | ~mask
                else:
                    return number & mask
            else:
                return number
        except Exception as e1:
            self.LogErrorLine("Error in getSignedNumber: " + str(e1))
            return number
