"""
Experiment Queue Management System

Manages imaging experiment requests from researchers worldwide,
enabling reviewers to approve/reject experiments for specific microscope systems.
"""

import json
import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Callable


class RequestStatus(Enum):
    """Status states for experiment requests."""
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class Priority(Enum):
    """Priority levels for experiment requests."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

    @property
    def sort_order(self) -> int:
        return {"urgent": 0, "high": 1, "medium": 2, "low": 3}[self.value]


@dataclass
class Requester:
    """Information about the experiment requester."""
    name: str
    email: str
    institution: str
    department: Optional[str] = None
    country: Optional[str] = None
    orcid: Optional[str] = None


@dataclass
class ReviewInfo:
    """Review workflow information."""
    reviewer_name: Optional[str] = None
    reviewer_email: Optional[str] = None
    review_date: Optional[str] = None
    comments: Optional[str] = None
    requested_modifications: list[str] = field(default_factory=list)


@dataclass
class SchedulingInfo:
    """Scheduling information for approved experiments."""
    scheduled_date: Optional[str] = None
    assigned_microscope_id: Optional[str] = None
    estimated_start: Optional[str] = None
    estimated_end: Optional[str] = None


@dataclass
class ExecutionInfo:
    """Execution tracking information."""
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    actual_microscope_id: Optional[str] = None
    operator: Optional[str] = None
    completion_status: Optional[str] = None
    execution_notes: Optional[str] = None


@dataclass
class ResultsInfo:
    """Information about experiment results."""
    data_location: Optional[str] = None
    data_size_gb: Optional[float] = None
    file_count: Optional[int] = None
    quality_metrics: dict[str, Any] = field(default_factory=dict)
    preliminary_analysis: Optional[str] = None


@dataclass
class HistoryEntry:
    """Audit trail entry."""
    timestamp: str
    event: str
    actor: str
    details: Optional[str] = None


@dataclass
class BiologicalQuery:
    """
    Query parameters for searching experiments by biological context.

    All fields are optional - only non-None fields are used for filtering.
    String fields support partial matching (case-insensitive).
    List fields match if any item overlaps with the sample's list.
    """
    # Core biological identifiers
    cell_line: Optional[str] = None
    organism: Optional[str] = None
    tissue_type: Optional[str] = None

    # Genetic context
    genetic_modifications: Optional[list[str]] = None  # Match any
    fluorescent_proteins: Optional[list[str]] = None   # Match any (by name)

    # Staining/markers
    antibody_targets: Optional[list[str]] = None       # Match any primary antibody target
    fluorophores: Optional[list[str]] = None           # Match any (secondary antibodies or FPs)
    nuclear_stain: Optional[str] = None

    # Treatments
    compound_names: Optional[list[str]] = None         # Match any compound

    # Imaging requirements
    microscope_type: Optional[str] = None
    has_z_stack: Optional[bool] = None
    has_time_lapse: Optional[bool] = None
    live_cell: Optional[bool] = None  # fixation_method == "live"

    # Request metadata
    status: Optional[str] = None

    def matches(self, request: "ExperimentRequest") -> bool:
        """Check if an experiment request matches this query."""
        spec = request.sample_spec
        bio = spec.get("biological_context", {})
        staining = spec.get("staining_protocol", {})
        imaging = spec.get("imaging_parameters", {})
        treatments = spec.get("treatments", {})
        prep = spec.get("sample_preparation", {})

        # Helper for case-insensitive partial match
        def str_match(query_val: Optional[str], target_val: Any) -> bool:
            if query_val is None:
                return True
            if target_val is None:
                return False
            return query_val.lower() in str(target_val).lower()

        # Helper for list overlap (any match)
        def list_overlap(query_list: Optional[list], target_list: list) -> bool:
            if query_list is None:
                return True
            if not target_list:
                return False
            query_lower = {q.lower() for q in query_list}
            target_lower = {str(t).lower() for t in target_list}
            return bool(query_lower & target_lower)

        # Core biological context
        if not str_match(self.cell_line, bio.get("cell_line")):
            return False
        if not str_match(self.organism, bio.get("organism")):
            return False
        if not str_match(self.tissue_type, bio.get("tissue_type")):
            return False

        # Genetic modifications
        if self.genetic_modifications is not None:
            target_mods = bio.get("genetic_modifications", [])
            if not list_overlap(self.genetic_modifications, target_mods):
                return False

        # Fluorescent proteins (in staining_protocol)
        if self.fluorescent_proteins is not None:
            fps = staining.get("fluorescent_proteins", [])
            fp_names = [fp.get("name", "") for fp in fps]
            if not list_overlap(self.fluorescent_proteins, fp_names):
                return False

        # Antibody targets
        if self.antibody_targets is not None:
            primaries = staining.get("primary_antibodies", [])
            targets = [ab.get("target", "") for ab in primaries]
            if not list_overlap(self.antibody_targets, targets):
                return False

        # Fluorophores (from secondary antibodies)
        if self.fluorophores is not None:
            secondaries = staining.get("secondary_antibodies", [])
            fluors = [ab.get("fluorophore", "") for ab in secondaries]
            # Also include FP names
            fps = staining.get("fluorescent_proteins", [])
            fluors.extend([fp.get("name", "") for fp in fps])
            if not list_overlap(self.fluorophores, fluors):
                return False

        # Nuclear stain
        if not str_match(self.nuclear_stain, staining.get("nuclear_stain")):
            return False

        # Compound treatments
        if self.compound_names is not None:
            compounds = treatments.get("compounds", [])
            names = [c.get("name", "") for c in compounds]
            if not list_overlap(self.compound_names, names):
                return False

        # Microscope type
        if not str_match(self.microscope_type, imaging.get("microscope_type")):
            return False

        # Z-stack
        if self.has_z_stack is not None:
            z_stack = imaging.get("z_stack", {})
            has_z = z_stack.get("enabled", False)
            if self.has_z_stack != has_z:
                return False

        # Time-lapse
        if self.has_time_lapse is not None:
            time_lapse = imaging.get("time_lapse", {})
            has_tl = time_lapse.get("enabled", False)
            if self.has_time_lapse != has_tl:
                return False

        # Live cell imaging
        if self.live_cell is not None:
            is_live = prep.get("fixation_method") == "live"
            if self.live_cell != is_live:
                return False

        # Request status
        if self.status is not None:
            if request.status.value != self.status:
                return False

        return True


@dataclass
class ExperimentRequest:
    """
    Represents a single experiment request with approval workflow.
    Extends Sample_Spec with request metadata and status tracking.
    """
    sample_spec: dict[str, Any]
    requester: Requester
    microscope_system: str
    scientific_rationale: str

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    submission_date: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    status: RequestStatus = RequestStatus.SUBMITTED
    priority: Priority = Priority.MEDIUM

    review: ReviewInfo = field(default_factory=ReviewInfo)
    scheduling: SchedulingInfo = field(default_factory=SchedulingInfo)
    execution: ExecutionInfo = field(default_factory=ExecutionInfo)
    results: ResultsInfo = field(default_factory=ResultsInfo)
    history: list[HistoryEntry] = field(default_factory=list)

    def __post_init__(self):
        # Add submission event to history
        if not self.history:
            self.add_history_entry("submitted", self.requester.name, "Request submitted")

    def add_history_entry(self, event: str, actor: str, details: Optional[str] = None):
        """Add an entry to the audit trail."""
        self.history.append(HistoryEntry(
            timestamp=datetime.utcnow().isoformat(),
            event=event,
            actor=actor,
            details=details
        ))

    def to_dict(self) -> dict[str, Any]:
        """Convert request to dictionary for serialization."""
        def convert(obj):
            if isinstance(obj, Enum):
                return obj.value
            if hasattr(obj, '__dataclass_fields__'):
                return {k: convert(v) for k, v in asdict(obj).items()}
            if isinstance(obj, list):
                return [convert(item) for item in obj]
            if isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items()}
            return obj

        return {
            "request_id": self.request_id,
            "submission_date": self.submission_date,
            "status": self.status.value,
            "priority": self.priority.value,
            "requester": convert(self.requester),
            "experiment": {
                "sample_spec": self.sample_spec,
                "microscope_system": self.microscope_system,
                "scientific_rationale": self.scientific_rationale,
            },
            "review": convert(self.review),
            "scheduling": convert(self.scheduling),
            "execution": convert(self.execution),
            "results": convert(self.results),
            "history": convert(self.history),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentRequest":
        """Create ExperimentRequest from dictionary."""
        requester = Requester(**data["requester"])

        request = cls(
            sample_spec=data["experiment"]["sample_spec"],
            requester=requester,
            microscope_system=data["experiment"]["microscope_system"],
            scientific_rationale=data["experiment"]["scientific_rationale"],
            request_id=data["request_id"],
            submission_date=data["submission_date"],
            status=RequestStatus(data["status"]),
            priority=Priority(data.get("priority", "medium")),
        )

        # Restore review info
        if data.get("review"):
            request.review = ReviewInfo(**data["review"])

        # Restore scheduling info
        if data.get("scheduling"):
            request.scheduling = SchedulingInfo(**data["scheduling"])

        # Restore execution info
        if data.get("execution"):
            request.execution = ExecutionInfo(**data["execution"])

        # Restore results info
        if data.get("results"):
            request.results = ResultsInfo(**data["results"])

        # Restore history
        if data.get("history"):
            request.history = [HistoryEntry(**entry) for entry in data["history"]]

        return request


class ExperimentQueue:
    """
    Manages the queue of experiment requests with approval workflow.
    Provides methods for submission, review, and status tracking.
    """

    def __init__(self, storage_path: str = "experiment_queue.json"):
        self.storage_path = Path(storage_path)
        self.requests: dict[str, ExperimentRequest] = {}
        self._load()

    def _load(self):
        """Load requests from persistent storage."""
        if self.storage_path.exists():
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
                for req_data in data.get("requests", []):
                    req = ExperimentRequest.from_dict(req_data)
                    self.requests[req.request_id] = req

    def _save(self):
        """Save requests to persistent storage."""
        data = {
            "last_updated": datetime.utcnow().isoformat(),
            "schema_version": "1.0.0",
            "requests": [req.to_dict() for req in self.requests.values()]
        }
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)

    def submit(
        self,
        sample_spec: dict[str, Any],
        requester_name: str,
        requester_email: str,
        requester_institution: str,
        microscope_system: str,
        scientific_rationale: str,
        priority: str = "medium",
        **requester_kwargs,
    ) -> ExperimentRequest:
        """
        Submit a new experiment request to the queue.

        Returns:
            The created ExperimentRequest
        """
        requester = Requester(
            name=requester_name,
            email=requester_email,
            institution=requester_institution,
            **requester_kwargs,
        )

        request = ExperimentRequest(
            sample_spec=sample_spec,
            requester=requester,
            microscope_system=microscope_system,
            scientific_rationale=scientific_rationale,
            priority=Priority(priority),
        )

        self.requests[request.request_id] = request
        self._save()

        return request

    def get(self, request_id: str) -> Optional[ExperimentRequest]:
        """Retrieve a specific request by ID."""
        return self.requests.get(request_id)

    def list(
        self,
        status: Optional[str] = None,
        microscope_system: Optional[str] = None,
        priority: Optional[str] = None,
        requester_email: Optional[str] = None,
    ) -> list[ExperimentRequest]:
        """
        List requests with optional filtering.

        Results are sorted by priority (urgent first) then submission date.
        """
        results = list(self.requests.values())

        if status:
            status_enum = RequestStatus(status)
            results = [r for r in results if r.status == status_enum]

        if microscope_system:
            results = [r for r in results if r.microscope_system == microscope_system]

        if priority:
            priority_enum = Priority(priority)
            results = [r for r in results if r.priority == priority_enum]

        if requester_email:
            results = [r for r in results if r.requester.email == requester_email]

        # Sort by priority then submission date
        results.sort(key=lambda r: (r.priority.sort_order, r.submission_date))

        return results

    def find_by_biology(
        self,
        query: Optional[BiologicalQuery] = None,
        **kwargs,
    ) -> list[ExperimentRequest]:
        """
        Search experiments by biological context.

        Can pass a BiologicalQuery object or keyword arguments directly.

        Example usage:
            # Using BiologicalQuery
            query = BiologicalQuery(cell_line="HeLa", has_time_lapse=True)
            results = queue.find_by_biology(query)

            # Using kwargs directly
            results = queue.find_by_biology(cell_line="HeLa", organism="human")

            # Find all GFP experiments
            results = queue.find_by_biology(fluorescent_proteins=["GFP", "EGFP"])

            # Find live-cell time-lapse with specific treatment
            results = queue.find_by_biology(
                live_cell=True,
                has_time_lapse=True,
                compound_names=["nocodazole"]
            )

        Returns:
            List of matching ExperimentRequest objects, sorted by priority then date.
        """
        if query is None:
            query = BiologicalQuery(**kwargs)

        results = [req for req in self.requests.values() if query.matches(req)]
        results.sort(key=lambda r: (r.priority.sort_order, r.submission_date))

        return results

    def get_sample_summary(self, request_id: str) -> Optional[dict[str, Any]]:
        """
        Get a summary of the biological context for a specific experiment.

        Returns a flattened view of key sample properties for quick inspection.
        """
        request = self.requests.get(request_id)
        if not request:
            return None

        spec = request.sample_spec
        bio = spec.get("biological_context", {})
        staining = spec.get("staining_protocol", {})
        imaging = spec.get("imaging_parameters", {})
        prep = spec.get("sample_preparation", {})

        # Extract fluorophore/marker info
        fps = staining.get("fluorescent_proteins", [])
        secondaries = staining.get("secondary_antibodies", [])
        primaries = staining.get("primary_antibodies", [])

        return {
            "request_id": request_id,
            "status": request.status.value,
            "cell_line": bio.get("cell_line"),
            "organism": bio.get("organism"),
            "tissue_type": bio.get("tissue_type"),
            "genetic_modifications": bio.get("genetic_modifications", []),
            "fluorescent_proteins": [fp.get("name") for fp in fps],
            "antibody_targets": [ab.get("target") for ab in primaries],
            "fluorophores": (
                [ab.get("fluorophore") for ab in secondaries] +
                [fp.get("name") for fp in fps]
            ),
            "nuclear_stain": staining.get("nuclear_stain"),
            "microscope_type": imaging.get("microscope_type"),
            "live_cell": prep.get("fixation_method") == "live",
            "has_z_stack": imaging.get("z_stack", {}).get("enabled", False),
            "has_time_lapse": imaging.get("time_lapse", {}).get("enabled", False),
            "requester": request.requester.name,
            "institution": request.requester.institution,
        }

    def approve(
        self,
        request_id: str,
        reviewer_name: str,
        reviewer_email: Optional[str] = None,
        comments: str = "",
        scheduled_date: Optional[str] = None,
        assigned_microscope_id: Optional[str] = None,
    ) -> bool:
        """
        Approve an experiment request.

        Returns:
            True if successful, False if request not found
        """
        request = self.requests.get(request_id)
        if not request:
            return False

        request.status = RequestStatus.APPROVED
        request.review.reviewer_name = reviewer_name
        request.review.reviewer_email = reviewer_email
        request.review.comments = comments
        request.review.review_date = datetime.utcnow().isoformat()

        if scheduled_date:
            request.scheduling.scheduled_date = scheduled_date
            request.status = RequestStatus.SCHEDULED

        if assigned_microscope_id:
            request.scheduling.assigned_microscope_id = assigned_microscope_id

        request.add_history_entry("approved", reviewer_name, comments or "Request approved")

        self._save()
        return True

    def reject(
        self,
        request_id: str,
        reviewer_name: str,
        comments: str,
        reviewer_email: Optional[str] = None,
    ) -> bool:
        """
        Reject an experiment request.

        Returns:
            True if successful, False if request not found
        """
        request = self.requests.get(request_id)
        if not request:
            return False

        request.status = RequestStatus.REJECTED
        request.review.reviewer_name = reviewer_name
        request.review.reviewer_email = reviewer_email
        request.review.comments = comments
        request.review.review_date = datetime.utcnow().isoformat()

        request.add_history_entry("rejected", reviewer_name, comments)

        self._save()
        return True

    def request_revision(
        self,
        request_id: str,
        reviewer_name: str,
        requested_modifications: list[str],
        comments: str = "",
        reviewer_email: Optional[str] = None,
    ) -> bool:
        """
        Request revisions to an experiment request.

        Returns:
            True if successful, False if request not found
        """
        request = self.requests.get(request_id)
        if not request:
            return False

        request.status = RequestStatus.REVISION_REQUESTED
        request.review.reviewer_name = reviewer_name
        request.review.reviewer_email = reviewer_email
        request.review.comments = comments
        request.review.review_date = datetime.utcnow().isoformat()
        request.review.requested_modifications = requested_modifications

        request.add_history_entry(
            "revision_requested",
            reviewer_name,
            f"Modifications requested: {', '.join(requested_modifications)}"
        )

        self._save()
        return True

    def update_status(
        self,
        request_id: str,
        new_status: str,
        actor: str = "system",
        results_location: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """
        Update the status of an experiment request.

        Returns:
            True if successful, False if request not found
        """
        request = self.requests.get(request_id)
        if not request:
            return False

        old_status = request.status
        request.status = RequestStatus(new_status)

        if new_status == "in_progress":
            request.execution.start_time = datetime.utcnow().isoformat()
        elif new_status == "completed":
            request.execution.end_time = datetime.utcnow().isoformat()
            request.execution.completion_status = "success"
            if results_location:
                request.results.data_location = results_location
        elif new_status == "failed":
            request.execution.end_time = datetime.utcnow().isoformat()
            request.execution.completion_status = "failed"

        if notes:
            request.execution.execution_notes = notes

        request.add_history_entry(
            f"status_changed",
            actor,
            f"Status changed from {old_status.value} to {new_status}"
        )

        self._save()
        return True

    def get_pending_review(self, microscope_system: Optional[str] = None) -> list[ExperimentRequest]:
        """Get all requests pending review/approval."""
        return self.list(status="submitted", microscope_system=microscope_system)

    def get_approved_queue(self, microscope_system: Optional[str] = None) -> list[ExperimentRequest]:
        """Get all approved requests waiting to be executed."""
        approved = self.list(status="approved", microscope_system=microscope_system)
        scheduled = self.list(status="scheduled", microscope_system=microscope_system)
        return approved + scheduled

    def get_stats(self) -> dict[str, Any]:
        """Get queue statistics."""
        stats = {
            "total_requests": len(self.requests),
            "by_status": {},
            "by_microscope": {},
            "by_priority": {},
        }

        for request in self.requests.values():
            status_key = request.status.value
            stats["by_status"][status_key] = stats["by_status"].get(status_key, 0) + 1

            microscope_key = request.microscope_system
            stats["by_microscope"][microscope_key] = stats["by_microscope"].get(microscope_key, 0) + 1

            priority_key = request.priority.value
            stats["by_priority"][priority_key] = stats["by_priority"].get(priority_key, 0) + 1

        return stats


def main():
    """Example usage of the queue system."""
    print("=== gently-meta Experiment Queue ===\n")

    queue = ExperimentQueue("gently_meta_queue.json")

    # Submit a request
    print("1. Submitting experiment request...")

    request = queue.submit(
        sample_spec={
            "sample_id": "hela_timelapse_001",
            "biological_context": {
                "cell_line": "HeLa",
                "passage_number": 12,
            },
            "imaging_parameters": {
                "microscope_type": "light_sheet",
                "channels": [{"name": "GFP", "excitation": 488}],
                "time_lapse": {"enabled": True, "interval": 300},
            },
        },
        requester_name="Dr. Jane Smith",
        requester_email="jsmith@university.edu",
        requester_institution="University of Biology",
        microscope_system="DiSPIM",
        scientific_rationale="Study cell division dynamics in HeLa cells using fast volumetric imaging.",
        priority="high",
    )

    print(f"   Request ID: {request.request_id}")
    print(f"   Status: {request.status.value}\n")

    # List pending requests
    print("2. Pending reviews:")
    pending = queue.get_pending_review(microscope_system="DiSPIM")
    for req in pending:
        print(f"   - {req.request_id[:8]}... from {req.requester.name} ({req.priority.value})")

    # Approve request
    print("\n3. Approving request...")
    queue.approve(
        request_id=request.request_id,
        reviewer_name="Ryan",
        comments="Excellent use case for DiSPIM",
        scheduled_date="2025-11-20T09:00:00",
    )
    print(f"   Status: {queue.get(request.request_id).status.value}")

    # Show stats
    print("\n4. Queue statistics:")
    stats = queue.get_stats()
    print(f"   Total: {stats['total_requests']}")
    print(f"   By status: {stats['by_status']}")


if __name__ == "__main__":
    main()
