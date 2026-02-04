"""Unit tests for base model mixins."""

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class TestUUIDMixin:
    """Tests for UUIDMixin."""

    def test_mixin_provides_id_attribute(self):
        """Test that UUIDMixin provides id attribute to subclass."""

        class TestModel(Base, UUIDMixin):
            __tablename__ = "test_uuid_mixin"
            name: Mapped[str] = mapped_column(String(100))

        # Check that model has id column
        assert hasattr(TestModel, "id")
        assert "id" in TestModel.__table__.columns

    def test_id_is_primary_key(self):
        """Test that id is primary key."""

        class TestModel(Base, UUIDMixin):
            __tablename__ = "test_uuid_pk"
            name: Mapped[str] = mapped_column(String(100))

        id_column = TestModel.__table__.columns["id"]
        assert id_column.primary_key is True

    def test_id_has_index(self):
        """Test that id has index."""

        class TestModel(Base, UUIDMixin):
            __tablename__ = "test_uuid_index"
            name: Mapped[str] = mapped_column(String(100))

        id_column = TestModel.__table__.columns["id"]
        assert id_column.index is True


class TestTimestampMixin:
    """Tests for TimestampMixin."""

    def test_mixin_provides_timestamp_attributes(self):
        """Test that TimestampMixin provides created_at and updated_at."""

        class TestModel(Base, TimestampMixin):
            __tablename__ = "test_timestamp_mixin"
            id: Mapped[int] = mapped_column(primary_key=True)

        assert hasattr(TestModel, "created_at")
        assert hasattr(TestModel, "updated_at")
        assert "created_at" in TestModel.__table__.columns
        assert "updated_at" in TestModel.__table__.columns

    def test_timestamps_are_not_nullable(self):
        """Test that timestamp columns are not nullable."""

        class TestModel(Base, TimestampMixin):
            __tablename__ = "test_timestamp_notnull"
            id: Mapped[int] = mapped_column(primary_key=True)

        created_at_col = TestModel.__table__.columns["created_at"]
        updated_at_col = TestModel.__table__.columns["updated_at"]
        assert created_at_col.nullable is False
        assert updated_at_col.nullable is False

    def test_timestamps_are_datetime_with_timezone(self):
        """Test that timestamp columns use DateTime with timezone."""

        class TestModel(Base, TimestampMixin):
            __tablename__ = "test_timestamp_tz"
            id: Mapped[int] = mapped_column(primary_key=True)

        created_at_col = TestModel.__table__.columns["created_at"]
        updated_at_col = TestModel.__table__.columns["updated_at"]

        # Check type is DateTime
        assert isinstance(created_at_col.type, DateTime)
        assert isinstance(updated_at_col.type, DateTime)

        # Check timezone is enabled
        assert created_at_col.type.timezone is True
        assert updated_at_col.type.timezone is True


class TestCombinedMixins:
    """Tests for using both mixins together."""

    def test_combined_mixins(self):
        """Test using both UUIDMixin and TimestampMixin."""

        class TestModel(Base, UUIDMixin, TimestampMixin):
            __tablename__ = "test_combined_mixins"
            name: Mapped[str] = mapped_column(String(100))

        # Check all columns exist
        columns = TestModel.__table__.columns
        assert "id" in columns
        assert "created_at" in columns
        assert "updated_at" in columns
        assert "name" in columns

    def test_mixin_order_independence(self):
        """Test that mixin order doesn't matter."""

        class Model1(Base, UUIDMixin, TimestampMixin):
            __tablename__ = "test_mixin_order1"
            name: Mapped[str] = mapped_column(String(100))

        class Model2(Base, TimestampMixin, UUIDMixin):
            __tablename__ = "test_mixin_order2"
            name: Mapped[str] = mapped_column(String(100))

        # Both should have same columns
        cols1 = set(Model1.__table__.columns.keys())
        cols2 = set(Model2.__table__.columns.keys())
        assert cols1 == cols2
