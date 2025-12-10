"""Channel configuration models."""

from pydantic import BaseModel, Field


class YouTubeConfig(BaseModel):
    """YouTube channel configuration.

    Attributes:
        channel_id: YouTube channel ID
        handle: YouTube handle (e.g., @username)
    """

    channel_id: str = Field(..., description="YouTube channel ID")
    handle: str = Field(..., pattern=r"^@[a-zA-Z0-9_-]+$", description="YouTube handle")


class ChannelInfo(BaseModel):
    """Basic channel information.

    Attributes:
        id: Unique channel identifier
        name: Channel display name
        description: Channel description
        youtube: YouTube connection settings
    """

    id: str = Field(..., pattern=r"^[a-z0-9-]+$", description="Channel ID")
    name: str = Field(..., min_length=1, max_length=100, description="Channel name")
    description: str = Field(..., min_length=1, max_length=500, description="Channel description")
    youtube: YouTubeConfig
