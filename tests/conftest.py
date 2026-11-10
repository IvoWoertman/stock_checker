"""Shared test fixtures: an in-memory fake of the db module.

service.py accesses the lakehouse only through `db.fq`, `db.one`, `db.rows`,
and `db.connect`, so tests monkeypatch those to drive the business logic
without touching Databricks.
"""
import pytest


class FakeCursor:
    def __init__(self, fetchone_results=None):
        self.statements = []
        self._fetchone = list(fetchone_results or [])

    def execute(self, sql, params=None):
        self.statements.append((sql, params or []))

    def fetchone(self):
        return self._fetchone.pop(0) if self._fetchone else None

    def fetchall(self):
        return []

    def close(self):
        pass


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


class FakeDb:
    """A scriptable stand-in for the db module."""

    def __init__(self):
        self.one_results = []
        self.rows_results = []
        self.cursor = FakeCursor()
        self.connection = FakeConnection(self.cursor)
        self.connect_calls = 0

    def fq(self, table):
        return f"main.stock.{table}"

    def one(self, sql, params=None):
        return self.one_results.pop(0) if self.one_results else None

    def rows(self, sql, params=None):
        return self.rows_results.pop(0) if self.rows_results else []

    def connect(self, autocommit=True):
        self.connect_calls += 1
        return self.connection


@pytest.fixture
def fake_db(monkeypatch):
    import db as db_module

    fake = FakeDb()
    monkeypatch.setattr(db_module, "fq", fake.fq)
    monkeypatch.setattr(db_module, "one", fake.one)
    monkeypatch.setattr(db_module, "rows", fake.rows)
    monkeypatch.setattr(db_module, "connect", fake.connect)
    return fake
