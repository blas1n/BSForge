"""Unit tests for Channel and Persona models.

Tests cover:
- Model creation and validation
- Relationships (Channel <-> Persona, Channel <-> Topic, Channel <-> Source)
- Enum types
- JSONB config fields
- CASCADE deletion behavior
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel, ChannelStatus, Persona, TTSService
from app.models.topic import Topic


class TestChannel:
    """Test Channel model."""

    @pytest.mark.asyncio
    async def test_create_channel(self, db_session: AsyncSession) -> None:
        """Test creating a basic channel."""
        channel = Channel(
            name="Test Channel",
            description="A test channel",
            status=ChannelStatus.ACTIVE,
            topic_config={"enabled": True},
            source_config={"weights": {"reddit": 1.0}},
            content_config={"length": "short"},
            operation_config={"mode": "auto"},
        )

        db_session.add(channel)
        await db_session.commit()
        await db_session.refresh(channel)

        # Verify
        assert channel.id is not None
        assert isinstance(channel.id, uuid.UUID)
        assert channel.name == "Test Channel"
        assert channel.status == ChannelStatus.ACTIVE
        assert channel.created_at is not None
        assert channel.updated_at is not None

    @pytest.mark.asyncio
    async def test_channel_default_values(self, db_session: AsyncSession) -> None:
        """Test channel default values."""
        channel = Channel(
            name="Default Channel",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )

        db_session.add(channel)
        await db_session.commit()
        await db_session.refresh(channel)

        assert channel.status == ChannelStatus.ACTIVE
        assert channel.description is None
        assert channel.youtube_channel_id is None
        assert channel.default_hashtags is None

    @pytest.mark.asyncio
    async def test_channel_youtube_id_unique(self, db_session: AsyncSession) -> None:
        """Test YouTube channel ID uniqueness constraint."""
        channel1 = Channel(
            name="Channel 1",
            youtube_channel_id="UC123456",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel1)
        await db_session.commit()

        # Try to create duplicate
        channel2 = Channel(
            name="Channel 2",
            youtube_channel_id="UC123456",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel2)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_channel_with_arrays(self, db_session: AsyncSession) -> None:
        """Test channel with array fields."""
        channel = Channel(
            name="Array Channel",
            default_hashtags=["#tech", "#ai", "#coding"],
            default_links=["https://example.com", "https://github.com"],
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )

        db_session.add(channel)
        await db_session.commit()
        await db_session.refresh(channel)

        assert len(channel.default_hashtags) == 3
        assert "#ai" in channel.default_hashtags
        assert len(channel.default_links) == 2

    @pytest.mark.asyncio
    async def test_channel_persona_relationship(self, db_session: AsyncSession) -> None:
        """Test 1:1 Channel-Persona relationship."""
        channel = Channel(
            name="Relationship Test",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)
        await db_session.flush()

        persona = Persona(
            channel_id=channel.id,
            name="Test Persona",
            tts_service=TTSService.EDGE_TTS,
        )
        db_session.add(persona)
        await db_session.commit()

        # Refresh to load relationship
        await db_session.refresh(channel, ["persona"])

        assert channel.persona is not None
        assert channel.persona.name == "Test Persona"
        assert channel.persona.channel_id == channel.id

    @pytest.mark.asyncio
    async def test_channel_cascade_delete(self, db_session: AsyncSession) -> None:
        """Test CASCADE deletion of persona and topics when channel is deleted."""
        # Create channel with persona and topic
        channel = Channel(
            name="Delete Test",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)
        await db_session.flush()

        persona = Persona(
            channel_id=channel.id,
            name="Delete Persona",
            tts_service=TTSService.EDGE_TTS,
        )
        db_session.add(persona)

        topic = Topic(
            channel_id=channel.id,
            title_original="Test Topic",
            title_normalized="test topic",
            summary="A test topic",
            source_url="https://example.com",
            categories=["tech"],
            keywords=["test"],
            entities={},
            expires_at=datetime.now(UTC),
            content_hash="abc123",
        )
        db_session.add(topic)
        await db_session.commit()

        channel_id = channel.id

        # Delete channel
        await db_session.delete(channel)
        await db_session.commit()

        # Verify persona and topic are also deleted
        persona_result = await db_session.execute(
            select(Persona).where(Persona.channel_id == channel_id)
        )
        assert persona_result.scalar_one_or_none() is None

        topic_result = await db_session.execute(select(Topic).where(Topic.channel_id == channel_id))
        assert topic_result.scalar_one_or_none() is None


class TestPersona:
    """Test Persona model."""

    @pytest.mark.asyncio
    async def test_create_persona(self, db_session: AsyncSession) -> None:
        """Test creating a persona."""
        # Create channel first
        channel = Channel(
            name="Persona Test",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)
        await db_session.flush()

        persona = Persona(
            channel_id=channel.id,
            name="AI Expert",
            tagline="Your friendly AI guide",
            description="An expert in AI and machine learning",
            expertise=["AI", "ML", "Python"],
            voice_gender="neutral",
            tts_service=TTSService.ELEVENLABS,
            voice_id="voice_123",
            voice_settings={"speed": 1.0, "pitch": 0},
            communication_style={"tone": "friendly", "length": "concise"},
            perspective={"viewpoint": "technical", "expertise_level": "advanced"},
            examples={"greeting": "Hey there, tech enthusiast!"},
        )

        db_session.add(persona)
        await db_session.commit()
        await db_session.refresh(persona)

        # Verify
        assert persona.id is not None
        assert persona.name == "AI Expert"
        assert persona.tts_service == TTSService.ELEVENLABS
        assert len(persona.expertise) == 3
        assert persona.voice_settings["speed"] == 1.0
        assert persona.communication_style["tone"] == "friendly"

    @pytest.mark.asyncio
    async def test_persona_default_tts(self, db_session: AsyncSession) -> None:
        """Test persona default TTS service."""
        channel = Channel(
            name="Default TTS",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)
        await db_session.flush()

        persona = Persona(
            channel_id=channel.id,
            name="Default Voice",
        )
        db_session.add(persona)
        await db_session.commit()
        await db_session.refresh(persona)

        assert persona.tts_service == TTSService.EDGE_TTS

    @pytest.mark.asyncio
    async def test_persona_unique_channel(self, db_session: AsyncSession) -> None:
        """Test that a channel can only have one persona."""
        channel = Channel(
            name="One Persona",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)
        await db_session.flush()

        persona1 = Persona(
            channel_id=channel.id,
            name="First Persona",
            tts_service=TTSService.EDGE_TTS,
        )
        db_session.add(persona1)
        await db_session.commit()

        # Try to add second persona
        persona2 = Persona(
            channel_id=channel.id,
            name="Second Persona",
            tts_service=TTSService.ELEVENLABS,
        )
        db_session.add(persona2)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_persona_tts_enum_values(self, db_session: AsyncSession) -> None:
        """Test all TTS service enum values."""
        assert TTSService.EDGE_TTS == "edge-tts"
        assert TTSService.ELEVENLABS == "elevenlabs"
        assert TTSService.CLOVA == "clova"

        # Test that enum is properly stored
        channel = Channel(
            name="Enum Test",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)
        await db_session.flush()

        for tts_service in TTSService:
            persona = Persona(
                channel_id=channel.id,
                name=f"Persona {tts_service.value}",
                tts_service=tts_service,
            )
            db_session.add(persona)
            await db_session.commit()
            await db_session.refresh(persona)
            assert persona.tts_service == tts_service
            await db_session.delete(persona)
            await db_session.commit()


class TestChannelStatus:
    """Test ChannelStatus enum."""

    def test_channel_status_values(self) -> None:
        """Test ChannelStatus enum values."""
        assert ChannelStatus.ACTIVE == "active"
        assert ChannelStatus.PAUSED == "paused"
        assert ChannelStatus.ARCHIVED == "archived"

        # Test all values exist
        statuses = [s.value for s in ChannelStatus]
        assert "active" in statuses
        assert "paused" in statuses
        assert "archived" in statuses
