from __future__ import annotations

import re
from typing import Any

import psycopg
from psycopg import sql


class CompatibleRow(dict):
    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


def row_factory(cursor):
    names = [column.name for column in cursor.description]

    def make_row(values):
        return CompatibleRow(zip(names, values))

    return make_row


def adapt_query(query: str) -> str:
    query = query.replace("COLLATE NOCASE", "")
    query = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", query, flags=re.I)
    if query.lstrip().upper().startswith("INSERT INTO") and "ON CONFLICT" not in query.upper():
        query = query.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return query.replace("?", "%s")


class Connection:
    def __init__(self, url: str):
        self._connection = psycopg.connect(url, row_factory=row_factory)

    def execute(self, query: str, params: Any = ()):
        return self._connection.execute(adapt_query(query), params)

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            statement = statement.strip()
            if statement and not statement.upper().startswith("PRAGMA"):
                self.execute(statement)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            self._connection.rollback()
        else:
            self._connection.commit()
        self._connection.close()