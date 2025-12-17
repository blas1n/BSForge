"""Tests for app.core.types module."""

from collections.abc import Callable
from typing import get_type_hints

import pytest

from app.core.types import SessionFactory


@pytest.mark.unit
def test_session_factory_import() -> None:
    """Test that SessionFactory can be imported."""
    assert SessionFactory is not None


@pytest.mark.unit
def test_session_factory_is_callable_alias() -> None:
    """Test that SessionFactory is a Callable type alias."""
    # SessionFactory should be Callable[[], AsyncSession]
    # Check that it's derived from Callable
    assert hasattr(SessionFactory, "__origin__") or SessionFactory.__class__.__name__ in (
        "_CallableGenericAlias",
        "_GenericAlias",
    )


@pytest.mark.unit
def test_session_factory_in_all_exports() -> None:
    """Test that SessionFactory is in __all__."""
    from app.core import types

    assert "SessionFactory" in types.__all__


@pytest.mark.unit
def test_session_factory_type_annotation_usage() -> None:
    """Test that SessionFactory can be used as type annotation."""

    def example_function(factory: SessionFactory) -> None:
        """Example function using SessionFactory type."""
        pass

    hints = get_type_hints(example_function)
    assert "factory" in hints


@pytest.mark.unit
def test_session_factory_callable_signature() -> None:
    """Test SessionFactory represents correct callable signature."""
    # A valid SessionFactory should be a callable that returns AsyncSession
    # We can verify by checking the type structure

    # Get the args from the callable alias
    origin = getattr(SessionFactory, "__origin__", None)
    if origin is not None:
        assert origin is Callable or str(origin) == "collections.abc.Callable"
