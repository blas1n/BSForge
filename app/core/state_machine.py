"""Generic State Machine for model status transitions.

This module provides a reusable state machine pattern for managing
status transitions across different models (Topic, Script, Video, Upload).

Example:
    # Define transitions
    UPLOAD_TRANSITIONS: TransitionMap[UploadStatus] = {
        UploadStatus.PENDING: [UploadStatus.SCHEDULED, UploadStatus.FAILED],
        UploadStatus.SCHEDULED: [UploadStatus.UPLOADING, UploadStatus.FAILED],
        UploadStatus.UPLOADING: [UploadStatus.PROCESSING, UploadStatus.FAILED],
        UploadStatus.PROCESSING: [UploadStatus.COMPLETED, UploadStatus.FAILED],
        UploadStatus.COMPLETED: [],
        UploadStatus.FAILED: [UploadStatus.PENDING],  # Allow retry
    }

    # Create state machine
    sm = StateMachine(UploadStatus.PENDING, UPLOAD_TRANSITIONS)

    # Check and perform transitions
    if sm.can_transition(UploadStatus.SCHEDULED):
        sm.transition(UploadStatus.SCHEDULED)

    # Or use transition_to for simpler API
    sm.transition_to(UploadStatus.UPLOADING)
"""

from enum import Enum
from typing import Generic, TypeVar

from app.core.exceptions import BSForgeError

T = TypeVar("T", bound=str | Enum)

# Type alias for transition maps
TransitionMap = dict[T, list[T]]


class InvalidTransitionError(BSForgeError):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, current: T, target: T, allowed: list[T] | None = None):
        self.current = current
        self.target = target
        self.allowed = allowed or []
        self.error_code = "INVALID_TRANSITION"
        allowed_str = ", ".join(str(s) for s in self.allowed) if self.allowed else "none"
        super().__init__(
            message=f"Invalid transition from '{current}' to '{target}'. "
            f"Allowed transitions: {allowed_str}",
            context={
                "current": str(current),
                "target": str(target),
                "allowed": [str(s) for s in self.allowed],
            },
        )


class StateMachine(Generic[T]):
    """Generic state machine for status transitions.

    Provides a type-safe way to manage status transitions with
    explicit allowed transitions defined upfront.

    Attributes:
        current: Current state
        transitions: Map of allowed transitions from each state

    Example:
        sm = StateMachine(
            initial=TopicStatus.PENDING,
            transitions={
                TopicStatus.PENDING: [TopicStatus.APPROVED, TopicStatus.REJECTED],
                TopicStatus.APPROVED: [TopicStatus.USED, TopicStatus.EXPIRED],
                TopicStatus.REJECTED: [],
                TopicStatus.USED: [],
                TopicStatus.EXPIRED: [],
            }
        )

        sm.transition_to(TopicStatus.APPROVED)  # OK
        sm.transition_to(TopicStatus.PENDING)   # Raises InvalidTransitionError
    """

    def __init__(self, initial: T, transitions: TransitionMap[T]):
        """Initialize state machine.

        Args:
            initial: Initial state
            transitions: Map of state -> list of allowed target states
        """
        self._current = initial
        self._transitions = transitions

    @property
    def current(self) -> T:
        """Get current state."""
        return self._current

    @property
    def allowed_transitions(self) -> list[T]:
        """Get list of states we can transition to from current state."""
        return self._transitions.get(self._current, [])

    def can_transition(self, target: T) -> bool:
        """Check if transition to target state is allowed.

        Args:
            target: Target state to check

        Returns:
            True if transition is allowed, False otherwise
        """
        return target in self.allowed_transitions

    def transition(self, target: T) -> None:
        """Perform transition to target state.

        Args:
            target: Target state

        Raises:
            InvalidTransitionError: If transition is not allowed
        """
        if not self.can_transition(target):
            raise InvalidTransitionError(
                current=self._current,
                target=target,
                allowed=self.allowed_transitions,
            )
        self._current = target

    def transition_to(self, target: T) -> T:
        """Perform transition and return new state.

        Convenience method that returns the new state after transition.

        Args:
            target: Target state

        Returns:
            The new current state (same as target)

        Raises:
            InvalidTransitionError: If transition is not allowed
        """
        self.transition(target)
        return self._current

    def reset(self, state: T) -> None:
        """Reset state machine to a specific state (bypass transition rules).

        Use with caution - this bypasses transition validation.
        Useful for testing or administrative operations.

        Args:
            state: State to reset to
        """
        self._current = state

    def __str__(self) -> str:
        return f"StateMachine(current={self._current})"

    def __repr__(self) -> str:
        return f"StateMachine(current={self._current!r}, allowed={self.allowed_transitions!r})"


# ============================================
# Predefined Transition Maps
# ============================================
# Import the actual status enums and define transitions


def get_topic_transitions() -> TransitionMap:
    """Get transition map for TopicStatus."""
    from app.models.topic import TopicStatus

    return {
        TopicStatus.PENDING: [TopicStatus.APPROVED, TopicStatus.REJECTED, TopicStatus.EXPIRED],
        TopicStatus.APPROVED: [TopicStatus.USED, TopicStatus.REJECTED, TopicStatus.EXPIRED],
        TopicStatus.REJECTED: [],  # Terminal state
        TopicStatus.USED: [TopicStatus.EXPIRED],
        TopicStatus.EXPIRED: [],  # Terminal state
    }


def get_script_transitions() -> TransitionMap:
    """Get transition map for ScriptStatus."""
    from app.models.script import ScriptStatus

    return {
        ScriptStatus.GENERATED: [ScriptStatus.REVIEWED, ScriptStatus.REJECTED],
        ScriptStatus.REVIEWED: [ScriptStatus.APPROVED, ScriptStatus.REJECTED],
        ScriptStatus.APPROVED: [ScriptStatus.PRODUCED, ScriptStatus.REJECTED],
        ScriptStatus.REJECTED: [],  # Terminal state
        ScriptStatus.PRODUCED: [],  # Terminal state
    }


def get_video_transitions() -> TransitionMap:
    """Get transition map for VideoStatus."""
    from app.models.video import VideoStatus

    return {
        VideoStatus.GENERATING: [VideoStatus.GENERATED, VideoStatus.FAILED],
        VideoStatus.GENERATED: [VideoStatus.REVIEWED, VideoStatus.REJECTED],
        VideoStatus.REVIEWED: [VideoStatus.APPROVED, VideoStatus.REJECTED],
        VideoStatus.APPROVED: [VideoStatus.UPLOADED, VideoStatus.REJECTED],
        VideoStatus.UPLOADED: [VideoStatus.ARCHIVED],
        VideoStatus.REJECTED: [VideoStatus.ARCHIVED],
        VideoStatus.FAILED: [VideoStatus.GENERATING],  # Allow retry
        VideoStatus.ARCHIVED: [],  # Terminal state
    }


def get_upload_transitions() -> TransitionMap:
    """Get transition map for UploadStatus."""
    from app.models.upload import UploadStatus

    return {
        UploadStatus.PENDING: [UploadStatus.SCHEDULED, UploadStatus.FAILED],
        UploadStatus.SCHEDULED: [UploadStatus.UPLOADING, UploadStatus.FAILED],
        UploadStatus.UPLOADING: [UploadStatus.PROCESSING, UploadStatus.FAILED],
        UploadStatus.PROCESSING: [UploadStatus.COMPLETED, UploadStatus.FAILED],
        UploadStatus.COMPLETED: [],  # Terminal state
        UploadStatus.FAILED: [UploadStatus.PENDING],  # Allow retry
    }


# ============================================
# Factory Functions
# ============================================


def create_topic_state_machine(initial_status: str | None = None) -> StateMachine:
    """Create a state machine for Topic status.

    Args:
        initial_status: Initial status (default: PENDING)

    Returns:
        Configured StateMachine for Topic
    """
    from app.models.topic import TopicStatus

    initial = TopicStatus(initial_status) if initial_status else TopicStatus.PENDING
    return StateMachine(initial, get_topic_transitions())


def create_script_state_machine(initial_status: str | None = None) -> StateMachine:
    """Create a state machine for Script status.

    Args:
        initial_status: Initial status (default: GENERATED)

    Returns:
        Configured StateMachine for Script
    """
    from app.models.script import ScriptStatus

    initial = ScriptStatus(initial_status) if initial_status else ScriptStatus.GENERATED
    return StateMachine(initial, get_script_transitions())


def create_video_state_machine(initial_status: str | None = None) -> StateMachine:
    """Create a state machine for Video status.

    Args:
        initial_status: Initial status (default: GENERATING)

    Returns:
        Configured StateMachine for Video
    """
    from app.models.video import VideoStatus

    initial = VideoStatus(initial_status) if initial_status else VideoStatus.GENERATING
    return StateMachine(initial, get_video_transitions())


def create_upload_state_machine(initial_status: str | None = None) -> StateMachine:
    """Create a state machine for Upload status.

    Args:
        initial_status: Initial status (default: PENDING)

    Returns:
        Configured StateMachine for Upload
    """
    from app.models.upload import UploadStatus

    initial = UploadStatus(initial_status) if initial_status else UploadStatus.PENDING
    return StateMachine(initial, get_upload_transitions())
