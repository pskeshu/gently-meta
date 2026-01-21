"""
gently-meta: Multi-Microscope Coordination Infrastructure

Provides coordination infrastructure for autonomous microscopy systems,
enabling multiple gently instances to work together on shared scientific goals.
"""

__version__ = "0.1.0"

from .queue import ExperimentQueue, ExperimentRequest, RequestStatus, Priority
from .microscope_registry import MicroscopeRegistry, MicroscopeCapability, MicroscopeStatus

__all__ = [
    "ExperimentQueue",
    "ExperimentRequest",
    "RequestStatus",
    "Priority",
    "MicroscopeRegistry",
    "MicroscopeCapability",
    "MicroscopeStatus",
]
