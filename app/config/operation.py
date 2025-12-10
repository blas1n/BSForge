"""Operation mode configuration models."""

from typing import Literal

from pydantic import BaseModel, Field


class ReviewGates(BaseModel):
    """Review gate configuration.

    Attributes:
        topic: Topic review mode
        script: Script review mode
        video: Video review mode
        upload: Upload review mode
    """

    topic: Literal["auto", "manual", "hybrid"] = Field(default="auto")
    script: Literal["auto", "manual", "hybrid"] = Field(default="manual")
    video: Literal["auto", "manual", "hybrid"] = Field(default="manual")
    upload: Literal["auto", "manual", "hybrid"] = Field(default="auto")


class AutoApproveConfig(BaseModel):
    """Auto-approval configuration.

    Attributes:
        max_risk_score: Maximum risk score for auto-approval
        require_series_match: Whether series match is required
    """

    max_risk_score: int = Field(default=20, ge=0, le=100)
    require_series_match: bool = Field(default=False)


class NotificationConfig(BaseModel):
    """Notification configuration.

    Attributes:
        telegram: Enable Telegram notifications
        new_review: Notify on new review items
        daily_summary: Send daily summary
    """

    telegram: bool = Field(default=True)
    new_review: bool = Field(default=True)
    daily_summary: bool = Field(default=True)


class OperationConfig(BaseModel):
    """Operation mode configuration.

    Attributes:
        review_gates: Review gate settings
        auto_approve: Auto-approval settings
        notifications: Notification settings
    """

    review_gates: ReviewGates = Field(default_factory=ReviewGates)
    auto_approve: AutoApproveConfig = Field(default_factory=AutoApproveConfig)
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)
