"""Base model mixins and utilities.

This module provides reusable mixins for common model patterns:
- UUIDMixin: UUID primary key
- TimestampMixin: created_at and updated_at fields
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.core.database import Base


class UUIDMixin:
    """Mixin for UUID primary key.

    Provides a UUID primary key field that is automatically generated.

    Example:
        >>> class User(Base, UUIDMixin, TimestampMixin):
        ...     __tablename__ = "users"
        ...     name: Mapped[str]
    """

    @declared_attr
    @classmethod
    def id(cls) -> Mapped[uuid.UUID]:
        """UUID primary key.

        Returns:
            UUID column mapped to primary key
        """
        return mapped_column(
            primary_key=True,
            default=uuid.uuid4,
            index=True,
        )


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps.

    Provides automatic timestamp tracking for create and update operations.

    Example:
        >>> class Post(Base, UUIDMixin, TimestampMixin):
        ...     __tablename__ = "posts"
        ...     title: Mapped[str]
    """

    @declared_attr
    @classmethod
    def created_at(cls) -> Mapped[datetime]:
        """Timestamp when record was created.

        Returns:
            DateTime column with default as current UTC time
        """
        return mapped_column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        )

    @declared_attr
    @classmethod
    def updated_at(cls) -> Mapped[datetime]:
        """Timestamp when record was last updated.

        Returns:
            DateTime column that updates automatically
        """
        return mapped_column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        )


__all__ = [
    "Base",
    "UUIDMixin",
    "TimestampMixin",
]
