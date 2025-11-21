# -------------------------------------------------------------------------------
# PURPOSE: manage threads
#
#  AUTHOR: Jason G Yates
#    DATE: 04-Mar-2017
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

"""
Module for managing threads with stop capabilities.

This module defines the `MyThread` class, which wraps the standard `threading.Thread`
to provide a convenient way to signal the thread to stop and to check for stop signals.
"""

import threading
from typing import Optional, Callable, Any


class MyThread:
    """
    Thread class with a stop() method.

    The thread itself has to check regularly for the stopped() condition using
    `StopSignaled()` or `Wait()`.

    Attributes:
        StopEvent (threading.Event): Event used to signal the thread to stop.
        ThreadObj (threading.Thread): The underlying thread object.
    """

    def __init__(
        self,
        ThreadFunction: Callable[..., Any],
        Name: Optional[str] = None,
        start: bool = True
    ):
        """
        Initializes the MyThread instance.

        Args:
            ThreadFunction (Callable): The function to run in the thread.
            Name (str, optional): The name of the thread. Defaults to None.
            start (bool, optional): Whether to start the thread immediately.
                Defaults to True.
        """
        self.StopEvent = threading.Event()
        self.ThreadObj = threading.Thread(target=ThreadFunction, name=Name)
        self.ThreadObj.daemon = True
        if start:
            self.Start()

    def GetThreadObject(self) -> threading.Thread:
        """
        Returns the underlying threading.Thread object.

        Returns:
            threading.Thread: The thread object.
        """
        return self.ThreadObj

    def Start(self, timeout: Optional[float] = None) -> None:
        """
        Starts the thread.

        Args:
            timeout (float, optional): Unused, kept for compatibility or future use.
        """
        # timeout is not used in standard Thread.start()
        self.ThreadObj.start()  # start thread

    def Wait(self, timeout: Optional[float] = None) -> bool:
        """
        Waits for the stop signal for a specified amount of time.

        This acts like a sleep that can be interrupted if `Stop()` is called.

        Args:
            timeout (float, optional): The maximum time to wait in seconds.

        Returns:
            bool: True if the stop event was set, False if the timeout occurred.
        """
        return self.StopEvent.wait(timeout)

    def Stop(self) -> None:
        """
        Signals the thread to stop.
        """
        self.StopEvent.set()

    def StopSignaled(self) -> bool:
        """
        Checks if the thread has been signaled to stop.

        Returns:
            bool: True if the stop signal is set, False otherwise.
        """
        return self.StopEvent.is_set()

    def IsAlive(self) -> bool:
        """
        Checks if the thread is currently alive.

        Returns:
            bool: True if the thread is alive, False otherwise.
        """
        return self.ThreadObj.is_alive()

    def Name(self) -> str:
        """
        Returns the name of the thread.

        Returns:
            str: The thread name.
        """
        return self.ThreadObj.name

    def WaitForThreadToEnd(self, Timeout: Optional[float] = None) -> None:
        """
        Waits for the thread to terminate.

        Args:
            Timeout (float, optional): The maximum time to wait for the thread to join.
        """
        return self.ThreadObj.join(Timeout)
