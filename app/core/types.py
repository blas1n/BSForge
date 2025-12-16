"""Common type definitions for the application.

This module provides shared type aliases used across multiple modules
to avoid duplication and ensure consistency.
"""

from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

# Type alias for async session factory functions
# Used by services that need to create database sessions
SessionFactory = Callable[[], AsyncSession]

__all__ = [
    "SessionFactory",
]
