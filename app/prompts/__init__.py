"""Prompt management system.

This module provides centralized prompt management with:
- Template-based prompts (Jinja2)
- Version control for prompts
- Easy modification without code changes
- Type-safe prompt rendering
"""

from app.prompts.manager import PromptManager, PromptTemplate

__all__ = ["PromptManager", "PromptTemplate"]
