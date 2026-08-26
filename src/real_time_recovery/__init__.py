"""Utilities for bringing up the real-time recovery hardware."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("real-time-robot-recovery")
except PackageNotFoundError:  # Source tree used without an installed package.
    __version__ = "0.0.0"

__all__ = ["__version__"]
