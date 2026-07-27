from enum import Enum
from typing import Optional, Type, TypeVar

import sqlalchemy as sa
from sqlalchemy import TypeDecorator
from sqlalchemy.dialects import postgresql

E = TypeVar("E", bound=Enum)


class EnumByValue(TypeDecorator):
    """
    Stores a Python Enum by .value (not .name) using a native PostgreSQL ENUM column.
    Falls back to VARCHAR on other databases (e.g. SQLite in tests).
    """

    cache_ok = True
    impl = sa.String

    def __init__(self, enum_class: Type[E], pg_name: str) -> None:
        super().__init__(100)
        self._enum_class = enum_class
        self._pg_name = pg_name

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(
                postgresql.ENUM(
                    *[e.value for e in self._enum_class],
                    name=self._pg_name,
                    create_type=False,
                )
            )
        return dialect.type_descriptor(sa.String(100))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, self._enum_class):
            return value.value
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return self._enum_class(value)
