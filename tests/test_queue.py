"""Tests for the experiment queue system."""

import json
import tempfile
from pathlib import Path

import pytest

from gently_meta.queue import (
    ExperimentQueue,
    ExperimentRequest,
    Priority,
    RequestStatus,
    Requester,
)


@pytest.fixture
def temp_queue():
    """Create a temporary queue for testing."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        queue = ExperimentQueue(storage_path=f.name)
        yield queue
        Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def sample_spec():
    """Sample specification for testing."""
    return {
        "sample_id": "test_sample_001",
        "biological_context": {
            "cell_line": "HeLa",
            "passage_number": 12,
        },
        "imaging_parameters": {
            "microscope_type": "light_sheet",
            "channels": [{"name": "GFP", "excitation": 488}],
        },
    }


class TestExperimentRequest:
    """Tests for ExperimentRequest class."""

    def test_create_request(self, sample_spec):
        """Test creating an experiment request."""
        requester = Requester(
            name="Dr. Test",
            email="test@example.com",
            institution="Test University",
        )

        request = ExperimentRequest(
            sample_spec=sample_spec,
            requester=requester,
            microscope_system="DiSPIM",
            scientific_rationale="Test the system",
        )

        assert request.request_id is not None
        assert request.status == RequestStatus.SUBMITTED
        assert request.priority == Priority.MEDIUM
        assert request.requester.name == "Dr. Test"
        assert len(request.history) == 1

    def test_to_dict_and_back(self, sample_spec):
        """Test serialization and deserialization."""
        requester = Requester(
            name="Dr. Test",
            email="test@example.com",
            institution="Test University",
        )

        original = ExperimentRequest(
            sample_spec=sample_spec,
            requester=requester,
            microscope_system="DiSPIM",
            scientific_rationale="Test the system",
            priority=Priority.HIGH,
        )

        data = original.to_dict()
        restored = ExperimentRequest.from_dict(data)

        assert restored.request_id == original.request_id
        assert restored.status == original.status
        assert restored.priority == original.priority
        assert restored.requester.name == original.requester.name


class TestExperimentQueue:
    """Tests for ExperimentQueue class."""

    def test_submit_request(self, temp_queue, sample_spec):
        """Test submitting an experiment request."""
        request = temp_queue.submit(
            sample_spec=sample_spec,
            requester_name="Dr. Test",
            requester_email="test@example.com",
            requester_institution="Test University",
            microscope_system="DiSPIM",
            scientific_rationale="Test submission functionality",
        )

        assert request.request_id in temp_queue.requests
        assert request.status == RequestStatus.SUBMITTED

    def test_get_request(self, temp_queue, sample_spec):
        """Test retrieving a request by ID."""
        request = temp_queue.submit(
            sample_spec=sample_spec,
            requester_name="Dr. Test",
            requester_email="test@example.com",
            requester_institution="Test University",
            microscope_system="DiSPIM",
            scientific_rationale="Test retrieval",
        )

        retrieved = temp_queue.get(request.request_id)
        assert retrieved is not None
        assert retrieved.request_id == request.request_id

        # Non-existent request
        assert temp_queue.get("non-existent-id") is None

    def test_list_with_filters(self, temp_queue, sample_spec):
        """Test listing requests with filters."""
        # Submit multiple requests
        temp_queue.submit(
            sample_spec=sample_spec,
            requester_name="Dr. A",
            requester_email="a@example.com",
            requester_institution="University A",
            microscope_system="DiSPIM",
            scientific_rationale="Rationale A",
            priority="high",
        )

        temp_queue.submit(
            sample_spec=sample_spec,
            requester_name="Dr. B",
            requester_email="b@example.com",
            requester_institution="University B",
            microscope_system="confocal",
            scientific_rationale="Rationale B",
            priority="low",
        )

        # Filter by microscope
        dispim_requests = temp_queue.list(microscope_system="DiSPIM")
        assert len(dispim_requests) == 1
        assert dispim_requests[0].requester.name == "Dr. A"

        # Filter by priority
        high_priority = temp_queue.list(priority="high")
        assert len(high_priority) == 1

        # All requests
        all_requests = temp_queue.list()
        assert len(all_requests) == 2

    def test_approve_request(self, temp_queue, sample_spec):
        """Test approving a request."""
        request = temp_queue.submit(
            sample_spec=sample_spec,
            requester_name="Dr. Test",
            requester_email="test@example.com",
            requester_institution="Test University",
            microscope_system="DiSPIM",
            scientific_rationale="Test approval",
        )

        success = temp_queue.approve(
            request_id=request.request_id,
            reviewer_name="Reviewer",
            comments="Approved for testing",
            scheduled_date="2025-12-01T09:00:00",
        )

        assert success
        updated = temp_queue.get(request.request_id)
        assert updated.status == RequestStatus.SCHEDULED
        assert updated.review.reviewer_name == "Reviewer"
        assert len(updated.history) == 2  # submitted + approved

    def test_reject_request(self, temp_queue, sample_spec):
        """Test rejecting a request."""
        request = temp_queue.submit(
            sample_spec=sample_spec,
            requester_name="Dr. Test",
            requester_email="test@example.com",
            requester_institution="Test University",
            microscope_system="DiSPIM",
            scientific_rationale="Test rejection",
        )

        success = temp_queue.reject(
            request_id=request.request_id,
            reviewer_name="Reviewer",
            comments="Insufficient justification",
        )

        assert success
        updated = temp_queue.get(request.request_id)
        assert updated.status == RequestStatus.REJECTED
        assert updated.review.comments == "Insufficient justification"

    def test_update_status(self, temp_queue, sample_spec):
        """Test status updates."""
        request = temp_queue.submit(
            sample_spec=sample_spec,
            requester_name="Dr. Test",
            requester_email="test@example.com",
            requester_institution="Test University",
            microscope_system="DiSPIM",
            scientific_rationale="Test status updates",
        )

        # Approve first
        temp_queue.approve(
            request_id=request.request_id,
            reviewer_name="Reviewer",
        )

        # Start execution
        temp_queue.update_status(
            request_id=request.request_id,
            new_status="in_progress",
            actor="operator",
        )
        updated = temp_queue.get(request.request_id)
        assert updated.status == RequestStatus.IN_PROGRESS
        assert updated.execution.start_time is not None

        # Complete
        temp_queue.update_status(
            request_id=request.request_id,
            new_status="completed",
            actor="operator",
            results_location="/data/results/test",
        )
        updated = temp_queue.get(request.request_id)
        assert updated.status == RequestStatus.COMPLETED
        assert updated.results.data_location == "/data/results/test"

    def test_priority_sorting(self, temp_queue, sample_spec):
        """Test that requests are sorted by priority."""
        # Submit in non-priority order
        temp_queue.submit(
            sample_spec=sample_spec,
            requester_name="Low",
            requester_email="low@example.com",
            requester_institution="U",
            microscope_system="DiSPIM",
            scientific_rationale="Low priority",
            priority="low",
        )

        temp_queue.submit(
            sample_spec=sample_spec,
            requester_name="Urgent",
            requester_email="urgent@example.com",
            requester_institution="U",
            microscope_system="DiSPIM",
            scientific_rationale="Urgent priority",
            priority="urgent",
        )

        temp_queue.submit(
            sample_spec=sample_spec,
            requester_name="Medium",
            requester_email="medium@example.com",
            requester_institution="U",
            microscope_system="DiSPIM",
            scientific_rationale="Medium priority",
            priority="medium",
        )

        requests = temp_queue.list()
        priorities = [r.priority.value for r in requests]
        assert priorities == ["urgent", "medium", "low"]

    def test_get_stats(self, temp_queue, sample_spec):
        """Test statistics generation."""
        temp_queue.submit(
            sample_spec=sample_spec,
            requester_name="Dr. Test",
            requester_email="test@example.com",
            requester_institution="Test University",
            microscope_system="DiSPIM",
            scientific_rationale="Test stats",
            priority="high",
        )

        stats = temp_queue.get_stats()
        assert stats["total_requests"] == 1
        assert stats["by_status"]["submitted"] == 1
        assert stats["by_microscope"]["DiSPIM"] == 1
        assert stats["by_priority"]["high"] == 1

    def test_persistence(self, sample_spec):
        """Test that data persists across queue instances."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            storage_path = f.name

        try:
            # Create queue and submit request
            queue1 = ExperimentQueue(storage_path=storage_path)
            request = queue1.submit(
                sample_spec=sample_spec,
                requester_name="Dr. Test",
                requester_email="test@example.com",
                requester_institution="Test University",
                microscope_system="DiSPIM",
                scientific_rationale="Test persistence",
            )
            request_id = request.request_id

            # Create new queue instance
            queue2 = ExperimentQueue(storage_path=storage_path)
            retrieved = queue2.get(request_id)

            assert retrieved is not None
            assert retrieved.requester.name == "Dr. Test"

        finally:
            Path(storage_path).unlink(missing_ok=True)
