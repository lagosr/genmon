#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: myplatform.py
# PURPOSE: Platform Specific Code
#
#  AUTHOR: Jason G Yates
#    DATE: 20-May-2018
#
# MODIFICATIONS:
#
# USAGE:
#
# -------------------------------------------------------------------------------

"""
Module for platform-specific interactions.

This module provides the `MyPlatform` class which includes methods for
detecting the operating system, retrieving system statistics (CPU, uptime),
checking network status, and interacting with Raspberry Pi specific hardware.
"""

import datetime
import os
import re
import subprocess
import sys
from subprocess import PIPE, Popen
from typing import Optional, List, Dict, Union, Any

from genmonlib.mycommon import MyCommon


# ------------ MyPlatform class -------------------------------------------------
class MyPlatform(MyCommon):
    """
    A class for handling platform-specific operations.

    Attributes:
        log (Any): Logger instance.
        UseMetric (bool): Whether to use metric units.
        debug (bool): Debug mode flag.
    """

    def __init__(
        self, log: Any = None, usemetric: bool = True, debug: Optional[bool] = None
    ):
        """
        Initializes the MyPlatform instance.

        Args:
            log (Any, optional): Logger instance.
            usemetric (bool, optional): If True, use metric units. Defaults to True.
            debug (bool, optional): If True, enable debug logging. Defaults to None.
        """
        self.log = log
        self.UseMetric = usemetric
        self.debug = debug

    def GetInfo(self, JSONNum: bool = False) -> List[Dict]:
        """
        Retrieves general system information.

        Collects platform info, OS info, and current system time.

        Args:
            JSONNum (bool, optional): Unused in current implementation.

        Returns:
            List[Dict]: A list of dictionaries containing system info.
        """
        Info = []

        PlatformInfo = self.GetPlatformInfo()

        if PlatformInfo is not None:
            Info.extend(PlatformInfo)

        OSInfo = self.GetOSInfo()

        if OSInfo is not None:
            Info.extend(OSInfo)

        Info.append({"System Time": self.GetSystemTime()})
        return Info

    def GetSystemTime(self) -> str:
        """
        Gets the current system time formatted as a string.

        Returns:
            str: Formatted date time string (e.g., "Sunday May 20, 2018 10:00:00").
        """
        return datetime.datetime.now().strftime("%A %B %-d, %Y %H:%M:%S")

    def GetPlatformInfo(self, JSONNum: bool = False) -> Optional[List[Dict]]:
        """
        Retrieves platform-specific hardware info (currently Raspberry Pi only).

        Args:
            JSONNum (bool, optional): Unused.

        Returns:
            Optional[List[Dict]]: List of platform info dicts or None.
        """
        if self.IsPlatformRaspberryPi():
            return self.GetRaspberryPiInfo()
        else:
            return None

    def GetOSInfo(self, JSONNum: bool = False) -> Optional[List[Dict]]:
        """
        Retrieves Operating System information (Linux only).

        Args:
            JSONNum (bool, optional): Unused.

        Returns:
            Optional[List[Dict]]: List of OS info dicts or None.
        """
        if self.IsOSLinux():
            return self.GetLinuxInfo()
        return None

    def PlatformBitDepth(self) -> str:
        """
        Determines the system architecture bit depth.

        Returns:
            str: "32", "64", or "Unknown".
        """
        try:
            import platform

            if platform.architecture()[0] == "32bit":
                return "32"
            elif platform.architecture()[0] == "64bit":
                return "64"
            else:
                return "Unknown"
        except Exception as e1:
            self.LogErrorLine("Error in PlatformBitDepth: " + str(e1))
            return "Unknown"

    @staticmethod
    def IsOSLinux() -> bool:
        """
        Checks if the operating system is Linux.

        Returns:
            bool: True if Linux, False otherwise.
        """
        if "linux" in sys.platform:
            return True
        return False

    @staticmethod
    def IsOSWindows() -> bool:
        """
        Checks if the operating system is Windows.

        Returns:
            bool: True if Windows, False otherwise.
        """
        if "win" in sys.platform:
            return True
        return False

    def IsPlatformRaspberryPi(self, raise_on_errors: bool = False) -> bool:
        """
        Checks if the hardware platform is a Raspberry Pi.

        Args:
            raise_on_errors (bool, optional): If True, raises ValueError on detection failure.
                Defaults to False.

        Returns:
            bool: True if Raspberry Pi, False otherwise.
        """
        try:
            model = self.GetRaspberryPiModel(bForce=True)
            if model is not None and "raspberry" in model.lower():
                return True

            with open("/proc/cpuinfo", "r") as cpuinfo:
                found = False
                for line in cpuinfo:
                    if line.startswith("Hardware"):
                        found = True
                        label, value = line.strip().split(":", 1)
                        value = value.strip()
                        if value not in (
                            "BCM2708",
                            "BCM2709",
                            "BCM2835",
                            "BCM2836",
                            "BCM2711",
                        ):
                            if raise_on_errors:
                                raise ValueError(
                                    "This system does not appear to be a Raspberry Pi."
                                )
                            else:
                                return False
                if not found:
                    if raise_on_errors:
                        raise ValueError(
                            "Unable to determine if this system is a Raspberry Pi."
                        )
                    else:
                        return False
        except IOError:
            if raise_on_errors:
                raise ValueError("Unable to open `/proc/cpuinfo`.")
            else:
                return False

        return True

    def GetRaspberryPiTemp(
        self, ReturnFloat: bool = False, JSONNum: bool = False
    ) -> Union[str, float]:
        """
        Gets the Raspberry Pi CPU temperature.

        Args:
            ReturnFloat (bool, optional): If True, return a float value.
                Defaults to False.
            JSONNum (bool, optional): Unused.

        Returns:
            Union[str, float]: Temperature string (with units) or float value.
        """
        # get CPU temp
        try:
            if ReturnFloat:
                DefaultReturn = 0.0
            else:
                DefaultReturn = "0"

            if not self.IsOSLinux():
                return DefaultReturn
            try:
                if os.path.exists("/usr/bin/vcgencmd"):
                    binarypath = "/usr/bin/vcgencmd"
                else:
                    binarypath = "/opt/vc/bin/vcgencmd"

                process = Popen([binarypath, "measure_temp"], stdout=PIPE)
                output, _error = process.communicate()
                output_str = output.decode("utf-8")
                if sys.version_info[0] >= 3:
                    output_str = str(output_str)

                TempCelciusFloat = float(
                    output_str[output_str.index("=") + 1 : output_str.rindex("'")]
                )

            except Exception:
                # for non rasbpian based systems
                tempfilepath = self.GetHwMonParamPath("temp1_input")
                if tempfilepath is None:
                    tempfilepath = "/sys/class/thermal/thermal_zone0/temp"

                if os.path.exists(tempfilepath):
                    process = Popen(["cat", tempfilepath], stdout=PIPE)
                    output, _error = process.communicate()
                    output_str = output.decode("utf-8")

                    TempCelciusFloat = float(float(output_str) / 1000)
                else:
                    # not sure what OS this is, possibly docker image
                    return DefaultReturn
            if self.UseMetric:
                if not ReturnFloat:
                    return "%.2f C" % TempCelciusFloat
                else:
                    return round(TempCelciusFloat, 2)
            else:
                if not ReturnFloat:
                    return "%.2f F" % float(
                        self.ConvertCelsiusToFahrenheit(TempCelciusFloat)
                    )
                else:
                    return round(
                        float(self.ConvertCelsiusToFahrenheit(TempCelciusFloat)), 2
                    )
        except Exception as e1:
            self.LogErrorLine("Error in GetRaspberryPiTemp: " + str(e1))
        return DefaultReturn

    def GetRaspberryPiModel(self, bForce: bool = False) -> Optional[str]:
        """
        Retrieves the Raspberry Pi model string.

        Args:
            bForce (bool, optional): If False, checks IsPlatformRaspberryPi first.
                Defaults to False.

        Returns:
            Optional[str]: The model string or None if not found.
        """
        try:
            if bForce is False and not self.IsPlatformRaspberryPi():
                return None

            process = Popen(["cat", "/proc/device-tree/model"], stdout=PIPE)
            output, _error = process.communicate()
            if sys.version_info[0] >= 3:
                output_str = output.decode("utf-8")
            else:
                output_str = str(output)
            return str(output_str.rstrip("\x00"))
        except Exception:
            return None

    def GetRaspberryPiInfo(self, JSONNum: bool = False) -> Optional[List[Dict]]:
        """
        Gets detailed Raspberry Pi information.

        Args:
            JSONNum (bool, optional): Unused.

        Returns:
            Optional[List[Dict]]: List containing temp, model, and throttle status.
        """
        if not self.IsPlatformRaspberryPi():
            return None
        PiInfo = []

        try:
            PiInfo.append(
                {"CPU Temperature": self.GetRaspberryPiTemp(ReturnFloat=False)}
            )
            try:
                model = self.GetRaspberryPiModel()
                PiInfo.append({"Pi Model": model})
            except Exception:
                pass
            try:
                ThrottledStatus = self.GetThrottledStatus()
                if len(ThrottledStatus):
                    PiInfo.extend(ThrottledStatus)
            except Exception:
                pass

        except Exception as e1:
            self.LogErrorLine("Error in GetRaspberryPiInfo: " + str(e1))

        return PiInfo

    def ParseThrottleStatus(self, status: int) -> List[Dict]:
        """
        Decodes the Raspberry Pi throttle status bits.

        Args:
            status (int): The status integer from vcgencmd.

        Returns:
            List[Dict]: A list of human-readable status dictionaries.
        """
        PiThrottleInfo = []

        StatusStr = ""

        if status & 0x40000:
            StatusStr += "Has occurred. "
        if status & 0x4:
            StatusStr += "Throttling Active. "

        if StatusStr == "":
            StatusStr += "OK"

        PiThrottleInfo.append({"Pi CPU Frequency Throttling": StatusStr})

        StatusStr = ""
        if status & 0x20000:
            StatusStr += "Has occurred. "
        if status & 0x2:
            StatusStr += "ARM frequency capped. "

        if StatusStr == "":
            StatusStr += "OK"

        PiThrottleInfo.append({"Pi ARM Frequency Cap": StatusStr})

        StatusStr = ""
        if status & 0x10000:
            StatusStr += "Has occurred. "
        if status & 0x1:
            StatusStr += "Undervoltage Detected. "

        if StatusStr == "":
            StatusStr += "OK"

        PiThrottleInfo.append({"Pi Undervoltage": StatusStr})
        return PiThrottleInfo

    def GetThrottledStatus(self) -> List[Dict]:
        """
        Retrieves the current throttle status from vcgencmd or sysfs.

        Returns:
            List[Dict]: Parsed throttle status info.
        """
        try:
            if os.path.exists("/usr/bin/vcgencmd"):
                binarypath = "/usr/bin/vcgencmd"
            else:
                binarypath = "/opt/vc/bin/vcgencmd"

            process = Popen([binarypath, "get_throttled"], stdout=PIPE)
            output, _error = process.communicate()
            output_str = output.decode("utf-8")
            hex_val = output_str.split("=")[1].strip()
            get_throttled = int(hex_val, 16)
            return self.ParseThrottleStatus(get_throttled)

        except Exception:
            try:
                # if we get here then vcgencmd is not found, try an alternate approach
                # /sys/class/hwmon/hwmonX/in0_lcrit_alarm
                throttle_file_path = self.GetHwMonParamPath("in0_lcrit_alarm")

                if throttle_file_path is not None:
                    file = open(throttle_file_path)
                else:
                    # this method is deprecated
                    file = open("/sys/devices/platform/soc/soc:firmware/get_throttled")
                status = file.read()
                return self.ParseThrottleStatus(int(status))
            except Exception:
                return []

    def GetHwMonParamPath(self, param: str) -> Optional[str]:
        """
        Searches for a hardware monitoring parameter file.

        Args:
            param (str): The parameter name (e.g., "temp1_input").

        Returns:
            Optional[str]: The file path if found, None otherwise.
        """
        try:
            for i in range(5):
                hwmon_path = "/sys/class/hwmon/hwmon%d" % (i) + "/" + str(param)
                if os.path.exists(hwmon_path):
                    return hwmon_path
        except Exception as e1:
            self.LogError("Error in GetHwMonParamPath: " + str(e1))
        return None

    def GetLinuxInfo(self, JSONNum: bool = False) -> Optional[List[Dict]]:
        """
        Retrieves general Linux system information (CPU, OS, Uptime, Network).

        Args:
            JSONNum (bool, optional): Unused.

        Returns:
            Optional[List[Dict]]: List of system info dicts.
        """
        if not self.IsOSLinux():
            return None
        LinuxInfo = []

        try:
            CPU_Pct = str(
                round(
                    float(
                        os.popen(
                            """grep 'cpu ' /proc/stat | awk '{usage=($2+$4)*100/($2+$4+$5)} END {print usage }' """
                        ).readline()
                    ),
                    2,
                )
            )
            if len(CPU_Pct):
                LinuxInfo.append({"CPU Utilization": CPU_Pct + "%"})
        except Exception:
            pass
        try:
            with open("/etc/os-release", "r") as f:
                OSReleaseInfo = {}
                for line in f:
                    if "=" not in line:
                        continue
                    k, v = line.rstrip().split("=")
                    # .strip('"') will remove if there or else do nothing
                    OSReleaseInfo[k] = v.strip('"')
                LinuxInfo.append({"OS Name": OSReleaseInfo.get("NAME", "Unknown")})
                if "VERSION" in OSReleaseInfo:
                    LinuxInfo.append({"OS Version": OSReleaseInfo["VERSION"]})
                elif "VERSION_ID" in OSReleaseInfo:
                    LinuxInfo.append({"OS Version": OSReleaseInfo["VERSION_ID"]})
            try:
                with open("/proc/uptime", "r") as f:
                    uptime_seconds = float(f.readline().split()[0])
                    uptime_string = str(datetime.timedelta(seconds=uptime_seconds))
                    LinuxInfo.append(
                        {"System Uptime": uptime_string.split(".")[0]}
                    )  # remove microseconds
            except Exception:
                pass

            try:
                adapter = (
                    os.popen(
                        "ip link | grep BROADCAST | grep -v NO-CARRIER | grep -m 1 LOWER_UP  | awk -F'[:. ]' '{print $3}'"
                    )
                    .readline()
                    .rstrip("\n")
                )
                # output, _error = process.communicate()
                LinuxInfo.append({"Network Interface Used": adapter})
                try:
                    if adapter.startswith("wl"):
                        LinuxInfo.extend(self.GetWiFiInfo(adapter))
                except Exception:
                    pass

            except Exception:
                pass
        except Exception as e1:
            self.LogErrorLine("Error in GetLinuxInfo: " + str(e1))

        return LinuxInfo

    def GetWiFiSignalStrength(
        self, ReturnInt: bool = True, JSONNum: bool = False, usepercent: bool = False
    ) -> Union[int, str]:
        """
        Gets the WiFi signal strength.

        Args:
            ReturnInt (bool, optional): If True, returns int (dBm). Defaults to True.
            JSONNum (bool, optional): Unused.
            usepercent (bool, optional): Unused (logic seems partial).

        Returns:
            Union[int, str]: Signal strength value.
        """
        try:
            if ReturnInt is True:
                DefaultReturn = 0
            else:
                DefaultReturn = 0  # Type mismatch in original code fixed intention

            if not self.IsOSLinux():
                return DefaultReturn

            adapter = (
                os.popen(
                    "ip link | grep BROADCAST | grep -v NO-CARRIER | grep -m 1 LOWER_UP  | awk -F'[:. ]' '{print $3}'"
                )
                .readline()
                .rstrip("\n")
            )

            if not adapter.startswith("wl"):
                return DefaultReturn

            signal = self.GetWiFiSignalStrengthFromAdapter(adapter)
            if not usepercent:
                # signal is usually negative dBm string like "50" meaning -50dBm
                # or already negative? iw output is "signal: -50 dBm"
                # original code: signal = int(signal) * -1
                # if GetWiFiSignalStrengthFromAdapter returns absolute value string
                try:
                    signal_int = int(signal)
                    if signal_int > 0:
                        signal_int = signal_int * -1
                    return signal_int
                except ValueError:
                    return DefaultReturn
            return signal
        except Exception as e1:
            self.LogErrorLine("Error in GetWiFiSignalStrength: " + str(e1))
            return 0

    def GetWiFiSignalStrengthFromAdapter(
        self, adapter: str, JSONNum: bool = False
    ) -> str:
        """
        Gets WiFi signal strength using `iw`.

        Args:
            adapter (str): Network adapter name.
            JSONNum (bool, optional): Unused.

        Returns:
            str: Signal strength (dBm value as string).
        """
        try:
            result = subprocess.check_output(["iw", adapter, "link"])
            if sys.version_info[0] >= 3:
                result_str = result.decode("utf-8")
            else:
                result_str = str(result)
            match = re.search("signal: -(\\d+) dBm", result_str)
            if match:
                return match.group(1)
            else:
                raise ValueError("Regex match failed")
        except Exception:
            # This allow the wifi gauge to return correctly if the above iw method does not work
            result = self.GetWiFiSignalStrenthFromProc(adapter)
            return str(result)

    def GetWiFiSignalQuality(self, adapter: str, JSONNum: bool = False) -> str:
        """
        Gets WiFi link quality using `iwconfig`.

        Args:
            adapter (str): Network adapter name.
            JSONNum (bool, optional): Unused.

        Returns:
            str: Link quality string (e.g. "70/70").
        """
        try:
            result = subprocess.check_output(["iwconfig", adapter])
            if sys.version_info[0] >= 3:
                result_str = result.decode("utf-8")
            else:
                result_str = str(result)
            match = re.search("Link Quality=([\\s\\S]*?) ", result_str)
            if match:
                return match.group(1)
            return ""
        except Exception:
            return ""

    def GetWiFiSSID(self, adapter: str) -> str:
        """
        Gets the WiFi SSID.

        Args:
            adapter (str): Network adapter name.

        Returns:
            str: The SSID string.
        """
        try:
            result = subprocess.check_output(["iwconfig", adapter])
            if sys.version_info[0] >= 3:
                result_str = result.decode("utf-8")
            else:
                result_str = str(result)
            match = re.search('ESSID:"([\\s\\S]*?)"', result_str)
            if match:
                return match.group(1)
            return ""
        except Exception:
            return ""

    def GetWiFiSignalStrenthFromProc(self, adapter: str) -> int:
        """
        Gets WiFi signal strength from `/proc/net/wireless`.

        Args:
            adapter (str): Network adapter name.

        Returns:
            int: Signal strength.
        """
        try:
            ReturnValue = 0
            with open("/proc/net/wireless", "r") as f:
                for line in f:
                    if adapter not in line:
                        continue
                    ListItems = line.split()
                    if len(ListItems) > 4:
                        return int(ListItems[3].replace(".", ""))
                return ReturnValue
        except Exception:
            return 0

    def GetWiFiInfo(self, adapter: str, JSONNum: bool = False) -> List[Dict]:
        """
        Aggregates WiFi connection information.

        Args:
            adapter (str): Network adapter name.
            JSONNum (bool, optional): Unused.

        Returns:
            List[Dict]: WiFi stats (Signal Level, Quality, Noise, SSID).
        """
        WiFiInfo = []

        try:
            with open("/proc/net/wireless", "r") as f:
                for line in f:
                    if adapter not in line:
                        continue
                    ListItems = line.split()
                    if len(ListItems) > 4:

                        signal = self.GetWiFiSignalStrength(JSONNum=JSONNum)
                        if signal != 0:
                            WiFiInfo.append(
                                {"WLAN Signal Level": str(signal) + " dBm"}
                            )
                        else:
                            WiFiInfo.append(
                                {
                                    "WLAN Signal Level": ListItems[3].replace(".", "")
                                    + " dBm"
                                }
                            )
                        # Note that some WLAN drivers make this value based from 0 - 70, others are 0-100
                        # There is no standard on the range
                        try:
                            WiFiInfo.append(
                                {
                                    "WLAN Signal Quality": self.GetWiFiSignalQuality(
                                        adapter, JSONNum=JSONNum
                                    )
                                }
                            )
                        except Exception:
                            WiFiInfo.append(
                                {
                                    "WLAN Signal Quality": ListItems[2].replace(".", "")
                                    + "/70"
                                }
                            )

                        WiFiInfo.append(
                            {
                                "WLAN Signal Noise": ListItems[4].replace(".", "")
                                + " dBm"
                            }
                        )
            essid = self.GetWiFiSSID(adapter)
            if essid is not None and essid != "":
                WiFiInfo.append({"WLAN ESSID": essid})
        except Exception:
            pass
        return WiFiInfo

    @staticmethod
    def InternetConnected() -> bool:
        """
        Checks if internet connectivity is available by pinging google.com.

        Returns:
            bool: True if connected, False otherwise.
        """
        if sys.version_info[0] < 3:
            import httplib
        else:
            import http.client as httplib

        conn = httplib.HTTPConnection("www.google.com", timeout=2)
        try:
            conn.request("HEAD", "/")
            conn.close()
            return True
        except Exception:
            conn.close()
            return False
