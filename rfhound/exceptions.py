"""Exception hierarchy for RFHound."""

from __future__ import annotations


class RFHoundError(Exception):
    """Base class for all RFHound errors."""


class DependencyMissingError(RFHoundError):
    """A required external tool (hackrf_sweep, rtl_433, ...) is not installed."""

    def __init__(self, tool: str, hint: str | None = None) -> None:
        self.tool = tool
        self.hint = hint
        message = f"Required external tool '{tool}' was not found on PATH."
        if hint:
            message += f"\n  Install hint: {hint}"
        super().__init__(message)


class DeviceError(RFHoundError):
    """No HackRF was found, or the device could not be queried."""


class SafetyError(RFHoundError):
    """A transmit / active action was blocked by the safety subsystem."""


class ConfigError(RFHoundError):
    """The configuration file is invalid or could not be written."""


class ProcessError(RFHoundError):
    """An external process exited with a non-zero status."""

    def __init__(self, command: str, returncode: int, stderr: str = "") -> None:
        self.command = command
        self.returncode = returncode
        self.stderr = stderr
        message = f"Command failed ({returncode}): {command}"
        if stderr.strip():
            message += f"\n{stderr.strip()}"
        super().__init__(message)
