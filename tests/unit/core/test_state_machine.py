"""Unit tests for StateMachine."""

import pytest

from app.core.state_machine import (
    InvalidTransitionError,
    StateMachine,
    create_script_state_machine,
    create_topic_state_machine,
    create_upload_state_machine,
    create_video_state_machine,
)
from app.models.script import ScriptStatus
from app.models.topic import TopicStatus
from app.models.upload import UploadStatus
from app.models.video import VideoStatus


class TestStateMachine:
    """Tests for generic StateMachine."""

    @pytest.fixture
    def simple_transitions(self):
        """Create simple transition map for testing."""
        return {
            "start": ["middle", "end"],
            "middle": ["end"],
            "end": [],
        }

    @pytest.fixture
    def state_machine(self, simple_transitions):
        """Create state machine with simple transitions."""
        return StateMachine("start", simple_transitions)

    def test_initial_state(self, state_machine):
        """Test that initial state is set correctly."""
        assert state_machine.current == "start"

    def test_can_transition_valid(self, state_machine):
        """Test can_transition returns True for valid transitions."""
        assert state_machine.can_transition("middle") is True
        assert state_machine.can_transition("end") is True

    def test_can_transition_invalid(self, state_machine):
        """Test can_transition returns False for invalid transitions."""
        assert state_machine.can_transition("nonexistent") is False

    def test_transition_valid(self, state_machine):
        """Test valid transition updates state."""
        state_machine.transition("middle")
        assert state_machine.current == "middle"

    def test_transition_invalid_raises(self, state_machine):
        """Test invalid transition raises error."""
        state_machine.transition("middle")

        with pytest.raises(InvalidTransitionError) as exc_info:
            state_machine.transition("start")  # Can't go back

        assert exc_info.value.current == "middle"
        assert exc_info.value.target == "start"
        assert "end" in exc_info.value.allowed

    def test_transition_to_returns_state(self, state_machine):
        """Test transition_to returns new state."""
        result = state_machine.transition_to("middle")
        assert result == "middle"

    def test_allowed_transitions(self, state_machine):
        """Test allowed_transitions property."""
        assert state_machine.allowed_transitions == ["middle", "end"]

        state_machine.transition("end")
        assert state_machine.allowed_transitions == []

    def test_reset_bypasses_validation(self, state_machine):
        """Test reset allows setting any state."""
        state_machine.transition("end")  # Terminal state

        # Can't transition from end
        assert state_machine.can_transition("start") is False

        # But reset works
        state_machine.reset("start")
        assert state_machine.current == "start"

    def test_str_representation(self, state_machine):
        """Test string representation."""
        assert "start" in str(state_machine)

    def test_repr_representation(self, state_machine):
        """Test repr representation."""
        repr_str = repr(state_machine)
        assert "start" in repr_str
        assert "middle" in repr_str


class TestTopicStateMachine:
    """Tests for Topic state machine."""

    def test_create_with_default(self):
        """Test creating with default initial state."""
        sm = create_topic_state_machine()
        assert sm.current == TopicStatus.PENDING

    def test_create_with_initial(self):
        """Test creating with specific initial state."""
        sm = create_topic_state_machine("approved")
        assert sm.current == TopicStatus.APPROVED

    def test_pending_to_approved(self):
        """Test PENDING -> APPROVED transition."""
        sm = create_topic_state_machine()
        sm.transition_to(TopicStatus.APPROVED)
        assert sm.current == TopicStatus.APPROVED

    def test_pending_to_rejected(self):
        """Test PENDING -> REJECTED transition."""
        sm = create_topic_state_machine()
        sm.transition_to(TopicStatus.REJECTED)
        assert sm.current == TopicStatus.REJECTED

    def test_approved_to_used(self):
        """Test APPROVED -> USED transition."""
        sm = create_topic_state_machine("approved")
        sm.transition_to(TopicStatus.USED)
        assert sm.current == TopicStatus.USED

    def test_rejected_is_terminal(self):
        """Test REJECTED is a terminal state."""
        sm = create_topic_state_machine("rejected")
        assert sm.allowed_transitions == []


class TestScriptStateMachine:
    """Tests for Script state machine."""

    def test_create_with_default(self):
        """Test creating with default initial state."""
        sm = create_script_state_machine()
        assert sm.current == ScriptStatus.GENERATED

    def test_full_workflow(self):
        """Test complete workflow: GENERATED -> REVIEWED -> APPROVED -> PRODUCED."""
        sm = create_script_state_machine()

        sm.transition_to(ScriptStatus.REVIEWED)
        assert sm.current == ScriptStatus.REVIEWED

        sm.transition_to(ScriptStatus.APPROVED)
        assert sm.current == ScriptStatus.APPROVED

        sm.transition_to(ScriptStatus.PRODUCED)
        assert sm.current == ScriptStatus.PRODUCED

    def test_rejection_at_any_stage(self):
        """Test scripts can be rejected at various stages."""
        # From GENERATED
        sm1 = create_script_state_machine()
        sm1.transition_to(ScriptStatus.REJECTED)
        assert sm1.current == ScriptStatus.REJECTED

        # From REVIEWED
        sm2 = create_script_state_machine("reviewed")
        sm2.transition_to(ScriptStatus.REJECTED)
        assert sm2.current == ScriptStatus.REJECTED


class TestVideoStateMachine:
    """Tests for Video state machine."""

    def test_create_with_default(self):
        """Test creating with default initial state."""
        sm = create_video_state_machine()
        assert sm.current == VideoStatus.GENERATING

    def test_generation_success_workflow(self):
        """Test successful generation workflow."""
        sm = create_video_state_machine()

        sm.transition_to(VideoStatus.GENERATED)
        sm.transition_to(VideoStatus.REVIEWED)
        sm.transition_to(VideoStatus.APPROVED)
        sm.transition_to(VideoStatus.UPLOADED)

        assert sm.current == VideoStatus.UPLOADED

    def test_generation_failure_and_retry(self):
        """Test generation failure and retry."""
        sm = create_video_state_machine()

        sm.transition_to(VideoStatus.FAILED)
        assert sm.current == VideoStatus.FAILED

        # Can retry
        sm.transition_to(VideoStatus.GENERATING)
        assert sm.current == VideoStatus.GENERATING


class TestUploadStateMachine:
    """Tests for Upload state machine."""

    def test_create_with_default(self):
        """Test creating with default initial state."""
        sm = create_upload_state_machine()
        assert sm.current == UploadStatus.PENDING

    def test_full_upload_workflow(self):
        """Test complete upload workflow."""
        sm = create_upload_state_machine()

        sm.transition_to(UploadStatus.SCHEDULED)
        sm.transition_to(UploadStatus.UPLOADING)
        sm.transition_to(UploadStatus.PROCESSING)
        sm.transition_to(UploadStatus.COMPLETED)

        assert sm.current == UploadStatus.COMPLETED

    def test_failure_and_retry(self):
        """Test upload failure and retry flow."""
        sm = create_upload_state_machine()

        sm.transition_to(UploadStatus.SCHEDULED)
        sm.transition_to(UploadStatus.FAILED)

        # Can retry from FAILED
        sm.transition_to(UploadStatus.PENDING)
        assert sm.current == UploadStatus.PENDING

    def test_cannot_skip_states(self):
        """Test that states cannot be skipped."""
        sm = create_upload_state_machine()

        # Cannot go directly from PENDING to UPLOADING
        with pytest.raises(InvalidTransitionError):
            sm.transition_to(UploadStatus.UPLOADING)

        # Cannot go directly from PENDING to COMPLETED
        with pytest.raises(InvalidTransitionError):
            sm.transition_to(UploadStatus.COMPLETED)


class TestInvalidTransitionError:
    """Tests for InvalidTransitionError."""

    def test_error_attributes(self):
        """Test error has correct attributes."""
        error = InvalidTransitionError(
            current="a",
            target="b",
            allowed=["c", "d"],
        )

        assert error.current == "a"
        assert error.target == "b"
        assert error.allowed == ["c", "d"]

    def test_error_message(self):
        """Test error message formatting."""
        error = InvalidTransitionError(
            current="pending",
            target="completed",
            allowed=["scheduled", "failed"],
        )

        message = str(error)
        assert "pending" in message
        assert "completed" in message
        assert "scheduled" in message

    def test_error_code(self):
        """Test error has correct error code."""
        error = InvalidTransitionError("a", "b", [])
        assert error.error_code == "INVALID_TRANSITION"
