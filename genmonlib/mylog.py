# -------------------------------------------------------------------------------
# PURPOSE: setup logging
#
#  AUTHOR: Jason G Yates
#    DATE: 03-Dec-2016
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

"""
Module for setting up and configuring logging.

This module provides a helper function to create and configure a logger with
rotating file handlers and optional console output.
"""

import logging
import logging.handlers
from typing import Optional


def SetupLogger(
    logger_name: str,
    log_file: str,
    level: int = logging.INFO,
    stream: bool = False
) -> logging.Logger:
    """
    Configures and returns a logger instance.

    Creates a logger with the specified name and level. It sets up a rotating
    file handler if a log file path is provided. It can optionally add a
    stream handler to output logs to the console. Existing handlers on the
    logger are removed to prevent duplicate logging.

    Args:
        logger_name (str): The name of the logger to retrieve.
        log_file (str): The path to the log file. If empty string, file logging
            is skipped.
        level (int, optional): The logging level (e.g., logging.INFO).
            Defaults to logging.INFO.
        stream (bool, optional): If True, adds a StreamHandler to output logs
            to the console (stdout/stderr). Defaults to False.

    Returns:
        logging.Logger: The configured logger instance.
    """
    logger = logging.getLogger(logger_name)

    # remove existing log handlers
    for handler in logger.handlers[:]:  # make a copy of the list
        logger.removeHandler(handler)

    logger.setLevel(level)

    if log_file != "":
        formatter = logging.Formatter("%(asctime)s : %(message)s")
        rotate = logging.handlers.RotatingFileHandler(
            log_file, mode="a", maxBytes=50000, backupCount=5
        )
        rotate.setFormatter(formatter)
        logger.addHandler(rotate)

    if stream:  # print to screen also?
        # Dont format stream log messages, just print the message
        log_format = "%(message)s"
        stream_handler = logging.StreamHandler()
        formatter = logging.Formatter(log_format)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return logging.getLogger(logger_name)
