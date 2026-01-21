"""
Microscope Registry

Manages registration and discovery of microscope capabilities.
Enables routing experiments to appropriate instruments based on requirements.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class MicroscopeStatus(Enum):
    """Operational status of a microscope."""
    ONLINE = "online"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"
    BUSY = "busy"
    RESERVED = "reserved"


class MicroscopeType(Enum):
    """Types of microscopes."""
    WIDEFIELD = "widefield"
    CONFOCAL = "confocal"
    TWO_PHOTON = "two_photon"
    LIGHT_SHEET = "light_sheet"
    SUPER_RESOLUTION = "super_resolution"
    SPINNING_DISK = "spinning_disk"
    DISPIM = "DiSPIM"


@dataclass
class Objective:
    """Objective lens specification."""
    magnification: int
    numerical_aperture: float
    immersion: str = "air"
    working_distance_mm: Optional[float] = None


@dataclass
class LightSource:
    """Light source specification."""
    type: str
    wavelengths: list[int]
    max_power_mw: Optional[float] = None


@dataclass
class Detector:
    """Camera/detector specification."""
    type: str
    pixel_size_um: Optional[float] = None
    resolution_x: Optional[int] = None
    resolution_y: Optional[int] = None
    quantum_efficiency: Optional[float] = None


@dataclass
class FilterSet:
    """Filter set specification."""
    name: str
    excitation: int
    emission: int
    fluorophores: list[str] = field(default_factory=list)


@dataclass
class EnvironmentalChamber:
    """Environmental control chamber."""
    available: bool = False
    temperature_control: bool = False
    co2_control: bool = False
    humidity_control: bool = False


@dataclass
class Hardware:
    """Microscope hardware specification."""
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    objectives: list[Objective] = field(default_factory=list)
    light_sources: list[LightSource] = field(default_factory=list)
    detectors: list[Detector] = field(default_factory=list)
    filter_sets: list[FilterSet] = field(default_factory=list)
    environmental_chamber: EnvironmentalChamber = field(default_factory=EnvironmentalChamber)


@dataclass
class SchedulingConfig:
    """Scheduling configuration."""
    weekday_start: str = "08:00"
    weekday_end: str = "18:00"
    weekend_start: Optional[str] = None
    weekend_end: Optional[str] = None
    max_booking_duration_hours: float = 8
    min_booking_duration_hours: float = 0.5
    advance_booking_days: int = 14


@dataclass
class Contact:
    """Contact information."""
    name: str
    email: str
    phone: Optional[str] = None


@dataclass
class Metrics:
    """Operational metrics."""
    uptime_percentage: Optional[float] = None
    experiments_completed: int = 0
    average_queue_time_hours: Optional[float] = None
    last_maintenance: Optional[str] = None
    next_maintenance: Optional[str] = None


@dataclass
class Location:
    """Physical location."""
    institution: str
    building: Optional[str] = None
    room: Optional[str] = None
    timezone: str = "UTC"


@dataclass
class MicroscopeCapability:
    """
    Advertisement of microscope capabilities for routing and scheduling.
    """
    microscope_id: str
    type: MicroscopeType
    status: MicroscopeStatus = MicroscopeStatus.OFFLINE

    name: Optional[str] = None
    location: Optional[Location] = None
    capabilities: list[str] = field(default_factory=list)
    hardware: Hardware = field(default_factory=Hardware)
    scheduling: SchedulingConfig = field(default_factory=SchedulingConfig)
    primary_contact: Optional[Contact] = None
    reviewers: list[Contact] = field(default_factory=list)
    metrics: Metrics = field(default_factory=Metrics)

    last_heartbeat: Optional[str] = None
    registered_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def update_heartbeat(self):
        """Update the last heartbeat timestamp."""
        self.last_heartbeat = datetime.utcnow().isoformat()

    def supports_capability(self, capability: str) -> bool:
        """Check if microscope supports a specific capability."""
        return capability in self.capabilities

    def supports_all(self, required_capabilities: list[str]) -> bool:
        """Check if microscope supports all required capabilities."""
        return all(cap in self.capabilities for cap in required_capabilities)

    def supports_any(self, capabilities: list[str]) -> bool:
        """Check if microscope supports any of the given capabilities."""
        return any(cap in self.capabilities for cap in capabilities)

    def has_wavelength(self, wavelength: int, tolerance: int = 10) -> bool:
        """Check if microscope has a light source near the given wavelength."""
        for source in self.hardware.light_sources:
            for wl in source.wavelengths:
                if abs(wl - wavelength) <= tolerance:
                    return True
        return False

    def has_objective(self, magnification: int) -> bool:
        """Check if microscope has an objective with the given magnification."""
        return any(obj.magnification == magnification for obj in self.hardware.objectives)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        def convert(obj):
            if isinstance(obj, Enum):
                return obj.value
            if hasattr(obj, '__dataclass_fields__'):
                return {k: convert(v) for k, v in asdict(obj).items() if v is not None}
            if isinstance(obj, list):
                return [convert(item) for item in obj]
            if isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items() if v is not None}
            return obj

        return convert(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MicroscopeCapability":
        """Create MicroscopeCapability from dictionary."""
        # Parse nested structures
        location = Location(**data["location"]) if data.get("location") else None

        hardware = Hardware()
        if data.get("hardware"):
            hw = data["hardware"]
            if hw.get("objectives"):
                hardware.objectives = [Objective(**obj) for obj in hw["objectives"]]
            if hw.get("light_sources"):
                hardware.light_sources = [LightSource(**ls) for ls in hw["light_sources"]]
            if hw.get("detectors"):
                hardware.detectors = [Detector(**det) for det in hw["detectors"]]
            if hw.get("filter_sets"):
                hardware.filter_sets = [FilterSet(**fs) for fs in hw["filter_sets"]]
            if hw.get("environmental_chamber"):
                hardware.environmental_chamber = EnvironmentalChamber(**hw["environmental_chamber"])
            hardware.manufacturer = hw.get("manufacturer")
            hardware.model = hw.get("model")

        scheduling = SchedulingConfig()
        if data.get("scheduling"):
            sched = data["scheduling"]
            scheduling.weekday_start = sched.get("weekday_start", "08:00")
            scheduling.weekday_end = sched.get("weekday_end", "18:00")
            scheduling.weekend_start = sched.get("weekend_start")
            scheduling.weekend_end = sched.get("weekend_end")
            scheduling.max_booking_duration_hours = sched.get("max_booking_duration_hours", 8)
            scheduling.min_booking_duration_hours = sched.get("min_booking_duration_hours", 0.5)
            scheduling.advance_booking_days = sched.get("advance_booking_days", 14)

        primary_contact = Contact(**data["primary_contact"]) if data.get("primary_contact") else None
        reviewers = [Contact(**r) for r in data.get("reviewers", [])]
        metrics = Metrics(**data["metrics"]) if data.get("metrics") else Metrics()

        return cls(
            microscope_id=data["microscope_id"],
            type=MicroscopeType(data["type"]),
            status=MicroscopeStatus(data.get("status", "offline")),
            name=data.get("name"),
            location=location,
            capabilities=data.get("capabilities", []),
            hardware=hardware,
            scheduling=scheduling,
            primary_contact=primary_contact,
            reviewers=reviewers,
            metrics=metrics,
            last_heartbeat=data.get("last_heartbeat"),
            registered_at=data.get("registered_at", datetime.utcnow().isoformat()),
        )


class MicroscopeRegistry:
    """
    Registry of available microscopes and their capabilities.
    Enables routing experiments to appropriate instruments.
    """

    def __init__(self, storage_path: str = "microscope_registry.json"):
        self.storage_path = Path(storage_path)
        self.microscopes: dict[str, MicroscopeCapability] = {}
        self._load()

    def _load(self):
        """Load registry from persistent storage."""
        if self.storage_path.exists():
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
                for mic_data in data.get("microscopes", []):
                    mic = MicroscopeCapability.from_dict(mic_data)
                    self.microscopes[mic.microscope_id] = mic

    def _save(self):
        """Save registry to persistent storage."""
        data = {
            "last_updated": datetime.utcnow().isoformat(),
            "schema_version": "1.0.0",
            "microscopes": [mic.to_dict() for mic in self.microscopes.values()]
        }
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)

    def register(self, microscope: MicroscopeCapability) -> MicroscopeCapability:
        """Register a new microscope or update an existing one."""
        microscope.update_heartbeat()
        self.microscopes[microscope.microscope_id] = microscope
        self._save()
        return microscope

    def unregister(self, microscope_id: str) -> bool:
        """Remove a microscope from the registry."""
        if microscope_id in self.microscopes:
            del self.microscopes[microscope_id]
            self._save()
            return True
        return False

    def get(self, microscope_id: str) -> Optional[MicroscopeCapability]:
        """Get a specific microscope by ID."""
        return self.microscopes.get(microscope_id)

    def list(
        self,
        type: Optional[str] = None,
        status: Optional[str] = None,
        capability: Optional[str] = None,
    ) -> list[MicroscopeCapability]:
        """List microscopes with optional filtering."""
        results = list(self.microscopes.values())

        if type:
            type_enum = MicroscopeType(type)
            results = [m for m in results if m.type == type_enum]

        if status:
            status_enum = MicroscopeStatus(status)
            results = [m for m in results if m.status == status_enum]

        if capability:
            results = [m for m in results if m.supports_capability(capability)]

        return results

    def update_status(
        self,
        microscope_id: str,
        status: str,
    ) -> bool:
        """Update the operational status of a microscope."""
        microscope = self.microscopes.get(microscope_id)
        if not microscope:
            return False

        microscope.status = MicroscopeStatus(status)
        microscope.update_heartbeat()
        self._save()
        return True

    def heartbeat(self, microscope_id: str) -> bool:
        """Record a heartbeat from a microscope."""
        microscope = self.microscopes.get(microscope_id)
        if not microscope:
            return False

        microscope.update_heartbeat()
        self._save()
        return True

    def find_suitable(
        self,
        microscope_type: Optional[str] = None,
        required_capabilities: Optional[list[str]] = None,
        required_wavelengths: Optional[list[int]] = None,
        required_magnification: Optional[int] = None,
        only_available: bool = True,
    ) -> list[MicroscopeCapability]:
        """
        Find microscopes that match the given requirements.

        Args:
            microscope_type: Required microscope type
            required_capabilities: List of required capabilities
            required_wavelengths: List of required excitation wavelengths
            required_magnification: Required objective magnification
            only_available: Only return online microscopes

        Returns:
            List of matching microscopes, sorted by suitability
        """
        candidates = list(self.microscopes.values())

        if only_available:
            candidates = [m for m in candidates if m.status == MicroscopeStatus.ONLINE]

        if microscope_type:
            type_enum = MicroscopeType(microscope_type)
            candidates = [m for m in candidates if m.type == type_enum]

        if required_capabilities:
            candidates = [m for m in candidates if m.supports_all(required_capabilities)]

        if required_wavelengths:
            candidates = [m for m in candidates if all(m.has_wavelength(wl) for wl in required_wavelengths)]

        if required_magnification:
            candidates = [m for m in candidates if m.has_objective(required_magnification)]

        # Sort by metrics (experiments completed, uptime)
        def score(mic: MicroscopeCapability) -> tuple:
            uptime = mic.metrics.uptime_percentage or 0
            experiments = mic.metrics.experiments_completed or 0
            return (-uptime, -experiments)

        candidates.sort(key=score)

        return candidates

    def get_reviewer_emails(self, microscope_type: str) -> list[str]:
        """Get reviewer email addresses for a microscope type."""
        emails = []
        for mic in self.list(type=microscope_type):
            for reviewer in mic.reviewers:
                if reviewer.email not in emails:
                    emails.append(reviewer.email)
        return emails


def main():
    """Example usage of the microscope registry."""
    print("=== gently-meta Microscope Registry ===\n")

    registry = MicroscopeRegistry("gently_meta_microscopes.json")

    # Register a DiSPIM
    print("1. Registering DiSPIM microscope...")

    dispim = MicroscopeCapability(
        microscope_id="dispim-001",
        type=MicroscopeType.DISPIM,
        status=MicroscopeStatus.ONLINE,
        name="DiSPIM Alpha",
        location=Location(
            institution="University of Biology",
            building="Life Sciences",
            room="302",
            timezone="America/New_York",
        ),
        capabilities=[
            "3d_imaging",
            "live_cell",
            "fast_acquisition",
            "minimal_phototoxicity",
            "time_lapse",
            "environmental_control",
        ],
        hardware=Hardware(
            manufacturer="ASI",
            model="DiSPIM",
            objectives=[
                Objective(magnification=40, numerical_aperture=0.8, immersion="water"),
            ],
            light_sources=[
                LightSource(type="laser", wavelengths=[488, 561, 640]),
            ],
            detectors=[
                Detector(type="sCMOS", pixel_size_um=6.5, resolution_x=2048, resolution_y=2048),
            ],
            environmental_chamber=EnvironmentalChamber(
                available=True,
                temperature_control=True,
                co2_control=True,
            ),
        ),
        primary_contact=Contact(name="Ryan", email="ryan@lab.org"),
        reviewers=[Contact(name="Ryan", email="ryan@lab.org")],
    )

    registry.register(dispim)
    print(f"   Registered: {dispim.microscope_id}")

    # Register a confocal
    print("\n2. Registering confocal microscope...")

    confocal = MicroscopeCapability(
        microscope_id="confocal-001",
        type=MicroscopeType.CONFOCAL,
        status=MicroscopeStatus.ONLINE,
        name="Confocal Beta",
        capabilities=[
            "3d_imaging",
            "fixed_cell",
            "high_resolution",
            "multi_channel",
        ],
        hardware=Hardware(
            manufacturer="Zeiss",
            model="LSM 880",
            objectives=[
                Objective(magnification=20, numerical_aperture=0.8, immersion="air"),
                Objective(magnification=63, numerical_aperture=1.4, immersion="oil"),
            ],
            light_sources=[
                LightSource(type="laser", wavelengths=[405, 488, 561, 633]),
            ],
        ),
        reviewers=[Contact(name="Imaging Team", email="imaging@lab.org")],
    )

    registry.register(confocal)
    print(f"   Registered: {confocal.microscope_id}")

    # Find suitable microscopes
    print("\n3. Finding microscopes for live cell imaging...")
    suitable = registry.find_suitable(
        required_capabilities=["live_cell", "time_lapse"],
    )
    for mic in suitable:
        print(f"   - {mic.microscope_id} ({mic.type.value})")

    # List all online microscopes
    print("\n4. All online microscopes:")
    online = registry.list(status="online")
    for mic in online:
        print(f"   - {mic.microscope_id}: {mic.name or 'unnamed'} ({mic.type.value})")


if __name__ == "__main__":
    main()
