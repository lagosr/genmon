#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: controller.py
# PURPOSE: Controller Specific Detils for Base Class
#
#  AUTHOR: Jason G Yates
#    DATE: 24-Apr-2018
#
# MODIFICATIONS:
#
# USAGE: This is the base class of generator controllers. LogError or FatalError
#   should be used to log errors or fatal errors.
#
# -------------------------------------------------------------------------------

"""
Module defining the base GeneratorController class.

This class serves as the foundation for all generator controller implementations.
It manages communication threads, data storage (Modbus registers), logging
(power, fuel, maintenance), and interaction with the user interface and external
systems.
"""

import collections
import copy
import datetime
import json
import os
import re
import sys
import threading
import time
from typing import Optional, List, Dict, Any, Tuple, Union

from genmonlib.mylog import SetupLogger
from genmonlib.myplatform import MyPlatform
from genmonlib.mysupport import MySupport
from genmonlib.mythread import MyThread
from genmonlib.mytile import MyTile
from genmonlib.program_defaults import ProgramDefaults

# Fix Python 2.x. unicode type
if sys.version_info[0] >= 3:  # PYTHON 3
    unicode = str


class GeneratorController(MySupport):
    """
    Base class for all generator controllers.

    This class handles the core logic for monitoring and controlling a generator.
    It abstracts away specific communication protocols (Modbus) and provides a
    unified interface for higher-level applications.

    Attributes:
        log (logging.Logger): Logger instance.
        NewInstall (bool): Flag indicating a new installation.
        Simulation (bool): Flag for simulation mode.
        SimulationFile (str): Path to the simulation data file.
        FeedbackPipe (Any): Pipe for feedback messages.
        MessagePipe (Any): Pipe for user messages (notifications).
        config (Any): Configuration object.
        ModBus (Any): Modbus protocol handler instance.
        InitComplete (bool): Initialization status flag.
        IsStopping (bool): Stopping status flag.
        InitCompleteEvent (threading.Event): Event signaled on init completion.
        CheckForAlarmEvent (threading.Event): Event to trigger alarm checks.
        Holding (OrderedDict): Cache for Holding Registers.
        Strings (OrderedDict): Cache for String Registers.
        FileData (OrderedDict): Cache for File Record Data.
        Coils (OrderedDict): Cache for Coils.
        Inputs (OrderedDict): Cache for Input Registers.
        NotChanged (int): Counter for unchanged registers.
        Changed (int): Counter for changed registers.
        TotalChanged (float): Ratio of changed/unchanged.
        MaintLog (str): Path to maintenance log.
        MaintLogList (List): Cache of maintenance log entries.
        MaintLock (threading.RLock): Lock for maintenance log access.
        OutageLog (str): Path to outage log.
        PowerLog (str): Path to power log.
        FuelLog (str): Path to fuel log.
        TileList (List): List of UI tiles.
        Platform (MyPlatform): Platform interface instance.
        # ... (many other state variables)
    """

    def __init__(
        self,
        log: Any,
        newinstall: bool = False,
        simulation: bool = False,
        simulationfile: Optional[str] = None,
        message: Any = None,
        feedback: Any = None,
        config: Any = None,
        ConfigFilePath: str = ProgramDefaults.ConfPath,
    ):
        """
        Initializes the GeneratorController.

        Args:
            log (Any): Logger instance.
            newinstall (bool, optional): New install flag. Defaults to False.
            simulation (bool, optional): Simulation mode. Defaults to False.
            simulationfile (str, optional): Simulation file path. Defaults to None.
            message (Any, optional): Message pipe. Defaults to None.
            feedback (Any, optional): Feedback pipe. Defaults to None.
            config (Any, optional): Configuration object. Defaults to None.
            ConfigFilePath (str, optional): Config file path. Defaults to ProgramDefaults.ConfPath.
        """
        super(GeneratorController, self).__init__(simulation=simulation)
        self.log = log
        self.NewInstall = newinstall
        self.Simulation = simulation
        self.SimulationFile = simulationfile
        self.FeedbackPipe = feedback
        self.MessagePipe = message
        self.config = config

        self.ModBus: Any = None
        self.InitComplete: bool = False
        self.IsStopping: bool = False
        self.InitCompleteEvent: threading.Event = threading.Event()
        self.CheckForAlarmEvent: threading.Event = threading.Event()

        self.Holding: collections.OrderedDict = collections.OrderedDict()
        self.Strings: collections.OrderedDict = collections.OrderedDict()
        self.FileData: collections.OrderedDict = collections.OrderedDict()
        self.Coils: collections.OrderedDict = collections.OrderedDict()
        self.Inputs: collections.OrderedDict = collections.OrderedDict()

        self.NotChanged: int = 0
        self.Changed: int = 0
        self.TotalChanged: float = 0.0

        self.MaintLog: str = os.path.join(ConfigFilePath, "maintlog.json")
        self.MaintLogList: List[Any] = []
        self.MaintLock: threading.RLock = threading.RLock()

        self.OutageLog: str = os.path.join(ConfigFilePath, "outage.txt")
        self.MinimumOutageDuration: int = 0

        self.PowerLogMaxSize: float = 15.0  # 15 MB max size
        self.PowerLog: str = os.path.join(ConfigFilePath, "kwlog.txt")
        self.MaxPowerLogEntries: int = 8000
        self.PowerLogList: List[List[str]] = []
        self.PowerLock: threading.RLock = threading.RLock()

        self.FuelLog: str = os.path.join(ConfigFilePath, "fuellog.txt")
        self.FuelLock: threading.RLock = threading.RLock()

        self.bAlternateDateFormat: bool = False
        self.HoursFuelRemainingAtLoad: Optional[float] = None
        self.HoursFuelRemainingCurrentLoad: Optional[float] = None
        self.EstimatedFuleInTank: Optional[float] = None

        self.KWHoursMonth: Optional[str] = None
        self.FuelMonth: Optional[str] = None
        self.RunHoursMonth: Optional[str] = None

        self.TileList: List[Any] = []  # Tile list for GUI
        self.TankData: Any = None
        self.FuelLevelOK: Optional[bool] = None
        self.debug: bool = False

        self.UtilityVoltsMin: int = 0
        self.UtilityVoltsMax: int = 0
        self.SystemInOutage: bool = False
        self.TransferActive: bool = False

        self.ControllerSelected: Optional[str] = None

        # The values "Unknown" are checked to validate conf file items are found
        self.FuelType: str = "Unknown"
        self.NominalFreq: str = "Unknown"
        self.NominalRPM: str = "Unknown"
        self.NominalKW: str = "Unknown"
        self.Model: str = "Unknown"
        self.Phase: str = "Unknown"
        self.NominalLineVolts: int = 240
        self.EngineDisplacement: str = "Unknown"
        self.TankSize: int = 0

        self.UseExternalFuelData: bool = False
        self.UseExternalCTData: bool = False
        self.ExternalCTData: Any = None
        self.UseExternalSensorData: bool = False
        self.ExternalSensorData: Any = None
        self.ExternalSensorDataTime: Optional[datetime.datetime] = None
        self.ExternalSensorGagueData: Any = None
        self.ExternalDataLock: threading.RLock = threading.RLock()
        self.DisableOutageCheck: bool = False

        self.ProgramStartTime: datetime.datetime = datetime.datetime.now()
        self.OutageStartTime: datetime.datetime = self.ProgramStartTime
        self.OutageReoccuringNoticeTime: datetime.datetime = self.ProgramStartTime
        self.OutageNoticeDelayTime: Optional[datetime.datetime] = None
        self.LastOutageDuration: datetime.timedelta = self.OutageStartTime - self.OutageStartTime
        self.OutageNoticeDelay: int = 0
        self.Buttons: List[Dict] = []  # UI command buttons

        try:
            self.console = SetupLogger("controller_console", log_file="", stream=True)
            if self.config is not None:
                self.SiteName = self.config.ReadValue("sitename", default="Home")
                self.LogLocation = self.config.ReadValue(
                    "loglocation", default="/var/log/"
                )
                self.UseMetric = self.config.ReadValue(
                    "metricweather", return_type=bool, default=False
                )
                self.debug = self.config.ReadValue(
                    "debug", return_type=bool, default=False
                )
                self.EnableDebug = self.config.ReadValue(
                    "enabledebug", return_type=bool, default=False
                )
                self.bDisplayExperimentalData = self.config.ReadValue(
                    "displayunknown", return_type=bool, default=False
                )
                self.bDisablePowerLog = self.config.ReadValue(
                    "disablepowerlog", return_type=bool, default=False
                )
                self.SubtractFuel = self.config.ReadValue(
                    "subtractfuel", return_type=float, default=0.0
                )
                self.UserURL = self.config.ReadValue("user_url", default="").strip()
                self.FuelUnits = self.config.ReadValue("fuel_units", default="gal")
                self.FuelHalfRate = self.config.ReadValue(
                    "half_rate", return_type=float, default=0.0
                )
                self.FuelFullRate = self.config.ReadValue(
                    "full_rate", return_type=float, default=0.0
                )
                self.UseExternalCTData = self.config.ReadValue(
                    "use_external_power_data", return_type=bool, default=False
                )

                self.UseExternalFuelData = self.config.ReadValue(
                    "use_external_fuel_data", return_type=bool, default=False
                )
                if not self.UseExternalFuelData:
                    # for gentankdiy
                    self.UseExternalFuelData = self.config.ReadValue(
                        "use_external_fuel_data_diy", return_type=bool, default=False
                    )

                self.EstimateLoad = self.config.ReadValue(
                    "estimated_load", return_type=float, default=0.50
                )
                if self.EstimateLoad < 0:
                    self.EstimateLoad = 0
                if self.EstimateLoad > 1:
                    self.EstimateLoad = 1

                self.DisableOutageCheck = self.config.ReadValue(
                    "disableoutagecheck", return_type=bool, default=False
                )
                
                if self.config.HasOption("outagelog"):
                    self.OutageLog = self.config.ReadValue("outagelog")
                    self.LogError(
                        "Using alternate outage logfile: " + str(self.OutageLog)
                    )

                if self.config.HasOption("kwlog"):
                    self.PowerLog = self.config.ReadValue("kwlog")

                if self.config.HasOption("fuel_log"):
                    self.FuelLog = self.config.ReadValue("fuel_log")
                    self.FuelLog = self.FuelLog.strip()

                self.UseFuelLog = self.config.ReadValue(
                    "enable_fuel_log", return_type=bool, default=False
                )
                self.FuelLogFrequency = self.config.ReadValue(
                    "fuel_log_freq", return_type=float, default=15.0
                )

                self.MinimumOutageDuration = self.config.ReadValue(
                    "min_outage_duration", return_type=int, default=0
                )
                self.PowerLogMaxSize = self.config.ReadValue(
                    "kwlogmax", return_type=float, default=15.0
                )
                self.MaxPowerLogEntries = self.config.ReadValue(
                    "max_powerlog_entries", return_type=int, default=8000
                )

                if self.config.HasOption("nominalfrequency"):
                    self.NominalFreq = self.config.ReadValue("nominalfrequency")
                    if not self.StringIsInt(self.NominalFreq):
                        self.NominalFreq = "Unknown"
                if self.config.HasOption("nominalRPM"):
                    self.NominalRPM = self.config.ReadValue("nominalRPM")
                    if not self.StringIsInt(self.NominalRPM):
                        self.NominalRPM = "Unknown"
                if self.config.HasOption("nominalKW"):
                    self.NominalKW = self.config.ReadValue("nominalKW")
                    if not self.StringIsFloat(self.NominalKW):
                        self.NominalKW = "Unknown"
                if self.config.HasOption("model"):
                    self.Model = self.config.ReadValue("model")
                
                self.NominalLineVolts = self.config.ReadValue(
                    "nominallinevolts", return_type=int, default=240
                )

                self.Phase = self.config.ReadValue(
                    "phase", return_type=int, default=1
                )

                if self.config.HasOption("controllertype"):
                    self.ControllerSelected = self.config.ReadValue("controllertype")

                if self.config.HasOption("fueltype"):
                    self.FuelType = self.config.ReadValue("fueltype")

                self.TankSize = self.config.ReadValue(
                    "tanksize", return_type=int, default=0
                )

                self.SmartSwitch = self.config.ReadValue(
                    "smart_transfer_switch", return_type=bool, default=False
                )

                self.OutageNoticeDelay = self.config.ReadValue(
                    "outage_notice_delay", return_type=int, default=0
                )

                self.bDisablePlatformStats = self.config.ReadValue(
                    "disableplatformstats", return_type=bool, default=False
                )
                self.bAlternateDateFormat = self.config.ReadValue(
                    "alternate_date_format", return_type=bool, default=False
                )

                self.ImportButtonFileList = []
                self.ImportedButtons = []
                ImportButtonsFiles = config.ReadValue("import_buttons", default=None)

                if ImportButtonsFiles is not None:
                    if len(ImportButtonsFiles):
                        ImportList = ImportButtonsFiles.strip().split(",")
                        if len(ImportList):
                            for Items in ImportList:
                                self.ImportButtonFileList.append(Items.strip())

                self.OutageNoticeInterval = self.config.ReadValue(
                    "outage_notice_interval", return_type=int, default=0
                )

                self.UnbalancedCapacity = self.config.ReadValue(
                    "unbalanced_capacity", return_type=float, default=0
                )
                if self.bDisablePlatformStats:
                    self.bUseRaspberryPiCpuTempGauge = False
                    self.bUseLinuxWifiSignalGauge = False
                else:
                    self.bUseRaspberryPiCpuTempGauge = self.config.ReadValue(
                        "useraspberrypicputempgauge", return_type=bool, default=True
                    )
                    self.bUseLinuxWifiSignalGauge = self.config.ReadValue(
                        "uselinuxwifisignalgauge", return_type=bool, default=True
                    )
                    self.bWifiIsPercent = self.config.ReadValue(
                        "wifiispercent", return_type=bool, default=False
                    )
        except Exception as e1:
            self.FatalError("Missing config file or config file entries: " + str(e1))

        try:
            if not self.bDisablePlatformStats:
                self.Platform = MyPlatform(
                    log=self.log, usemetric=self.UseMetric, debug=self.debug
                )
                if self.Platform.GetRaspberryPiTemp(ReturnFloat=True) == 0.0:
                    self.LogError("CPU Temp not supported.")
                    self.bUseRaspberryPiCpuTempGauge = False
            else:
                self.Platform = None
        except Exception as e1:
            self.FatalError("Failure loading platform module: " + str(e1))

    def StartCommonThreads(self) -> None:
        """
        Starts background threads common to all controller types.

        Starts threads for alarm checking, processing, debugging (if enabled),
        power metering, maintenance housekeeping, and fuel logging (if enabled).
        """
        self.Threads["CheckAlarmThread"] = MyThread(
            self.CheckAlarmThread, Name="CheckAlarmThread", start=False
        )
        self.Threads["CheckAlarmThread"].Start()

        self.Threads["ProcessThread"] = MyThread(
            self.ProcessThread, Name="ProcessThread", start=False
        )
        self.Threads["ProcessThread"].Start()

        if self.EnableDebug:
            self.Threads["DebugThread"] = MyThread(
                self.DebugThread, Name="DebugThread", start=False
            )
            self.Threads["DebugThread"].Start()

        self.Threads["PowerMeter"] = MyThread(
            self.PowerMeter, Name="PowerMeter", start=False
        )
        self.Threads["PowerMeter"].Start()

        self.Threads["MaintenanceHouseKeepingThread"] = MyThread(
            self.MaintenanceHouseKeepingThread,
            Name="MaintenanceHouseKeepingThread",
            start=False,
        )
        self.Threads["MaintenanceHouseKeepingThread"].Start()

        if self.UseFuelLog:
            self.Threads["FuelLogger"] = MyThread(
                self.FuelLogger, Name="FuelLogger", start=False
            )
            self.Threads["FuelLogger"].Start()

    def CheckForOutageCommon(
        self, UtilityVolts: float, ThresholdVoltage: float, PickupVoltage: float
    ) -> None:
        """
        Common logic for detecting utility power outages.

        Updates min/max utility voltages and determines outage status based on
        voltage thresholds. Sends notifications on status change and logs outages.

        Args:
            UtilityVolts (float): Current utility voltage.
            ThresholdVoltage (float): Voltage below which outage is declared.
            PickupVoltage (float): Voltage above which power is restored.
        """
        try:
            if (
                UtilityVolts is None
                or ThresholdVoltage is None
                or PickupVoltage is None
            ):
                return

            if UtilityVolts < 0 or ThresholdVoltage < 0 or PickupVoltage < 0:
                return
            if UtilityVolts >= (self.NominalLineVolts * 2.5):
                return

            if self.UtilityVoltsMin == 0 and self.UtilityVoltsMax == 0:
                self.UtilityVoltsMin = UtilityVolts
                self.UtilityVoltsMax = UtilityVolts

            if UtilityVolts > self.UtilityVoltsMax:
                if UtilityVolts > PickupVoltage:
                    self.UtilityVoltsMax = UtilityVolts

            if UtilityVolts < self.UtilityVoltsMin:
                if UtilityVolts > ThresholdVoltage:
                    self.UtilityVoltsMin = UtilityVolts

            if self.SystemInOutage:
                if UtilityVolts > PickupVoltage:
                    self.SystemInOutage = False
                    self.LastOutageDuration = (
                        datetime.datetime.now() - self.OutageStartTime
                    )
                    OutageStr = str(self.LastOutageDuration).split(".")[0]
                    msgbody = (
                        "\nUtility Power Restored at "
                        + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        + ". Duration of outage "
                        + OutageStr
                    )
                    self.MessagePipe.SendMessage(
                        "Outage Recovery Notice at " + self.SiteName,
                        msgbody,
                        msgtype="outage",
                    )

                    try:
                        if (
                            self.PowerMeterIsSupported()
                            and self.FuelConsumptionSupported()
                        ):
                            if int(self.LastOutageDuration.total_seconds()) > 0:
                                FuelUsed = self.GetPowerHistory(
                                    "power_log_json=%d,fuel"
                                    % int(self.LastOutageDuration.total_seconds())
                                )
                            else:
                                if self.UseMetric:
                                    FuelUsed = "0 L"
                                else:
                                    FuelUsed = "0 gal"
                            if len(FuelUsed) and "unknown" not in FuelUsed.lower():
                                OutageStr += "," + FuelUsed
                    except Exception as e1:
                        self.LogErrorLine(
                            "Error recording fuel usage for outage: " + str(e1)
                        )

                    if (
                        int(self.LastOutageDuration.total_seconds())
                        > self.MinimumOutageDuration
                    ):
                        self.LogToFile(
                            self.OutageLog,
                            self.OutageStartTime.strftime("%Y-%m-%d %H:%M:%S"),
                            OutageStr,
                        )
                else:
                    self.SendRecuringOutageNotice()
            else:
                if UtilityVolts < ThresholdVoltage:
                    if self.CheckOutageNoticeDelay():
                        self.SystemInOutage = True
                        self.OutageStartTime = datetime.datetime.now()
                        self.OutageReoccuringNoticeTime = datetime.datetime.now()
                        msgbody = (
                            "\nUtility Power Out at "
                            + self.OutageStartTime.strftime("%Y-%m-%d %H:%M:%S")
                        )
                        self.MessagePipe.SendMessage(
                            "Outage Notice at " + self.SiteName,
                            msgbody,
                            msgtype="outage",
                        )
                else:
                    self.OutageNoticeDelayTime = None
        except Exception as e1:
            self.LogErrorLine("Error in CheckForOutageCommon: " + str(e1))
            return

    def SendRecuringOutageNotice(self) -> None:
        """
        Sends recurring notifications during an extended outage.
        """
        try:
            if not self.SystemInOutage:
                return
            if self.OutageNoticeInterval < 1:
                return

            LastOutageDuration = datetime.datetime.now() - self.OutageStartTime
            if LastOutageDuration.total_seconds() <= self.MinimumOutageDuration:
                return

            if (
                datetime.datetime.now() - self.OutageReoccuringNoticeTime
            ).total_seconds() / 60 < self.OutageNoticeInterval:
                return

            self.OutageReoccuringNoticeTime = datetime.datetime.now()
            OutageStr = str(LastOutageDuration).split(".")[0]
            msgbody = (
                "\nUtility Outage Status: Untility power still out at "
                + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                + ". Duration of outage "
                + OutageStr
            )
            self.MessagePipe.SendMessage(
                "Recurring Outage Notice at " + self.SiteName, msgbody, msgtype="outage"
            )
        except Exception as e1:
            self.LogErrorLine("Error in SendRecuringOutageNotice: " + str(e1))
            return

    def CheckOutageNoticeDelay(self) -> bool:
        """
        Checks if the outage delay timer has expired.

        Returns:
            bool: True if outage delay satisfied, False otherwise.
        """
        try:
            if self.OutageNoticeDelay == 0:
                return True

            if self.OutageNoticeDelayTime is None:
                self.OutageNoticeDelayTime = datetime.datetime.now()
                return False

            OutageNoticeDelta = datetime.datetime.now() - self.OutageNoticeDelayTime
            if self.OutageNoticeDelay > OutageNoticeDelta.total_seconds():
                return False

            self.OutageNoticeDelayTime = None
        except Exception as e1:
            self.LogErrorLine("Error in CheckOutageNoticeDelay: " + str(e1))
        return True

    def ProcessThread(self) -> None:
        """
        The main processing thread.

        Initializes the device and loops to perform master emulation (polling registers).
        Handles exceptions and stopping signals.
        """
        try:
            self.ModBus.Flush()
            self.InitDevice()
            if self.IsStopping:
                return
            while True:
                try:
                    if not self.InitComplete:
                        self.InitDevice()
                    else:
                        self.MasterEmulation()
                    if self.IsStopSignaled("ProcessThread"):
                        break
                    if self.IsStopping:
                        break
                except Exception as e1:
                    self.LogErrorLine(
                        "Error in Controller ProcessThread (1), continue: " + str(e1)
                    )
        except Exception as e1:
            self.LogErrorLine("Exiting Controller ProcessThread (2): " + str(e1))

    def CheckAlarmThread(self) -> None:
        """
        Thread for checking alarms.

        Waits for the `CheckForAlarmEvent` to be set and then calls `CheckForAlarms`.
        """
        time.sleep(0.25)
        while True:
            try:
                if self.WaitForExit("CheckAlarmThread", 0.25):
                    return

                if self.CheckForAlarmEvent.is_set():
                    self.CheckForAlarmEvent.clear()
                    self.CheckForAlarms()

            except Exception as e1:
                self.LogErrorLine("Error in  CheckAlarmThread: " + str(e1))

    def TestCommand(self) -> str:
        """
        Test command stub.

        Returns:
            str: "Not Supported".
        """
        return "Not Supported"

    def GeneratorIsRunning(self) -> bool:
        """
        Checks if the generator is currently running.

        Returns:
            bool: True if running, False otherwise.
        """
        return self.GetBaseStatus() in ["EXERCISING", "RUNNING", "RUNNING-MANUAL"]

    def FuelLogger(self) -> None:
        """
        Thread for logging fuel levels.

        Logs fuel level to file at specified frequency if enabled.
        """
        if not self.UseFuelLog:
            return

        time.sleep(0.25)
        while True:
            if self.InitComplete:
                break
            if self.WaitForExit("FuelLogger", 1):
                return

        LastFuelValue = None

        while True:
            try:
                if LastFuelValue is not None and self.WaitForExit(
                    "FuelLogger", self.FuelLogFrequency * 60.0
                ):
                    return

                if (
                    not self.ExternalFuelDataSupported()
                    and not self.FuelTankCalculationSupported()
                    and not self.FuelSensorSupported()
                ):
                    LastFuelValue = 0.0
                    continue

                FuelValue = self.GetFuelLevel(ReturnFloat=True)

                if FuelValue is None:
                    if self.WaitForExit("FuelLogger", self.FuelLogFrequency * 60.0):
                        return
                    continue
                if FuelValue == LastFuelValue:
                    continue

                LastFuelValue = FuelValue
                TimeStamp = datetime.datetime.now().strftime("%x %X")
                with self.FuelLock:
                    self.LogToFile(self.FuelLog, TimeStamp, str(FuelValue))

            except Exception as e1:
                self.LogErrorLine("Error in  FuelLogger: " + str(e1))

    def ClearFuelLog(self) -> str:
        """
        Clears the fuel log file.

        Returns:
            str: Status message.
        """
        try:
            if not len(self.FuelLog):
                return "Fuel Not Present"

            if not os.path.isfile(self.FuelLog):
                return "Power Log is empty"

            with self.FuelLock:
                os.remove(self.FuelLog)
                time.sleep(1)

            return "Fuel Log cleared"
        except Exception as e1:
            self.LogErrorLine("Error in  ClearFuelLog: " + str(e1))
            return "Error in  ClearFuelLog: " + str(e1)

    def DebugThread(self) -> None:
        """
        Thread for debugging register changes.

        Polls registers and reports changes if debug mode is enabled.
        """
        if not self.EnableDebug:
            return
        time.sleep(0.25)

        if (
            not self.ControllerSelected is None
            or not len(self.ControllerSelected)
            or self.ControllerSelected == "generac_evo_nexus"
        ):
            MaxReg = 0x400
        else:
            MaxReg = 0x2000
        self.InitCompleteEvent.wait()

        if self.IsStopping:
            return
        self.LogError("Debug Enabled")
        self.FeedbackPipe.SendFeedback(
            "Debug Thread Starting",
            FullLogs=True,
            Always=True,
            Message="Starting Debug Thread",
        )
        TotalSent = 0

        RegistersUnderTest = collections.OrderedDict()
        RegistersUnderTestData = ""

        while True:

            if self.IsStopSignaled("DebugThread"):
                return
            if TotalSent >= 5:
                self.FeedbackPipe.SendFeedback(
                    "Debug Thread Finished",
                    Always=True,
                    FullLogs=True,
                    Message="Finished Debug Thread",
                )
                if self.WaitForExit("DebugThread", 1):
                    return
                continue
            try:
                for Reg in range(0x0, MaxReg):
                    if self.WaitForExit("DebugThread", 0.25):
                        return
                    Register = "%04x" % Reg
                    NewValue = self.ModBus.ProcessTransaction(
                        Register, 1, skipupdate=True
                    )
                    if not len(NewValue):
                        continue
                    OldValue = RegistersUnderTest.get(Register, "")
                    if OldValue == "":
                        RegistersUnderTest[
                            Register
                        ] = NewValue
                    elif NewValue != OldValue:
                        BitsChanged, Mask = self.GetNumBitsChanged(OldValue, NewValue)
                        RegistersUnderTestData += (
                            "Reg %s changed from %s to %s, Bits Changed: %d, Mask: %x, Engine State: %s\n"
                            % (
                                Register,
                                OldValue,
                                NewValue,
                                BitsChanged,
                                Mask,
                                self.GetEngineState(),
                            )
                        )
                        RegistersUnderTest[Register] = NewValue

                msgbody = "\n"
                try:
                    msgbody += json.dumps(RegistersUnderTest, indent=4, sort_keys=False)
                except Exception:
                    for Register, Value in RegistersUnderTest.items():
                        msgbody += self.printToString("%s:%s" % (Register, Value))

                self.FeedbackPipe.SendFeedback(
                    "Debug Thread (Registers)",
                    FullLogs=True,
                    Always=True,
                    Message=msgbody,
                    NoCheck=True,
                )
                if len(RegistersUnderTestData):
                    self.FeedbackPipe.SendFeedback(
                        "Debug Thread (Changes)",
                        FullLogs=True,
                        Always=True,
                        Message=RegistersUnderTestData,
                        NoCheck=True,
                    )
                RegistersUnderTestData = "\n"
                TotalSent += 1

            except Exception as e1:
                self.LogErrorLine("Error in DebugThread: " + str(e1))

    def GetParameterStringValue(
        self,
        Register: str,
        ReturnString: bool = False,
        offset: Optional[int] = None,
        max: Optional[int] = None,
    ) -> str:
        """
        Retrieves a string parameter from the cache.

        Args:
            Register (str): Register address.
            ReturnString (bool): If True, converts hex to string.
            offset (int, optional): Start offset.
            max (int, optional): End offset.

        Returns:
            str: The parameter value.
        """
        StringValue = self.Strings.get(Register, "")
        if ReturnString:
            if offset is None:
                return self.HexStringToString(StringValue)
            elif offset is not None and max is not None:
                return self.HexStringToString(StringValue[offset:max])
            elif offset is not None and max is None:
                return self.HexStringToString(StringValue[offset:])
            elif offset is None and max is not None:
                return self.HexStringToString(StringValue[:max])
        return StringValue

    def GetParameterFileValue(
        self,
        Register: str,
        ReturnString: bool = False,
        offset: Optional[int] = None,
        max: Optional[int] = None,
    ) -> str:
        """
        Retrieves a file parameter from the cache.

        Args:
            Register (str): Register address.
            ReturnString (bool): If True, converts hex to string.
            offset (int, optional): Start offset.
            max (int, optional): End offset.

        Returns:
            str: The file parameter value.
        """
        StringValue = self.FileData.get(Register, "")
        if ReturnString:
            if offset is None:
                return self.HexStringToString(StringValue)
            elif offset is not None and max is not None:
                return self.HexStringToString(StringValue[offset:max])
            elif offset is not None and max is None:
                return self.HexStringToString(StringValue[offset:])
            elif offset is None and max is not None:
                return self.HexStringToString(StringValue[:max])
        return StringValue

    def GetRegisterValueFromList(
        self, Register: str, IsCoil: bool = False, IsInput: bool = False
    ) -> str:
        """
        Retrieves a register value from the appropriate cache.

        Args:
            Register (str): Register address.
            IsCoil (bool): True if coil.
            IsInput (bool): True if input register.

        Returns:
            str: The register value string.
        """
        try:
            if IsCoil:
                return self.Coils.get(Register, "")
            if IsInput:
                return self.Inputs.get(Register, "")
            return self.Holding.get(Register, "")
        except Exception as e1:
            self.LogErrorLine("Error in GetRegisterValueFromList: " + str(e1))
            return ""

    def GetCoil(
        self, Register: str, OnLabel: Optional[str] = None, OffLabel: Optional[str] = None
    ) -> Union[str, bool]:
        """
        Retrieves the value of a coil.

        Args:
            Register (str): Coil address.
            OnLabel (str, optional): Label for True.
            OffLabel (str, optional): Label for False.

        Returns:
            Union[str, bool]: The coil status (label or boolean).
        """
        try:
            if OnLabel is not None and OffLabel is not None:
                DefaultReturn = False
            else:
                DefaultReturn = OffLabel
            value = self.GetParameterBit(
                Register, 0x01, OnLabel=OnLabel, OffLabel=OffLabel, IsCoil=True
            )
            if OnLabel is not None and OffLabel is not None:
                return value
            if value == 1:
                return True
            return False
        except Exception as e1:
            self.LogErrorLine("Error in GetCoil: " + str(e1))
            return DefaultReturn

    def GetParameterBit(
        self,
        Register: str,
        Mask: int,
        OnLabel: Optional[str] = None,
        OffLabel: Optional[str] = None,
        IsCoil: bool = False,
        IsInput: bool = False,
    ) -> Any:
        """
        Checks if specific bits are set in a register.

        Args:
            Register (str): Register address.
            Mask (int): Bitmask.
            OnLabel (str, optional): Label if bits match.
            OffLabel (str, optional): Label if bits don't match.
            IsCoil (bool): True if coil.
            IsInput (bool): True if input register.

        Returns:
            Any: Label string or boolean status.
        """
        try:
            Value = self.GetRegisterValueFromList(
                Register, IsCoil=IsCoil, IsInput=IsInput
            )
            if not len(Value):
                return ""

            IntValue = int(Value, 16)

            if OnLabel is None or OffLabel is None:
                return self.BitIsEqual(IntValue, Mask, Mask)
            elif self.BitIsEqual(IntValue, Mask, Mask):
                return OnLabel
            else:
                return OffLabel
        except Exception as e1:
            self.LogErrorLine("Error in GetParameterBit: " + str(e1))
            return ""

    def GetParameterLong(
        self,
        RegisterLo: str,
        RegisterHi: str,
        Label: Optional[str] = None,
        Divider: Optional[float] = None,
        ReturnInt: bool = False,
        ReturnFloat: bool = False,
        IsCoil: bool = False,
        IsInput: bool = False,
    ) -> Any:
        """
        Retrieves a 32-bit parameter from two registers.

        Args:
            RegisterLo (str): Low word register address.
            RegisterHi (str): High word register address.
            Label (str, optional): Unit label.
            Divider (float, optional): Divider for scaling.
            ReturnInt (bool): Return integer.
            ReturnFloat (bool): Return float.
            IsCoil (bool): Check coils.
            IsInput (bool): Check input registers.

        Returns:
            Any: The parameter value formatted as requested.
        """
        try:
            if ReturnInt:
                DefaultReturn = 0
            elif ReturnFloat:
                DefaultReturn = 0.0
            else:
                DefaultReturn = ""

            if Label is not None:
                LabelStr = Label
            else:
                LabelStr = ""

            ValueLo = self.GetParameter(
                RegisterLo, IsCoil=IsCoil, IsInput=IsInput
            )
            ValueHi = self.GetParameter(
                RegisterHi, IsCoil=IsCoil, IsInput=IsInput
            )

            if not len(ValueLo) or not len(ValueHi):
                return DefaultReturn

            IntValueLo = int(ValueLo)
            IntValueHi = int(ValueHi)

            IntValue = IntValueHi << 16 | IntValueLo

            if ReturnInt:
                return IntValue

            if Divider is not None:
                FloatValue = IntValue / Divider
                if ReturnFloat:
                    return round(FloatValue, 3)
                return "%2.1f %s" % (FloatValue, LabelStr)
            return "%d %s" % (IntValue, LabelStr)
        except Exception as e1:
            self.LogErrorLine("Error in GetParameterLong: " + str(e1))
            return DefaultReturn

    def GetParameter(
        self,
        Register: str,
        Label: Optional[str] = None,
        Divider: Optional[float] = None,
        Hex: bool = False,
        ReturnInt: bool = False,
        ReturnFloat: bool = False,
        ReturnString: bool = False,
        IsCoil: bool = False,
        IsInput: bool = False,
    ) -> Any:
        """
        Retrieves a single register parameter.

        Args:
            Register (str): Register address.
            Label (str, optional): Unit label.
            Divider (float, optional): Divider for scaling.
            Hex (bool): Return raw hex string.
            ReturnInt (bool): Return integer.
            ReturnFloat (bool): Return float.
            ReturnString (bool): Return ASCII string.
            IsCoil (bool): Check coils.
            IsInput (bool): Check input registers.

        Returns:
            Any: The parameter value formatted as requested.
        """
        try:
            if ReturnInt:
                DefaultReturn = 0
            elif ReturnFloat:
                DefaultReturn = 0.0
            else:
                DefaultReturn = ""

            Value = self.GetRegisterValueFromList(
                Register, IsCoil=IsCoil, IsInput=IsInput
            )
            if not len(Value):
                return DefaultReturn

            if ReturnString:
                return self.HexStringToString(Value)

            if Divider is None and Label is None:
                if Hex:
                    return Value
                elif ReturnFloat:
                    return float(int(Value, 16))
                elif ReturnInt:
                    return int(Value, 16)
                else:
                    return str(int(Value, 16))

            IntValue = int(Value, 16)
            if Divider is not None:
                FloatValue = IntValue / Divider
                if ReturnInt:
                    return int(FloatValue)
                if ReturnFloat:
                    return round(FloatValue, 3)
                if Label is not None:
                    return "%.2f %s" % (FloatValue, Label)
                else:
                    return "%.2f" % (FloatValue)
            elif ReturnInt:
                return IntValue
            elif Label is not None:
                return "%d %s" % (IntValue, Label)
            else:
                return str(int(Value, 16))

        except Exception as e1:
            self.LogErrorLine(
                "Error in GetParameter: Reg: " + Register + ": " + str(e1)
            )
            return ""

    def GetConfig(self) -> bool:
        """
        Reads configuration file (Stub).

        Returns:
            bool: True.
        """
        return True

    def SystemInAlarm(self) -> bool:
        """
        Checks if system is in alarm state.

        Returns:
            bool: False (default).
        """
        return False

    def SetCommandButton(self, CommandString: str) -> str:
        """
        Processes a command button request from the UI.

        Args:
            CommandString (str): The command string (e.g. "set_button_command=[...]").

        Returns:
            str: "OK" on success, error message otherwise.
        """
        try:
            ValidInput = False
            EntryString = CommandString
            if EntryString is None or not len(EntryString):
                return "Error: Invalid input for Set Button Command entry."

            EntryString = EntryString.strip()
            if EntryString.startswith("set_button_command"):
                EntryString = EntryString[len("set_button_command") :]
                EntryString = EntryString.strip()
                if EntryString.strip().startswith("="):
                    EntryString = EntryString[len("=") :]
                    EntryString = EntryString.strip()
                    ValidInput = True

            if ValidInput:
                try:
                    CommandSetList = json.loads(EntryString)
                    # validate object
                    if not isinstance(CommandSetList, list) and not (len(CommandSetList) == 0):
                        self.LogError("Invalid button object in SetCommandButton")
                        return "Error: Invalid button object"
                    # Execute Command
                    return self.ExecuteRemoteCommand(CommandSetList)
                except Exception as e1:
                    self.LogErrorLine("Error in SetCommandButton: " + str(e1))
                    return "Error: Invalid input for SetCommandButton (2), see error log."
            else:
                self.LogError("Error in SetCommandButton: invalid input: " + str(CommandString))
                return "Error: Invalid input for SetCommandButton (3)."
            return "OK"
        except Exception as e1:
            self.LogErrorLine("Error in SetCommandButton: " + str(e1))
            return "Error in SetCommandButton, see error log."
        return "OK"

    def GetButtons(self, singlebuttonname: Optional[str] = None) -> List[Dict]:
        """
        Retrieves list of available UI buttons.

        Args:
            singlebuttonname (str, optional): Filter by specific button command.

        Returns:
            List[Dict]: List of button definitions.
        """
        try:
            if len(self.Buttons) < 1:
                return []
            button_list = self.Buttons
            button_list = self.GetButtonsCommon(button_list, singlebuttonname=singlebuttonname)
            return button_list
        except Exception as e1:
            self.LogErrorLine("Error in GetButtons: " + str(e1))
            return []

    def LoadButtonsFromFile(self) -> List[Dict]:
        """
        Loads custom button definitions from file.

        Returns:
            List[Dict]: List of loaded buttons.
        """
        try:
            if self.ImportButtonFileList is None or len(self.ImportButtonFileList) == 0:
                return []
            ImportedButtons = []

            for FileName in self.ImportButtonFileList:
                ConfigFileName = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
                    "data",
                    "commands",
                    FileName
                )
                if os.path.isfile(ConfigFileName):
                    try:
                        with open(ConfigFileName) as infile:
                            command_import = json.load(infile)
                            ImportedButtons.extend(command_import["buttons"])

                    except Exception as e1:
                        self.LogErrorLine("Error in LoadButtonsFromFile reading config import file: " + str(e1))
                        continue
                else:
                    self.LogError("Error in LoadButtonsFromFile reading button import file: " + str(ConfigFileName))
                    continue

        except Exception as e1:
            self.LogErrorLine("Error in LoadButtonsFromFile: " + str(e1))

        return ImportedButtons

    def GetButtonsCommon(
        self, button_list: List[Dict], singlebuttonname: Optional[str] = None
    ) -> Union[List[Dict], Dict]:
        """
        Common logic for retrieving and validating buttons.

        Args:
            button_list (List[Dict]): Initial list of buttons.
            singlebuttonname (str, optional): Filter.

        Returns:
            Union[List[Dict], Dict]: Button list or single button dict.
        """
        try:
            if len(self.ImportButtonFileList) == 0 and button_list is None:
                return []

            if not len(self.ImportedButtons):
                self.ImportedButtons = self.LoadButtonsFromFile()

                # combine lists only on first (and only) import
                if button_list is None or len(button_list) == 0:
                    button_list = self.ImportedButtons
                else:
                    button_list.extend(self.ImportedButtons)

            if not isinstance(button_list, list):
                self.LogError("Error in GetButtonsCommon: invalid input or data: "+ str(type(button_list)))
                return []

            # Validate buttons before sending to the web app
            return_buttons = []
            for button in button_list:
                
                if "onewordcommand" not in button.keys():
                    self.LogError("Error in GetButtonsCommon: button must have onewordcommand element: "+ str(button))
                    continue
                elif not isinstance(button["onewordcommand"], str):
                    self.LogError("Error in GetButtonsCommon: invalid button defined validateing onewordcommand (non string): "+ str(button))
                    continue
                if "title" not in button.keys():
                    self.LogError("Error in GetButtonsCommon: button must have title element: "+ str(button))
                    continue
                elif not isinstance(button["title"], str):
                    self.LogError("Error in GetButtonsCommon: invalid button defined validateing title (not string): "+ str(button))
                    continue
                if "command_sequence" not in button.keys():
                    self.LogError("Error in GetButtonsCommon: button must have command_sequence element: "+ str(button))
                    continue
                elif not isinstance(button["command_sequence"], list):
                    self.LogError("Error in GetButtonsCommon: invalid button defined validateing command_sequence:(not list) "+ str(button))
                    continue
                
                # valiate command sequeuence
                CommandError = False
                for command in button["command_sequence"]:
                    if "reg" not in command.keys() or not isinstance(command["reg"], str):
                        self.LogError("Error in GetButtonsCommon: invalid command string defined validateing reg: "+ str(button))
                        CommandError = True
                        break
                    if "reg_type" in command.keys():
                        if not command["reg_type"].lower() in ["holding","coil","script","singlecoil","singleholding"]:
                            self.LogError("Error in GetButtonsCommon: Error validateing re_type: "+ str(button))
                            CommandError = True
                            break

                    if "value" not in command.keys():
                        if "reg_type" in command.keys() and command["reg_type"].lower() == "script":
                            # other fields are not required, "reg" has script name
                            continue
                        # this command requires input from the web app, let's validate the params
                        # "input_title", "type" is required. "length" is default 2 but must be a multiple of 2
                        if "input_title" not in command.keys() or "type" not in command.keys():
                            self.LogError("Error in GetButtonsCommon: Error validateing input_title and type: "+ str(button))
                            CommandError = True
                            break
                        if "length" in command.keys():
                            if(int(command["length"]) % 2 != 0):
                                self.LogError("Error in GetButtonsCommon: length of command_sequence input must be a multiple of 2: " + str(button))
                                CommandError = True
                                break
                        if "bounds_regex" in command.keys():
                            if not self.RegExIsValid(command["bounds_regex"]):
                                self.LogError("Error in GetButtonsCommon: invalid regular expression for bounds_regex in command_sequence: " + str(button))
                                CommandError = True
                                break
                if CommandError:
                    continue

                if singlebuttonname is not None and singlebuttonname == button["onewordcommand"]:
                    return button

                return_buttons.append(button)

            return return_buttons
        except Exception as e1:
            self.LogErrorLine("Error in GetButtonsCommon: " + str(e1))
            self.ImportedButtons = []
            return []

    def ExecuteRemoteCommand(self, CommandSetList: List[Dict]) -> str:
        """
        Executes a remote command set.

        Args:
            CommandSetList (List[Dict]): List of command dictionaries.

        Returns:
            str: "OK" on success, error message otherwise.
        """
        try:
            if sys.version_info[0] < 3:  #
                self.LogError("Error in ExecuteRemoteCommand, requires python3: " + str(sys.version_info.major) + "." + str(sys.version_info.minor))
                return "Error in ExecuteRemoteCommand, requires python3"
            if not isinstance(CommandSetList, list):
                return "Error: invalid input in ExecuteRemoteCommand"
            
            with self.ModBus.CommAccessLock:
                # put the lock here so if there are multiple commands they will be executed back to back
                for button_command in CommandSetList:
                    if not isinstance(button_command, dict) and not len(button_command) == 1:
                        self.LogError("Error on ExecuteRemoteCommand, expecting single dict: " + str(button_command))
                        return "Error: invalid input in ExecuteRemoteCommand"
                    if "onewordcommand" not in button_command.keys():
                        self.LogError("Error on ExecuteRemoteCommand, invalid dict: " + str(button_command))
                        return "Error: invalid input in ExecuteRemoteCommand (2)"
                    # make a copy of the dict so we can add the input without modifying the original
                    returndict = self.GetButtons(singlebuttonname = button_command["onewordcommand"])
                    if returndict is None:
                        self.LogError("Error on ExecuteRemoteCommand, command not found: " + str(button_command))
                        return "Error: invalid input in ExecuteRemoteCommand command not found"
                    selected_command = copy.deepcopy(returndict)
                    if not len(selected_command):
                        self.LogError("Error on ExecuteRemoteCommand, invalid command: " + str(button_command))
                        return "Error: invalid command in ExecuteRemoteCommand (2)"
                    
                    # selected_command from genmon, button_command from UI
                    if "command_sequence" not in selected_command.keys() or "command_sequence" not in button_command.keys():
                        self.LogError("Error on ExecuteRemoteCommand, command sequence mismatch: " + str(button_command))
                        return "Error on ExecuteRemoteCommand, command sequence mismatch"
                    if not (len(selected_command["command_sequence"]) == len(button_command["command_sequence"])):
                        self.LogError("Error on ExecuteRemoteCommand, command sequence mismatch (2): " + str(button_command))
                        return "Error on ExecuteRemoteCommand, command sequence mismatch (2)"
                    # iterate thru both lists of commands
                    for gm_cmd, ui_cmd in zip(selected_command["command_sequence"], button_command["command_sequence"]):
                        if "input_title" in gm_cmd.keys() and "value" in ui_cmd.keys():
                            if "bounds_regex" in gm_cmd.keys():
                                if not re.match(gm_cmd["bounds_regex"], str(ui_cmd["value"])):
                                    self.LogError("Error in ExecuteRemoteCommand: Failed bounds check: " + str(ui_cmd))
                                    return "Error in ExecuteRemoteCommand: Failed bounds check"
                            if "type" in gm_cmd.keys() and gm_cmd["type"] == "int":
                                if "length" not in gm_cmd.keys() or ("length" in gm_cmd.keys() and gm_cmd["length"] == 2):
                                    gm_cmd["value"] = "%04x" % int(ui_cmd["value"])
                                elif "length" in gm_cmd and gm_cmd["length"] == 4:
                                    gm_cmd["value"] = "%08x" % int(ui_cmd["value"])
                                else:
                                    self.LogError("Error in ExecuteRemoteCommand: only 2 or 4 supported for int lenght: " + str(gm_cmd))
                                    return "Error in ExecuteRemoteCommand, invalid length of input"
                            else:
                                self.LogError("Error in ExecuteRemoteCommand, unsupported type: " + str(ui_cmd))
                                return "Error in ExecuteRemoteCommand, unsupported type"
                        elif "reg" not in gm_cmd.keys() or "value" not in gm_cmd.keys():
                            self.LogError("Error in ExecuteRemoteCommand, invalid command in sequence: " + str(selected_command))
                            self.LogDebug(str(button_command))
                            return "Error in ExecuteRemoteCommand, invalid command in sequence"
                    # execute the command selected_command
                    return self.ExecuteCommandSequence(selected_command["command_sequence"])

        except Exception as e1:
            self.LogErrorLine("Error in ExecuteRemoteCommand: " + str(e1))
            self.LogDebug(str(CommandSetList))
            return "Error in ExecuteRemoteCommand"
        return "OK"

    def ExecuteCommandSequence(self, command_sequence: List[Dict]) -> str:
        """
        Executes a sequence of commands.

        Args:
            command_sequence (List[Dict]): List of commands to execute.

        Returns:
            str: "OK" on success.
        """
        try:
            with self.ModBus.CommAccessLock:
                for command in command_sequence:
                    IsCoil = False      # can only be holding or coil
                    IsSingle = False
                    if "reg" not in command.keys():
                        self.LogDebug("Error in ExecuteCommandSequence: invalid value array, no 'reg' in command_sequence command: " + str(command))
                        continue
                    if "reg_type" in command.keys() and command["reg_type"] == "script":
                        # if we get here then we execute a script with the filename of the "reg" entry
                        ScriptFileName = os.path.join(
                            os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
                            "data",
                            "commands",
                            "script",
                            command["reg"]
                        )
                        
                        try:
                            import subprocess

                            OutputStream = subprocess.PIPE
                            executelist = [sys.executable, ScriptFileName]
                            pid = subprocess.Popen(
                                executelist,
                                stdout=OutputStream,
                                stderr=OutputStream,
                                stdin=OutputStream,
                            )
                            #subprocess.call(ScriptFileName, shell=True)
                            self.LogDebug("Script Name: " + ScriptFileName)
                        except Exception as e1:
                            self.LogErrorLine("Error calling script for button: " + ScriptFileName + " : " + str(e1))
                        continue
                    if not isinstance(command["value"], int) and not len(command["value"]):
                        self.LogDebug("Error in ExecuteCommandSequence: invalid value array")
                        continue
                    if "reg_type" in command.keys() and command["reg_type"] == "coil":
                        IsCoil = True
                    if "reg_type" in command.keys() and command["reg_type"] == "singlecoil":
                        IsCoil = True
                        IsSingle = True
                    if "reg_type" in command.keys() and command["reg_type"] == "singleholding":
                        IsSingle = True

                    if isinstance(command["value"], list):
                        if not (len(command["value"]) % 2) == 0:
                            self.LogDebug("Error in ExecuteCommandSequence: invalid value length")
                            return "Command not found."
                        Data = []
                        for item in command["value"]:
                            if isinstance(item, str):
                                Data.append(int(item, 16))
                            elif isinstance(item, int):
                                Data.append(item)
                            else:
                                self.LogDebug("Error in ExecuteCommandSequence: invalid type if value list")
                                return "Command not found."
                        self.LogDebug("Write List: len: " + str(int(len(Data)  / 2)) + " : "  + self.LogHexList(Data, prefix=command["reg"], nolog = True))
                        self.ModBus.ProcessWriteTransaction(command["reg"], len(Data) / 2, Data, IsCoil = IsCoil, IsSingle = IsSingle)

                    elif isinstance(command["value"], str):
                        # only supports single word writes
                        value = int(command["value"], 16)
                        LowByte = value & 0x00FF
                        HighByte = (value >> 8) & 0x00ff
                        Data = []
                        Data.append(HighByte)  
                        Data.append(LowByte)  
                        self.LogDebug("Write Str: len: "+ str(int(len(Data)  / 2)) + " : " + command["reg"] + ": "+ ("%04x %04x" % (HighByte, LowByte)))
                        self.ModBus.ProcessWriteTransaction(command["reg"], len(Data) / 2, Data, IsCoil = IsCoil, IsSingle = IsSingle)
                    elif isinstance(command["value"], int):
                        # only supports single word writes
                        value = command["value"]
                        LowByte = value & 0x00FF
                        HighByte = (value >> 8) & 0x00ff
                        Data = []
                        Data.append(HighByte)  
                        Data.append(LowByte)  
                        self.LogDebug("Write Int: len: "+ str(int(len(Data)  / 2)) + " : " + command["reg"]+ ": "+ ("%04x %04x" % (HighByte, LowByte)))
                        self.ModBus.ProcessWriteTransaction(command["reg"], len(Data) / 2, Data, IsCoil = IsCoil, IsSingle = IsSingle)
                    else:
                        self.LogDebug("Error in ExecuteCommandSequence: invalid value type")
                        return "Command not found."

                return "OK"
        except Exception as e1:
            self.LogErrorLine("Error in ExecuteCommandSequence: " + str(e1))
            self.LogDebug(str(command_sequence))
            return "Error in ExecuteCommandSequence"
        return "OK"

    def GetStartInfo(self, NoTile: bool = False) -> Dict[str, Any]:
        """
        Generates startup info for the UI.

        Args:
            NoTile (bool): If True, exclude tile data.

        Returns:
            Dict[str, Any]: Startup configuration info.
        """
        StartInfo = {}
        try:
            StartInfo["fueltype"] = self.FuelType
            StartInfo["model"] = self.Model
            StartInfo["nominalKW"] = self.NominalKW
            StartInfo["nominalRPM"] = self.NominalRPM
            StartInfo["nominalfrequency"] = self.NominalFreq
            StartInfo["phase"] = self.Phase
            StartInfo["Controller"] = "Generic Controller Name"
            StartInfo["PowerGraph"] = self.PowerMeterIsSupported()
            StartInfo["NominalBatteryVolts"] = "12"
            StartInfo["UtilityVoltageDisplayed"] = True
            StartInfo["RemoteCommands"] = True
            StartInfo["RemoteButtons"] = False
            if self.Platform is not None:
                StartInfo["Linux"] = self.Platform.IsOSLinux()
                StartInfo["RaspberryPi"] = self.Platform.IsPlatformRaspberryPi()

            if not NoTile:

                StartInfo["buttons"] = self.GetButtons()

                StartInfo["tiles"] = []
                for Tile in self.TileList:
                    StartInfo["tiles"].append(Tile.GetStartInfo())

        except Exception as e1:
            self.LogErrorLine("Error in GetStartInfo: " + str(e1))
        return StartInfo

    def GetStatusForGUI(self) -> Dict[str, Any]:
        """
        Generates current status for the UI.

        Returns:
            Dict[str, Any]: Current status data.
        """
        Status = {}
        try:
            Status["basestatus"] = self.GetBaseStatus()
            Status["switchstate"] = self.GetSwitchState()
            Status["enginestate"] = self.GetEngineState()
            Status["kwOutput"] = self.GetPowerOutput()
            Status["OutputVoltage"] = "0V"
            Status["BatteryVoltage"] = "0V"
            Status["UtilityVoltage"] = "0V"
            Status["Frequency"] = "0"
            Status["RPM"] = "0"

            # Exercise Info is a dict containing the following:
            ExerciseInfo = collections.OrderedDict()
            ExerciseInfo["Enabled"] = False
            ExerciseInfo["Frequency"] = "Weekly"  # Biweekly, Weekly or Monthly
            ExerciseInfo["Hour"] = "14"
            ExerciseInfo["Minute"] = "00"
            ExerciseInfo["QuietMode"] = "On"
            ExerciseInfo["EnhancedExerciseMode"] = False
            ExerciseInfo["Day"] = "Monday"
            Status["ExerciseInfo"] = ExerciseInfo
        except Exception as e1:
            self.LogErrorLine("Error in GetStatusForGUI: " + str(e1))
        return Status

    # ---------------------GeneratorController::DisplayLogs----------------------
    def DisplayLogs(
        self, AllLogs: bool = False, DictOut: bool = False, RawOutput: bool = False
    ) -> Any:
        """
        Displays log data.

        Args:
            AllLogs (bool): Show all logs.
            DictOut (bool): Return dictionary.
            RawOutput (bool): Return raw data.
        """
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in DisplayLogs: " + str(e1))

    # ------------ GeneratorController::DisplayMaintenance ----------------------
    def DisplayMaintenance(self, DictOut: bool = False, JSONNum: bool = False) -> Any:
        """
        Displays maintenance info.

        Args:
            DictOut (bool): Return dict.
            JSONNum (bool): Numeric format for JSON.
        """
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in DisplayMaintenance: " + str(e1))

    # ------------ GeneratorController::DisplayStatus ---------------------------
    def DisplayStatus(self, DictOut: bool = False, JSONNum: bool = False) -> Any:
        """
        Displays general status.

        Args:
            DictOut (bool): Return dict.
            JSONNum (bool): Numeric format for JSON.
        """
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in DisplayStatus: " + str(e1))

    # ------------------- GeneratorController::DisplayOutage --------------------
    def DisplayOutage(self, DictOut: bool = False, JSONNum: bool = False) -> Any:
        """
        Displays outage info.

        Args:
            DictOut (bool): Return dict.
            JSONNum (bool): Numeric format for JSON.
        """
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in DisplayOutage: " + str(e1))

    # ------------ GeneratorController::DisplayRegisters ------------------------
    def DisplayRegisters(self, AllRegs: bool = False, DictOut: bool = False) -> Any:
        """
        Displays register contents.

        Args:
            AllRegs (bool): Show all registers.
            DictOut (bool): Return dict.
        """
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in DisplayRegisters: " + str(e1))

    # ------------ Evolution:GetMessageText ------------------------------------
    def GetMessageText(self) -> str:
        """
        Returns comprehensive status message text.

        Returns:
            str: Status message.
        """
        try:
            msgtext = self.DisplayStatus()
            msgtext += self.DisplayMaintenance()
            return msgtext
        except Exception as e1:
            self.LogErrorLine("Error in GetMessageText: " + str(e1))
            return ""

    def SetGeneratorTimeDate(self) -> str:
        """
        Sets generator time to system time.

        Returns:
            str: Status message.
        """
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in SetGeneratorTimeDate: " + str(e1))

        return "Not Supported"

    def SetGeneratorQuietMode(self, CmdString: str) -> str:
        """
        Sets quiet mode.

        Args:
            CmdString (str): "setquiet=yes" or "setquiet=no"

        Returns:
            str: Status message.
        """
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in SetGeneratorQuietMode: " + str(e1))

        return "Not Supported"

    def SetGeneratorExerciseTime(self, CmdString: str) -> str:
        """
        Sets exercise time.

        Args:
            CmdString (str): Exercise settings string.

        Returns:
            str: Status message.
        """
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in SetGeneratorExerciseTime: " + str(e1))

        return "Not Supported"

    def SetGeneratorRemoteCommand(self, CmdString: str) -> str:
        """
        Sends a remote command to the generator.

        Args:
            CmdString (str): "setremote=command"

        Returns:
            str: Status message.
        """
        try:
            pass
        except Exception as e1:
            self.LogErrorLine("Error in SetGeneratorRemoteStartStop: " + str(e1))

        return "Not Supported"

    def GetController(self, Actual: bool = True) -> str:
        """
        Gets the controller name.

        Args:
            Actual (bool): Return detected controller or configured override.

        Returns:
            str: Controller name.
        """
        return "Test Controller"

    def ComminicationsIsActive(self) -> bool:
        """
        Checks if communication is active.

        Returns:
            bool: True if active, False otherwise.
        """
        return False

    def ResetCommStats(self) -> None:
        """Resets communication statistics."""
        self.ModBus.ResetCommStats()

    def RemoteButtonsSupported(self) -> bool:
        """
        Checks if remote buttons are supported.

        Returns:
            bool: True if supported.
        """
        return False

    def PowerMeterIsSupported(self) -> bool:
        """
        Checks if power metering is supported.

        Returns:
            bool: True if supported.
        """
        return False

    def GetPowerOutput(self, ReturnFloat: bool = False) -> Union[str, float]:
        """
        Gets current power output.

        Args:
            ReturnFloat (bool): Return as float.

        Returns:
            Union[str, float]: Power output.
        """
        return ""

    def GetCommStatus(self) -> Any:
        """
        Gets communication status stats.

        Returns:
            Any: Stats dict.
        """
        return self.ModBus.GetCommStats()

    def GetRunHours(self) -> str:
        """
        Gets total run hours.

        Returns:
            str: Run hours.
        """
        return "Unknown"

    def GetBaseStatus(self) -> str:
        """
        Gets the base generator status (OFF, READY, RUNNING, etc).

        Returns:
            str: Status string.
        """
        return "OFF"

    def GetOneLineStatus(self) -> str:
        """
        Gets a concise one-line status.

        Returns:
            str: Status string.
        """
        return self.GetSwitchState() + " : " + self.GetEngineState()

    def GetRegValue(self, CmdString: str) -> str:
        """
        Gets a raw register value based on a command string.

        Args:
            CmdString (str): "getregvalue=REGISTER"

        Returns:
            str: Register value.
        """
        msgbody = "Invalid command syntax for command getregvalue"
        try:
            # Format we are looking for is "getregvalue=01f4"
            CmdList = CmdString.split("=")
            if len(CmdList) != 2:
                self.LogError(
                    "Validation Error: Error parsing command string in GetRegValue (parse): "
                    + CmdString
                )
                return msgbody

            CmdList[0] = CmdList[0].strip()

            if not CmdList[0].lower() == "getregvalue":
                self.LogError(
                    "Validation Error: Error parsing command string in GetRegValue (parse2): "
                    + CmdString
                )
                return msgbody

            Register = CmdList[1].strip()

            RegValue = self.GetRegisterValueFromList(Register)

            if RegValue == "":
                self.LogError("Validation Error: Register  not known:" + Register)
                msgbody = "Unsupported Register: " + Register
                return msgbody

            msgbody = RegValue

        except Exception as e1:
            self.LogErrorLine(
                "Validation Error: Error parsing command string in GetRegValue: "
                + CmdString
            )
            self.LogError(str(e1))
            return msgbody

        return msgbody

    def ReadRegValue(self, CmdString: str) -> str:
        """
        Reads a register directly from the device.

        Args:
            CmdString (str): "readregvalue=REGISTER"

        Returns:
            str: Register value.
        """
        msgbody = "Invalid command syntax for command readregvalue"
        try:

            CmdList = CmdString.split("=")
            if len(CmdList) != 2:
                self.LogError(
                    "Validation Error: Error parsing command string in ReadRegValue (parse): "
                    + CmdString
                )
                return msgbody

            CmdList[0] = CmdList[0].strip()

            if not CmdList[0].lower() == "readregvalue":
                self.LogError(
                    "Validation Error: Error parsing command string in ReadRegValue (parse2): "
                    + CmdString
                )
                return msgbody

            Register = CmdList[1].strip()

            RegValue = self.ModBus.ProcessTransaction(Register, 1, skipupdate=True)

            if RegValue == "":
                self.LogError(
                    "Validation Error: Register not known (ReadRegValue):" + Register
                )
                msgbody = "Unsupported Register: " + Register
                return msgbody

            msgbody = RegValue

        except Exception as e1:
            self.LogErrorLine(
                "Validation Error: Error parsing command string in ReadRegValue: "
                + CmdString
            )
            self.LogError(str(e1))
            return msgbody

        return msgbody

    def WriteRegValue(self, CmdString: str) -> str:
        """
        Writes a value to a register.

        Args:
            CmdString (str): "writeregvalue=REGISTER,VALUE"

        Returns:
            str: "OK" or error message.
        """
        msgbody = "Invalid command syntax for command writeregvalue"
        try:

            CmdList = CmdString.split("=")
            if len(CmdList) != 2:
                self.LogError("Validation Error: Error parsing command string in WriteRegValue (parse): " + CmdString)
                return msgbody

            CmdList[0] = CmdList[0].strip()

            if not CmdList[0].lower() == "writeregvalue":
                self.LogError("Validation Error: Error parsing command string in WriteRegValue (parse2): " + CmdString)
                return msgbody

            ParsedList = CmdList[1].split(",")

            if len(ParsedList) != 2:
                self.LogError("Validation Error: Error parsing command string in WriteRegValue (parse3): " + CmdString)
                return msgbody
            Register = ParsedList[0].strip()
            ValueStr = ParsedList[1].strip()
            Value = int(ValueStr,16)
            LowByte = Value & 0x00FF
            HighByte = Value >> 8
            Data = []
            Data.append(HighByte)
            Data.append(LowByte)
            RegValue = self.ModBus.ProcessWriteTransaction(Register, len(Data) / 2, Data)

            if RegValue == "":
                msgbody = "OK"

        except Exception as e1:
            self.LogErrorLine("Validation Error: Error parsing command string in WriteRegValue: " + CmdString)
            self.LogError(str(e1))
            return msgbody

        return msgbody

    def DisplayOutageHistory(self, JSONNum: bool = False) -> Union[List[str], List[Dict]]:
        """
        Formats the outage history log.

        Args:
            JSONNum (bool): Use numeric format for JSON output.

        Returns:
            Union[List[str], List[Dict]]: List of outage strings or dicts.
        """
        LogHistory = []

        if not len(self.OutageLog):
            return []
        try:
            # check to see if a log file exist yet
            if not os.path.isfile(self.OutageLog):
                return []

            OutageLog = []

            with open(self.OutageLog, "r") as OutageFile:  # opens file

                for line in OutageFile:
                    line = line.strip()  # remove whitespace at beginning and end

                    if not len(line):
                        continue
                    if line[0] == "#":  # comment?
                        continue
                    line = self.removeNonPrintable(line)
                    Items = line.split(",")
                    # Three items is for duration greater than 24 hours, i.e 1 day, 08:12
                    if len(Items) < 2:
                        continue
                    strDuration = ""
                    strFuel = ""
                    if len(Items) == 2:
                        # Only date and duration less than a day
                        strDuration = Items[1]
                    elif (len(Items) == 3) and ("day" in Items[1]):
                        #  date and outage greater than 24 hours
                        strDuration = Items[1] + "," + Items[2]
                    elif len(Items) == 3:
                        # date, outage less than 1 day, and fuel
                        strDuration = Items[1]
                        strFuel = Items[2]
                    elif len(Items) == 4 and ("day" in Items[1]):
                        # date, outage less greater than 1 day, and fuel
                        strDuration = Items[1] + "," + Items[2]
                        strFuel = Items[3]
                    else:
                        continue

                    if len(strDuration) and len(strFuel):
                         OutageLog.insert(0, [Items[0], strDuration, strFuel])
                    elif len(strDuration):
                        OutageLog.insert(0, [Items[0], strDuration])

                    if len(OutageLog) > 100:  # limit log to 100 entries
                        OutageLog.pop()

            index = 0
            for Items in OutageLog:
                if len(Items) > 1:
                    try:
                        # should be format yyyy-mm-dd hh:mm:ss
                        EntryDate = datetime.datetime.strptime(Items[0], "%Y-%m-%d %H:%M:%S")
                        if self.bAlternateDateFormat:
                            FormattedDate = EntryDate.strftime("%d-%m-%Y %H:%M:%S")
                        else:
                            FormattedDate = EntryDate.strftime("%m-%d-%Y %H:%M:%S")
                    except Exception as e1:
                        self.LogErrorLine("Error parsing date/time in outage log: " + str(e1))
                        continue
                if len(Items) == 2:
                    if JSONNum:
                        LogHistory.append({index: [{"Date": FormattedDate}, {"Duration": Items[1]}]})
                    else:   
                        LogHistory.append("%s, Duration: %s" % (FormattedDate, Items[1]))
                elif len(Items) == 3:
                    if JSONNum:
                        LogHistory.append({index:[{"Date": FormattedDate}, {"Duration": Items[1]},{"Estimated Fuel": Items[2]}]})
                    else:
                        LogHistory.append("%s, Duration: %s, Estimated Fuel: %s"% (FormattedDate, Items[1], Items[2]))
                index += 1

            return LogHistory

        except Exception as e1:
            self.LogErrorLine("Error in  DisplayOutageHistory: " + str(e1))
            return []

    def LogToPowerLog(self, TimeStamp: str, Value: str) -> None:
        """
        Logs power value to file.

        Args:
            TimeStamp (str): Timestamp string.
            Value (str): Power value string.
        """
        try:
            TimeStamp = self.removeNonPrintable(TimeStamp)
            Value = self.removeNonPrintable(Value)
            if not len(TimeStamp) or not len(Value):
                self.LogError(
                    "Invalid entry in LogToPowerLog: "
                    + str(TimeStamp)
                    + ","
                    + str(Value)
                )
                return
            if len(self.PowerLogList):
                self.PowerLogList.insert(0, [TimeStamp, Value])
            self.LogToFile(self.PowerLog, TimeStamp, Value)
        except Exception as e1:
            self.LogErrorLine("Error in LogToPowerLog: " + str(e1))

    def GetPowerLogFileDetails(self) -> str:
        """
        Gets power log file size info.

        Returns:
            str: File size details.
        """
        if not self.PowerMeterIsSupported():
            return "Not Supported"
        try:
            LogSize = os.path.getsize(self.PowerLog)
            outstr = "%.2f MB of %.2f MB" % (
                (float(LogSize) / (1024.0 * 1024.0)),
                self.PowerLogMaxSize,
            )
            return outstr
        except Exception as e1:
            self.LogErrorLine("Error in GetPowerLogFileDetails : " + str(e1))
            return "Unknown"

    def PrunePowerLog(self, Minutes: int) -> str:
        """
        Reduces power log size by removing old entries.

        Args:
            Minutes (int): Keep entries newer than this age in minutes.

        Returns:
            str: Status message.
        """
        if not Minutes:
            self.LogError("Clearing power log")
            return self.ClearPowerLog()

        try:

            LogSize = os.path.getsize(self.PowerLog)
            if float(LogSize) / (1024 * 1024) < self.PowerLogMaxSize * 0.85:
                return "OK"

            if float(LogSize) / (1024 * 1024) >= self.PowerLogMaxSize * 0.98:
                msgbody = "The genmon kwlog (power log) file size is 98 percent of the maximum. Once "
                msgbody += "the log reaches 100 percent of the log will be reset. This will result "
                msgbody += "inaccurate fuel estimation (if you are using this feature). You can  "
                msgbody += "either increase the size of the kwlog on the advanced settings page,"
                msgbody += "or reset your power log."
                self.MessagePipe.SendMessage(
                    "Notice: Power Log file size warning",
                    msgbody,
                    msgtype="warn",
                    onlyonce=True,
                )

            # is the file size too big?
            if float(LogSize) / (1024 * 1024) >= self.PowerLogMaxSize:
                self.ClearPowerLog()
                self.LogError("Power Log entries deleted due to size reaching maximum.")
                return "OK"

            # if we get here the power log is 85% full or greater so let's try to reduce the size by
            # deleting entires that are older than the input Minutes
            CmdString = "power_log_json=%d" % Minutes
            PowerLog = self.GetPowerHistory(CmdString, NoReduce=True)

            self.ClearPowerLog(NoCreate=True)
            # Write oldest log entries first
            for Items in reversed(PowerLog):
                self.LogToPowerLog(Items[0], Items[1])

            # Add null entry at the end
            if not os.path.isfile(self.PowerLog):
                TimeStamp = datetime.datetime.now().strftime("%x %X")
                self.LogToPowerLog(TimeStamp, "0.0")

            # if the power log is now empty add one entry
            LogSize = os.path.getsize(self.PowerLog)
            if LogSize == 0:
                TimeStamp = datetime.datetime.now().strftime("%x %X")
                self.LogToPowerLog(TimeStamp, "0.0")

            return "OK"

        except Exception as e1:
            self.LogErrorLine("Error in  PrunePowerLog: " + str(e1))
            return "Error in  PrunePowerLog: " + str(e1)

    def ClearPowerLog(self, NoCreate: bool = False) -> str:
        """
        Deletes the power log file content.

        Args:
            NoCreate (bool): If True, don't create a new initial entry.

        Returns:
            str: Status message.
        """
        try:
            if not len(self.PowerLog):
                return "Power Log Disabled"

            if not os.path.isfile(self.PowerLog):
                return "Power Log is empty"
            try:
                with self.PowerLock:
                    os.remove(self.PowerLog)
                    time.sleep(1)
            except:
                pass

            self.PowerLogList = []

            if not NoCreate:
                # add zero entry to note the start of the log
                TimeStamp = datetime.datetime.now().strftime("%x %X")
                self.LogToPowerLog(TimeStamp, "0.0")

            return "Power Log cleared"
        except Exception as e1:
            self.LogErrorLine("Error in  ClearPowerLog: " + str(e1))
            return "Error in  ClearPowerLog: " + str(e1)

    def ReducePowerSamples(self, PowerList: List[List[str]], MaxSize: int) -> List[List[str]]:
        """
        Reduces the number of power log samples to fit MaxSize.

        Args:
            PowerList (List[List[str]]): List of [Timestamp, Value].
            MaxSize (int): Maximum allowed size.

        Returns:
            List[List[str]]: Reduced list.
        """
        if MaxSize == 0:
            self.LogError("RecducePowerSamples: Error: Max size is zero")
            return []

        if len(PowerList) < MaxSize:
            self.LogError("RecducePowerSamples: Error: Can't reduce ")
            return PowerList

        try:
            # if we have too many entries, then delete some
            if len(PowerList) > MaxSize:
                return self.RemovePowerSamples(PowerList, MaxSize)
        except Exception as e1:
            self.LogErrorLine("Error in RecducePowerSamples: %s" % str(e1))
            return PowerList

        return PowerList

    def AverageTwoSamples(self, a: List[str], b: List[str]) -> List[str]:
        """
        Averages two power samples.

        Args:
            a (List[str]): Sample 1 [Timestamp, Value].
            b (List[str]): Sample 2 [Timestamp, Value].

        Returns:
            List[str]: Averaged sample [Timestamp, AvgValue].
        """
        try:
            if float(a[1]) == 0:
                return a
            if float(b[1]) == 0:
                return b
             
            average = (float(a[1]) + float(b[1])) / 2.0
            average = round(average, 2)
            return [a[0], str(average)]
        except Exception as e1:
            self.LogErrorLine("Error in AverageTwoSamples: %s" % str(e1))
            return a

    def ReduceList(self, inputlist: List[List[str]]) -> List[List[str]]:
        """
        Reduces list size by averaging adjacent non-zero samples.

        Args:
            inputlist (List[List[str]]): Input list.

        Returns:
            List[List[str]]: Reduced list.
        """
        try:

            if len(inputlist) < 2:
                return inputlist
            if len(inputlist) % 2 == 0:
                # even
                Lenght = len(inputlist)
                isEven = True
            else:
                Lenght = len(inputlist) - 1
                isEven = False
            OutList = []

            for k in range(0,Lenght,2):
                try:
                    # check to see if there are zero entries for the power
                    if float(inputlist[k][1]) == 0 or float(inputlist[k+1][1]) == 0:
                        OutList.append(inputlist[k])
                        OutList.append(inputlist[k+1])
                    else:
                        OutList.append(self.AverageTwoSamples(inputlist[k],inputlist[k+1]))
                except Exception as e1:
                    self.LogErrorLine("Error in ReduceList (2): " + str(e1) +", " + str(k) + ", " + str(Lenght))
                    self.LogErrorLine("isEven = " + str(isEven))
            if not isEven:
                OutList.append(inputlist[-1])
            return OutList
        except Exception as e1:
            self.LogErrorLine("Error in ReduceList: %s" % str(e1))
            return inputlist

    def RemovePowerSamples(self, inputList: List[List[str]], MaxSize: int) -> List[List[str]]:
        """
        Truncates the power sample list to MaxSize.

        Args:
            inputList (List[List[str]]): Input list.
            MaxSize (int): Limit.

        Returns:
            List[List[str]]: Truncated list.
        """
        try:

            if len(inputList) <= MaxSize:
                self.LogError("RemovePowerSamples: Error: Can't remove ")
                return inputList
            
            # Simple truncation (keeping newest assuming appended to front or back?)
            # Usually logs are read such that index 0 is newest or oldest depending on parsing.
            # ReadPowerLogFromFile inserts at 0, so index 0 is newest.
            # Truncating [:MaxSize] keeps newest.
            if len(inputList) > MaxSize:
                NewList = inputList[:MaxSize]

            return NewList
        except Exception as e1:
            self.LogErrorLine("Error in RemovePowerSamples: %s" % str(e1))
            return NewList

    def GetPowerLogForMinutes(self, Minutes: int = 0, InputList: Optional[List] = None) -> List[List[str]]:
        """
        Filters power log for entries within the last N minutes.

        Args:
            Minutes (int): Duration in minutes.
            InputList (Optional[List]): Override input list.

        Returns:
            List[List[str]]: Filtered list.
        """
        try:
            ReturnList = []
            if InputList is None:
                PowerList = self.ReadPowerLogFromFile()
            else:
                PowerList = InputList
            if not Minutes:
                return PowerList
            CurrentTime = datetime.datetime.now()

            for Time, Power in reversed(PowerList):
                try:
                    struct_time = time.strptime(Time, "%x %X")
                    LogEntryTime = datetime.datetime.fromtimestamp(time.mktime(struct_time))
                except Exception as e1:
                    self.LogErrorLine("Error in GetPowerLogForMinutes: " + str(e1))
                    continue
                Delta = CurrentTime - LogEntryTime
                if self.GetDeltaTimeMinutes(Delta) < Minutes:
                    ReturnList.insert(0, [Time, Power])
            return ReturnList
        except Exception as e1:
            self.LogErrorLine("Error in GetPowerLogForMinutes: " + str(e1))
            return ReturnList

    def ReadPowerLogFromFile(self, Minutes: int = 0, NoReduce: bool = False) -> List[List[str]]:
        """
        Reads the power log from disk.

        Args:
            Minutes (int): Filter by minutes.
            NoReduce (bool): Skip reduction.

        Returns:
            List[List[str]]: Power log data.
        """
        # check to see if a log file exist yet
        if not os.path.isfile(self.PowerLog):
            return []
        PowerList = []

        with self.PowerLock:
            # return cached list if we have read the file before
            if len(self.PowerLogList) and not Minutes:
                return self.PowerLogList
            if Minutes:
                return self.GetPowerLogForMinutes(Minutes)

            try:
                with open(self.PowerLog, "r") as LogFile:  # opens file
                    for line in LogFile:
                        line = line.strip()  # remove whitespace at beginning and end

                        if not len(line):
                            continue
                        if line[0] == "#":  # comment
                            continue
                        line = self.removeNonPrintable(line)
                        Items = line.split(",")
                        if len(Items) != 2:
                            continue
                        # remove any kW labels that may be there
                        Items[1] = self.removeAlpha(Items[1])
                        PowerList.insert(0, [Items[0], Items[1]])

            except Exception as e1:
                self.LogErrorLine(
                    "Error in  ReadPowerLogFromFile (parse file): " + str(e1)
                )

            if len(PowerList) > self.MaxPowerLogEntries and not NoReduce:
                PowerList = self.ReducePowerSamples(PowerList, self.MaxPowerLogEntries)
            if not len(self.PowerLogList):
                self.PowerLogList = PowerList
        return PowerList

    def GetPowerHistory(
        self, CmdString: str, NoReduce: bool = False, FromUI: bool = False
    ) -> Union[str, List[List[str]]]:
        """
        Retrieves power history based on command string.

        Args:
            CmdString (str): "power_log_json=[minutes],[type]"
            NoReduce (bool): Skip reduction.
            FromUI (bool): Request originated from UI.

        Returns:
            Union[str, List[List[str]]]: Result (JSON list or calculated value).
        """
        KWHours = False
        FuelConsumption = False
        RunHours = False
        msgbody = "Invalid command syntax for command power_log_json"

        try:
            if not len(self.PowerLog):
                # power log disabled
                return []

            if not len(CmdString):
                self.LogError("Error in GetPowerHistory: Invalid input")
                return []

            # Format we are looking for is "power_log_json=5" or "power_log_json" or "power_log_json=1000,kw"
            CmdList = CmdString.split("=")

            if len(CmdList) > 2:
                self.LogError(
                    "Validation Error: Error parsing command string in GetPowerHistory (parse): "
                    + CmdString
                )
                return msgbody

            CmdList[0] = CmdList[0].strip()

            if not CmdList[0].lower() == "power_log_json":
                self.LogError(
                    "Validation Error: Error parsing command string in GetPowerHistory (parse2): "
                    + CmdString
                )
                return msgbody

            if len(CmdList) == 2:
                ParseList = CmdList[1].split(",")
                if len(ParseList) == 1:
                    Minutes = int(CmdList[1].strip())
                elif len(ParseList) == 2:
                    Minutes = int(ParseList[0].strip())
                    if ParseList[1].strip().lower() == "kw":
                        KWHours = True
                    elif ParseList[1].strip().lower() == "fuel":
                        FuelConsumption = True
                    elif ParseList[1].strip().lower() == "time":
                        RunHours = True
                else:
                    self.LogError(
                        "Validation Error: Error parsing command string in GetPowerHistory (parse3): "
                        + CmdString
                    )
                    return msgbody

            else:
                Minutes = 0
        except Exception as e1:
            self.LogErrorLine(
                "Error in  GetPowerHistory (Parse): %s : %s" % (CmdString, str(e1))
            )
            return msgbody

        try:
            if FromUI and Minutes == 0 and KWHours == False and FuelConsumption == False and RunHours == False:
                # if raw log is requested and minutes are zero and from the UI then reduce to 31 days
                self.LogDebug("Reducing from UI: " + CmdString)
                Minutes = (60 *24 * 31) # Minutes in month

            PowerList = self.ReadPowerLogFromFile(Minutes=Minutes)

            # Shorten list to self.MaxPowerLogEntries if specific duration requested
            # if not KWHours and len(PowerList) > self.MaxPowerLogEntries and Minutes and not NoReduce:
            if len(PowerList) > self.MaxPowerLogEntries and Minutes and not NoReduce:
                PowerList = self.ReducePowerSamples(PowerList, self.MaxPowerLogEntries)
            if KWHours:
                AvgPower, TotalSeconds = self.GetAveragePower(PowerList)
                return "%.2f" % ((TotalSeconds / 3600) * AvgPower)
            if FuelConsumption:
                AvgPower, TotalSeconds = self.GetAveragePower(PowerList)
                Consumption, Label = self.GetFuelConsumption(AvgPower, TotalSeconds)
                if Consumption is None:
                    return "Unknown"
                if Consumption < 0:
                    self.LogDebug("WARNING: Fuel Consumption is less than zero in GetPowerHistory: %d" % Consumption)
                return "%.2f %s" % (Consumption, Label)
            if RunHours:
                AvgPower, TotalSeconds = self.GetAveragePower(PowerList)
                return "%.2f" % (TotalSeconds / 60.0 / 60.0)

            return PowerList

        except Exception as e1:
            self.LogErrorLine("Error in  GetPowerHistory: " + str(e1))
            msgbody = "Error in  GetPowerHistory: " + str(e1)
            return msgbody

    # ----------  GeneratorController::GetAveragePower---------------------------
    # a list of the power log is passed in (already parsed for a time period)
    # returns a time period and average power used for that time period
    def GetAveragePower(self, PowerList: List[List[str]]) -> Tuple[float, float]:

        try:
            TotalTime = datetime.timedelta(seconds=0)
            Entries = 0
            TotalPower = 0.0
            LastPower = 0.0
            LastTime = None
            for Items in PowerList:
                try:
                    # is the power value a float?
                    Power = float(Items[1])
                except Exception as e1:
                    Power = 0.0
                    continue
                try:
                    # This should be date time
                    struct_time = time.strptime(Items[0], "%x %X")
                    LogEntryTime = datetime.datetime.fromtimestamp(
                        time.mktime(struct_time)
                    )
                except Exception as e1:
                    self.LogErrorLine("Invalid time entry in power log: " + str(e1))
                    continue

                # Changes in Daylight savings time will effect this
                if LastTime is None or Power == 0:
                    TotalTime += LogEntryTime - LogEntryTime
                else:
                    TotalTime += LastTime - LogEntryTime
                    TotalPower += (Power + LastPower) / 2
                    Entries += 1
                LastTime = LogEntryTime
                LastPower = Power

            if Entries == 0:
                return 0.0, 0.0
            TotalPower = TotalPower / Entries
            return TotalPower, TotalTime.total_seconds()
        except Exception as e1:
            self.LogErrorLine("Error in  GetAveragePower: " + str(e1))
            return 0.0, 0.0
