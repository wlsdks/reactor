"""Reactor Python agent service."""

from __future__ import annotations

import os
from importlib.metadata import version

os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")

__all__ = ["__version__"]

__version__ = version("reactor")
