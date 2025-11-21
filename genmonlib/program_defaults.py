#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: program_defaults.py
# PURPOSE: default values
#
#  AUTHOR: Jason G Yates
#    DATE: 10-May-2019
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

"""
Module for storing default program configuration values.

This module defines the `ProgramDefaults` class which holds static constants
used throughout the application for configuration paths, logging paths,
network settings, and version information.
"""


class ProgramDefaults(object):
    """
    A container for application-wide default constants.

    Attributes:
        ConfPath (str): The default directory path for configuration files.
        LogPath (str): The default directory path for log files.
        ServerPort (int): The default TCP port for the server.
        LocalHost (str): The default localhost IP address.
        GENMON_VERSION (str): The current version of the GenMon software.
    """
    ConfPath: str = "/etc/genmon/"
    LogPath: str = "/var/log/"
    ServerPort: int = 9082
    LocalHost: str = "127.0.0.1"
    GENMON_VERSION: str = "V1.19.07"
