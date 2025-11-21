#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: myconfig.py
# PURPOSE: Configuration file Abstraction
#
#  AUTHOR: Jason G Yates
#    DATE: 22-May-2018
#
# MODIFICATIONS:
#
# -------------------------------------------------------------------------------

"""
Module for configuration file abstraction.

This module provides the `MyConfig` class to read and write configuration
values using standard INI file formats. It wraps `configparser`.
"""

import sys
import threading
from typing import Optional, Any, List, Tuple, Union, Type

# Fix Python 2.x. unicode type
if sys.version_info[0] >= 3:  # PYTHON 3
    from configparser import ConfigParser
    unicode = str
else:
    from ConfigParser import ConfigParser

from genmonlib.mycommon import MyCommon


class MyConfig(MyCommon):
    """
    A wrapper class for configuration file handling.

    Provides thread-safe reading and writing of configuration values.

    Attributes:
        FileName (str): Path to the configuration file.
        Section (str): The default section to read/write.
        Simulation (bool): If True, prevents writing to files.
        CriticalLock (threading.Lock): Lock for file write operations.
        InitComplete (bool): Flag indicating if initialization was successful.
        config (ConfigParser): The underlying config parser object.
    """

    def __init__(
        self,
        filename: Optional[str] = None,
        section: Optional[str] = None,
        simulation: bool = False,
        log: Any = None
    ):
        """
        Initializes the MyConfig object.

        Args:
            filename (str, optional): Path to the config file.
            section (str, optional): Default section name.
            simulation (bool, optional): Simulation mode flag.
            log (Any, optional): Logger instance.
        """
        super(MyConfig, self).__init__()
        self.log = log
        self.FileName = filename
        self.Section = section
        self.Simulation = simulation
        self.CriticalLock = threading.Lock()  # Critical Lock (writing conf file)
        self.InitComplete = False
        try:
            if sys.version_info[0] < 3:
                self.config = ConfigParser()
            else:
                self.config = ConfigParser(interpolation=None)

            if self.FileName:
                self.config.read(self.FileName)

            if self.Section is None:
                SectionList = self.GetSections()
                if len(SectionList):
                    self.Section = SectionList[0]

        except Exception as e1:
            self.LogErrorLine("Error in MyConfig:init: " + str(e1))
            return
        self.InitComplete = True

    def HasOption(self, Entry: str) -> bool:
        """
        Checks if an option exists in the current section.

        Args:
            Entry (str): The option name.

        Returns:
            bool: True if the option exists, False otherwise.
        """
        return self.config.has_option(self.Section, Entry)

    def GetList(self) -> Optional[List[Tuple[str, str]]]:
        """
        Returns a list of items in the current section.

        Returns:
            Optional[List[Tuple[str, str]]]: List of (name, value) pairs or None on error.
        """
        try:
            return self.config.items(self.Section)

        except Exception as e1:
            self.LogErrorLine(
                "Error in MyConfig:GetList: " + str(self.Section) + ": " + str(e1)
            )
            return None

    def GetSections(self) -> List[str]:
        """
        Returns a list of sections in the configuration file.

        Returns:
            List[str]: List of section names.
        """
        return self.config.sections()

    def SetSection(self, section: str) -> bool:
        """
        Sets the current working section.

        Args:
            section (str): The section name to switch to.

        Returns:
            bool: True if successful, False on error.
        """
        if self.Simulation:
            return True
        if not (isinstance(section, str) or isinstance(section, unicode)) or not len(
            section
        ):
            self.LogError(
                "Error in MyConfig:ReadValue: invalid section: " + str(section)
            )
            return False
        self.Section = section
        return True

    def ReadValue(
        self,
        Entry: str,
        return_type: Type = str,
        default: Any = None,
        section: Optional[str] = None,
        NoLog: bool = False
    ) -> Any:
        """
        Reads a value from the configuration.

        Args:
            Entry (str): The option name.
            return_type (Type, optional): Expected type (str, bool, float, int). Defaults to str.
            default (Any, optional): Default value if option is missing or error occurs.
            section (str, optional): Section to read from (overrides current).
            NoLog (bool, optional): If True, suppresses error logging.

        Returns:
            Any: The read value cast to the requested type, or the default value.
        """
        try:
            if section is not None:
                self.SetSection(section)

            if self.config.has_option(self.Section, Entry):
                if return_type == str:
                    return self.config.get(self.Section, Entry)
                elif return_type == bool:
                    return self.config.getboolean(self.Section, Entry)
                elif return_type == float:
                    return self.config.getfloat(self.Section, Entry)
                elif return_type == int:
                    return self.config.getint(self.Section, Entry)
                else:
                    self.LogErrorLine(
                        "Warning in MyConfig:ReadValue: invalid type or missing value, using default :"
                        + str(return_type)
                    )
                    return default
            else:
                return default
        except Exception as e1:
            if not NoLog:
                self.LogErrorLine(
                    "Error in MyConfig:ReadValue: "
                    + str(self.Section)
                    + ": "
                    + Entry
                    + ": "
                    + str(e1)
                )
            return default

    def alt_WriteSection(self, SectionName: str) -> bool:
        """
        Writes a new section to the configuration file (Alternate method).

        NOTE: This method uses ConfigParser.write which will re-format the file
        and remove comments.

        Args:
            SectionName (str): The name of the section to add.

        Returns:
            bool: True on success, False on error.
        """
        if self.Simulation:
            return True

        if not self.InitComplete:
            return False
        SectionList = self.GetSections()

        if SectionName in SectionList:
            self.LogError("Error in WriteSection: Section already exist.")
            return True
        try:
            with self.CriticalLock:
                # open in unbuffered mode
                with open(self.FileName, "w") as ConfigFile:
                    if sys.version_info.major < 3:
                        self.config.add_section(SectionName)
                    else:
                        self.config[SectionName] = {}
                    self.config.write(ConfigFile)
            return True
        except Exception as e1:
            self.LogErrorLine("Error in WriteSection: " + str(e1))
            return False

    def WriteSection(self, SectionName: str) -> bool:
        """
        Appends a new section to the configuration file.

        Args:
            SectionName (str): The name of the section to add.

        Returns:
            bool: True on success, False on error.
        """
        if self.Simulation:
            return True

        if not self.InitComplete:
            return False
        SectionList = self.GetSections()

        if SectionName in SectionList:
            self.LogError("Error in WriteSection: Section already exist.")
            return True
        try:
            with self.CriticalLock:
                # open in unbuffered mode
                with open(self.FileName, "a") as ConfigFile:
                    ConfigFile.write("[" + SectionName + "]")
                    ConfigFile.flush()
                    ConfigFile.close()
                    # update the read data that is cached
                    self.config.read(self.FileName)
            return True
        except Exception as e1:
            self.LogErrorLine("Error in WriteSection: " + str(e1))
            return False

    def alt_WriteValue(
        self,
        Entry: str,
        Value: str,
        remove: bool = False,
        section: Optional[str] = None
    ) -> bool:
        """
        Writes a value to the configuration file (Alternate method).

        NOTE: This method uses ConfigParser.write which will re-format the file
        and remove comments.

        Args:
            Entry (str): The option name.
            Value (str): The value to write.
            remove (bool, optional): Unused in this implementation.
            section (str, optional): Section to write to.

        Returns:
            bool: True on success, False on error.
        """
        if self.Simulation:
            return False

        if not self.InitComplete:
            return False
        if section is not None:
            self.SetSection(section)

        try:
            with self.CriticalLock:
                if sys.version_info.major < 3:
                    self.config.set(self.Section, Entry, Value)
                else:
                    section_data = self.config[self.Section]
                    section_data[Entry] = Value

                # Write changes back to file
                with open(self.FileName, "w") as ConfigFile:
                    self.config.write(ConfigFile)
                return True

        except Exception as e1:
            self.LogErrorLine("Error in WriteValue: " + str(e1))
            return False

    def WriteValue(
        self,
        Entry: str,
        Value: str,
        remove: bool = False,
        section: Optional[str] = None
    ) -> bool:
        """
        Writes a value to the configuration file, preserving comments.

        Parses the file line by line to find the section and entry, then updates
        it or appends it.

        Args:
            Entry (str): The option name.
            Value (str): The value to write.
            remove (bool, optional): If True, does not write the entry (effectively removing it
                if it's not written back, though current logic just skips adding it new).
                Use with caution as the logic implies updating existing lines or adding new ones.
            section (str, optional): Section to write to.

        Returns:
            bool: True on success, False on error.
        """
        if self.Simulation:
            return False

        if not self.InitComplete:
            return False

        if section is not None:
            self.SetSection(section)

        SectionFound = False
        try:
            with self.CriticalLock:
                Found = False
                with open(self.FileName, "r") as ConfigFile:
                    FileString = ConfigFile.read()

                # open in unbuffered mode
                with open(self.FileName, "w") as ConfigFile:
                    for line in FileString.splitlines():
                        if not line.isspace():  # blank lines
                            newLine = line.strip()  # strip leading spaces
                            if len(newLine):
                                if not newLine[0] == "#":  # not a comment
                                    if not SectionFound and not self.LineIsSection(newLine):
                                        ConfigFile.write(line + "\n")
                                        continue

                                    if (
                                        self.LineIsSection(newLine)
                                        and self.Section.lower()
                                        != self.GetSectionName(newLine).lower()
                                    ):
                                        if (
                                            SectionFound and not Found and not remove
                                        ):  # we reached the end of the section
                                            ConfigFile.write(Entry + " = " + Value + "\n")
                                            Found = True
                                        SectionFound = False
                                        ConfigFile.write(line + "\n")
                                        continue
                                    if (
                                        self.LineIsSection(newLine)
                                        and self.Section.lower()
                                        == self.GetSectionName(newLine).lower()
                                    ):
                                        SectionFound = True
                                        ConfigFile.write(line + "\n")
                                        continue

                                    if not SectionFound:
                                        ConfigFile.write(line + "\n")
                                        continue
                                    items = newLine.split(
                                        "="
                                    )  # split items in line by spaces
                                    if len(items) >= 2:
                                        items[0] = items[0].strip()
                                        if items[0] == Entry:
                                            if not remove:
                                                ConfigFile.write(
                                                    Entry + " = " + Value + "\n"
                                                )
                                            Found = True
                                            continue

                        ConfigFile.write(line + "\n")
                    # if this is a new entry, then write it to the file, unless we are removing it
                    # this check is if there is not section below the one we are working in,
                    # it will be added to the end of the file
                    if not Found and not remove:
                        ConfigFile.write(Entry + " = " + Value + "\n")
                    ConfigFile.flush()

                # update the read data that is cached
                self.config.read(self.FileName)
            return True

        except Exception as e1:
            self.LogErrorLine("Error in WriteValue: " + str(e1))
            return False

    def GetSectionName(self, Line: str) -> str:
        """
        Extracts the section name from a line (e.g., "[Section]").

        Args:
            Line (str): The line to parse.

        Returns:
            str: The section name without brackets, or empty string if invalid.
        """
        if self.Simulation:
            return ""
        Line = Line.strip()
        if Line.startswith("[") and Line.endswith("]") and len(Line) >= 3:
            Line = Line.replace("[", "")
            Line = Line.replace("]", "")
            return Line
        return ""

    def LineIsSection(self, Line: str) -> bool:
        """
        Checks if a line represents a section header.

        Args:
            Line (str): The line to check.

        Returns:
            bool: True if it's a section header, False otherwise.
        """
        if self.Simulation:
            return False
        Line = Line.strip()
        if Line.startswith("[") and Line.endswith("]") and len(Line) >= 3:
            return True
        return False
