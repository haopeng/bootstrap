"""Tiny sqlite document store: every product persists jobs and results here."""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from typing import Any, Iterable, Optional

DEFAULT_PATH = os.environ.get("VENTURES_DB", os.path.join(os.path.dirname(__file__), "..", "ventures.db"))


class Store:
    def __init__(self, path: str = DEFAULT_PATH) -> None:
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS jobs (
                 id TEXT PRIMARY KEY, product TEXT, kind TEXT, created REAL,
                 payload TEXT, result TEXT, status TEXT)"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS events (
                 id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, ts REAL, kind TEXT, data TEXT)"""
        )
        self.conn.commit()

    def new_job(self, product: str, kind: str, payload: Any) -> str:
        jid = uuid.uuid4().hex[:12]
        self.conn.execute(
            "INSERT INTO jobs VALUES (?,?,?,?,?,?,?)",
            (jid, product, kind, time.time(), json.dumps(payload, default=str), None, "pending"),
        )
        self.conn.commit()
        return jid

    def finish(self, jid: str, result: Any, status: str = "done") -> None:
        self.conn.execute(
            "UPDATE jobs SET result=?, status=? WHERE id=?", (json.dumps(result, default=str), status, jid)
        )
        self.conn.commit()

    def get(self, jid: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "product": row[1], "kind": row[2], "created": row[3],
            "payload": json.loads(row[4]), "result": json.loads(row[5]) if row[5] else None, "status": row[6],
        }

    def log(self, jid: str, kind: str, data: Any = None) -> None:
        self.conn.execute(
            "INSERT INTO events (job_id, ts, kind, data) VALUES (?,?,?,?)",
            (jid, time.time(), kind, json.dumps(data, default=str)),
        )
        self.conn.commit()

    def events(self, jid: str) -> Iterable[dict]:
        for row in self.conn.execute("SELECT ts, kind, data FROM events WHERE job_id=? ORDER BY id", (jid,)):
            yield {"ts": row[0], "kind": row[1], "data": json.loads(row[2]) if row[2] else None}

    def recent(self, product: Optional[str] = None, limit: int = 20) -> list[dict]:
        q = "SELECT id FROM jobs" + (" WHERE product=?" if product else "") + " ORDER BY created DESC LIMIT ?"
        args = (product, limit) if product else (limit,)
        return [self.get(r[0]) for r in self.conn.execute(q, args)]
