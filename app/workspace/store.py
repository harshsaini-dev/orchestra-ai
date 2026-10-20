"""SQLAlchemy tenant catalog; one-process SQLite transactions and hash-linked audit."""

import hashlib
import json
import secrets
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import (
    JSON,
    Column,
    Integer,
    String,
    Float,
    UniqueConstraint,
    create_engine,
    select,
    event,
)
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


def uid():
    return uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=uid)
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)


class Company(Base):
    __tablename__ = "companies"
    id = Column(String, primary_key=True, default=uid)
    name = Column(String, nullable=False)


class Membership(Base):
    __tablename__ = "memberships"
    id = Column(String, primary_key=True, default=uid)
    company = Column(String, nullable=False, index=True)
    user = Column(String, nullable=False)
    role = Column(String, nullable=False)
    __table_args__ = (UniqueConstraint("company", "user"),)


class Login(Base):
    __tablename__ = "sessions"
    token = Column(String, primary_key=True)
    user = Column(String, nullable=False)
    expires = Column(Float, nullable=False)


class Item(Base):
    __tablename__ = "items"
    id = Column(String, primary_key=True, default=uid)
    company = Column(String, nullable=False, index=True)
    kind = Column(String, nullable=False, index=True)
    data = Column(JSON, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    created = Column(String, default=now)


class Audit(Base):
    __tablename__ = "audit"
    seq = Column(Integer, primary_key=True, autoincrement=True)
    company = Column(String, nullable=False, index=True)
    body = Column(JSON, nullable=False)
    previous = Column(String, nullable=False)
    digest = Column(String, nullable=False)


def pack(row):
    return {
        "id": row.id,
        "kind": row.kind,
        "version": row.version,
        "created": row.created,
        **row.data,
    }


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return (
        salt
        + ":"
        + hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 310000).hex()
    )


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            "sqlite:///" + str(path),
            connect_args={"check_same_thread": False, "timeout": 30},
        )

        @event.listens_for(self.engine, "connect")
        def configure(connection, _):
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)
        self.lock = threading.RLock()
        self.failures = {}
        self.dense_indexes = {}
        self.dense_root = Path(path).parent / "dense"

    def dense(self, company):
        import os

        if os.getenv("ORCHESTRA_DENSE") != "1":
            return None
        with self.lock:
            if company not in self.dense_indexes:
                from .dense import DenseIndex

                self.dense_indexes[company] = DenseIndex(self.dense_root, company)
            return self.dense_indexes[company]

    def answer(self, company, question):
        from .retrieval import answer

        try:
            dense = self.dense(company)
        except Exception:
            result = answer(self.items(company, "document"), question)
            result["warning"] = "Dense model unavailable; offline BM25 + TF-IDF used."
            return result
        return answer(self.items(company, "document"), question, dense)

    @contextmanager
    def tx(self):
        with self.lock, self.Session.begin() as session:
            yield session

    def items(self, company, kind, session=None):
        if session is not None:
            return session.scalars(
                select(Item)
                .where(Item.company == company, Item.kind == kind)
                .order_by(Item.created)
            ).all()
        with self.tx() as s:
            return [pack(i) for i in self.items(company, kind, s)]

    def get(self, s, company, key, kind=None):
        item = s.scalar(select(Item).where(Item.company == company, Item.id == key))
        if not item or (kind and item.kind != kind):
            raise HTTPException(404, "Item not found in this workspace")
        return item

    def put(self, s, company, kind, data):
        item = Item(company=company, kind=kind, data=data)
        s.add(item)
        s.flush()
        return item

    def audit(self, s, company, actor, action, detail):
        last = s.scalar(
            select(Audit)
            .where(Audit.company == company)
            .order_by(Audit.seq.desc())
            .limit(1)
        )
        previous = last.digest if last else "0" * 64
        body = {"at": now(), "actor": actor, "action": action, "detail": detail}
        digest = hashlib.sha256((previous + canonical(body)).encode()).hexdigest()
        s.add(Audit(company=company, body=body, previous=previous, digest=digest))

    def verify(self, company):
        with self.tx() as s:
            rows = s.scalars(
                select(Audit).where(Audit.company == company).order_by(Audit.seq)
            ).all()
            previous = "0" * 64
            for row in rows:
                expected = hashlib.sha256(
                    (previous + canonical(row.body)).encode()
                ).hexdigest()
                if row.previous != previous or row.digest != expected:
                    return {"valid": False, "broken_at": row.seq, "count": len(rows)}
                previous = row.digest
            return {
                "valid": True,
                "count": len(rows),
                "head": previous,
                "limitation": "Detects edits against the current chain; a database administrator can rewrite the entire chain.",
            }

    def identity(self, token, company=None):
        digest = hashlib.sha256((token or "").encode()).hexdigest()
        with self.tx() as s:
            login = s.get(Login, digest)
            if not login or login.expires < time.time():
                raise HTTPException(401, "Sign in to continue")
            user = s.get(User, login.user)
            identity = {"id": user.id, "email": user.email}
            if company:
                member = s.scalar(
                    select(Membership).where(
                        Membership.company == company, Membership.user == user.id
                    )
                )
                if not member:
                    raise HTTPException(404, "Workspace not found")
                identity["role"] = member.role
            return identity
