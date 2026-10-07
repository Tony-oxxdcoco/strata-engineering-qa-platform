"""Transactional persistence. Artifacts are immutable; state changes use CAS."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, Column, Float, Integer, String, Text, create_engine, event, select, update
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


def now():
    return datetime.now(timezone.utc).isoformat()


def uid(prefix="obj"):
    return f"{prefix}_{secrets.token_hex(12)}"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Resource(Base):
    __tablename__ = "resources"
    id = Column(String(80), primary_key=True)
    kind = Column(String(30), nullable=False, index=True)
    project_id = Column(String(80), nullable=False, index=True)
    data = Column(JSON, nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(String(40), nullable=False, default=now)


class User(Base):
    __tablename__ = "users"
    id = Column(String(80), primary_key=True)
    username = Column(String(100), nullable=False, unique=True)
    password = Column(String(300), nullable=False)
    admin = Column(Integer, nullable=False, default=0)


class LoginSession(Base):
    __tablename__ = "sessions"
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(String(80), nullable=False, index=True)
    expires_at = Column(Float, nullable=False)


class Membership(Base):
    __tablename__ = "memberships"
    project_id = Column(String(80), primary_key=True)
    user_id = Column(String(80), primary_key=True)
    role = Column(String(30), nullable=False)


class Audit(Base):
    __tablename__ = "audit"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(80), nullable=False, index=True)
    event = Column(JSON, nullable=False)
    event_hash = Column(String(64), nullable=False)
    previous_hash = Column(String(64), nullable=False)


class Store:
    def __init__(self, root, database_url=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.blobs = self.root / "blobs"
        self.blobs.mkdir(exist_ok=True)
        url = database_url or f"sqlite:///{self.root / 'strata.db'}"
        self.engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30} if url.startswith("sqlite:") else {}, pool_pre_ping=True)
        if url.startswith("sqlite:"):
            @event.listens_for(self.engine, "connect")
            def configure(connection, _):
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA busy_timeout=30000")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(self.engine, expire_on_commit=False)

    def put_blob(self, content):
        sha = hashlib.sha256(content).hexdigest()
        path = self.blobs / sha
        if not path.exists():
            temp = self.blobs / f".{sha}.{secrets.token_hex(4)}"
            with open(temp, "xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp, 0o600)
            os.replace(temp, path)
        return sha

    def get_blob(self, sha):
        if not isinstance(sha,str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError("Invalid source hash")
        content = (self.blobs / sha).read_bytes()
        if hashlib.sha256(content).hexdigest() != sha:
            raise ValueError("Source integrity verification failed")
        return content

    def add(self, session, kind, project_id, data, resource_id=None):
        row = Resource(id=resource_id or uid(kind), kind=kind, project_id=project_id, data=json.loads(canonical(data)))
        session.add(row)
        session.flush()
        return row

    def list(self, session, project_id, kind):
        return list(session.scalars(select(Resource).where(Resource.project_id == project_id, Resource.kind == kind).order_by(Resource.created_at.desc())))

    def change(self, session, row, data):
        revision = row.revision
        result = session.execute(update(Resource).where(Resource.id == row.id, Resource.revision == revision).values(data=json.loads(canonical(data)), revision=revision + 1), execution_options={"synchronize_session": False})
        if result.rowcount != 1:
            raise ValueError("Resource changed concurrently; reload and retry")
        session.expire(row)

    def audit(self, session, project_id, actor, action, target, detail=None):
        # Serialize the project's chain through its resource revision, in the
        # same transaction as the business change. Competing writes retry.
        project = session.get(Resource, project_id)
        if project:
            self.change(session, project, project.data)
        previous = session.scalar(select(Audit).where(Audit.project_id == project_id).order_by(Audit.id.desc()).limit(1))
        previous_hash = previous.event_hash if previous else "0" * 64
        payload = {"at": now(), "actor": actor, "action": action, "target": target, "detail": detail or {}}
        row = Audit(project_id=project_id, event=payload, previous_hash=previous_hash, event_hash=digest({"previous": previous_hash, "event": payload}))
        session.add(row)
        return row

    def audit_chain(self, session, project_id):
        rows = list(session.scalars(select(Audit).where(Audit.project_id == project_id).order_by(Audit.id)))
        previous, valid = "0" * 64, True
        items = []
        for row in rows:
            valid = valid and row.previous_hash == previous and row.event_hash == digest({"previous": previous, "event": row.event})
            items.append({"id": row.id, **row.event, "hash": row.event_hash})
            previous = row.event_hash
        return {"valid": valid, "items": items}


def public(row):
    return {**row.data, "id": row.id, "created_at": row.created_at, "revision": row.revision}
