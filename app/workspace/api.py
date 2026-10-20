"""Authenticated workspace API. All object lookups include the membership tenant."""

import asyncio
import hashlib
import io
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Literal
from pathlib import Path
from xml.sax.saxutils import escape
from fastapi import APIRouter, HTTPException, Request, Response, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from .store import (
    User,
    Company,
    Membership,
    Login,
    Item,
    Audit,
    password_hash,
    pack,
    canonical,
)
from .ingestion import parse, profile, chunk, MAX_BYTES
from .demo import seed
from .policies import Rules
from .operations import active_policy, approve, analytics
from .engine import RunInput


class Credentials(BaseModel):
    email: str = Field(
        min_length=3, max_length=150, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    )
    password: str = Field(min_length=10, max_length=200)


class CompanyInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)


class MemberInput(BaseModel):
    email: str = Field(max_length=150)
    role: Literal["Owner", "Manager", "Analyst"]


class ReviewInput(BaseModel):
    decision: Literal["approve", "reject"]
    version: int = Field(ge=1)


class PolicyInput(BaseModel):
    rules: Rules
    source_document: str
    expected_version: int = Field(default=0, ge=0)
    rationale: str = Field(min_length=5, max_length=1000)


class DocumentEdit(BaseModel):
    version: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=1500000)


class Question(BaseModel):
    question: str = Field(min_length=2, max_length=2000)


class RowInput(BaseModel):
    version: int = Field(ge=1)
    row_index: int = Field(ge=0)
    values: dict = Field(max_length=100)


class ScheduleInput(BaseModel):
    interval_minutes: int = Field(ge=1, le=43200)
    enabled: bool = True


class AutopilotInput(BaseModel):
    enabled: bool


def make_router(store, engine):
    router = APIRouter(prefix="/v1")

    def who(request, company=None, roles=None):
        user = store.identity(request.cookies.get("orchestra_session"), company)
        if roles and user.get("role") not in roles:
            raise HTTPException(403, "Your workspace role does not permit this action")
        return user

    def set_cookie(response, token):
        response.set_cookie(
            "orchestra_session",
            token,
            httponly=True,
            samesite="strict",
            secure=os.getenv("ORCHESTRA_SECURE_COOKIE") == "1",
            max_age=43200,
            path="/",
        )

    def session_for(s, user, response):
        token = secrets.token_urlsafe(32)
        s.add(
            Login(
                token=hashlib.sha256(token.encode()).hexdigest(),
                user=user.id,
                expires=time.time() + 43200,
            )
        )
        set_cookie(response, token)
        return {"id": user.id, "email": user.email}

    @router.post("/auth/register", status_code=201)
    def register(body: Credentials, response: Response):
        if os.getenv("ORCHESTRA_DISABLE_SIGNUP") == "1":
            raise HTTPException(403, "Registration is disabled")
        with store.tx() as s:
            email = body.email.lower().strip()
            if s.scalar(select(User).where(User.email == email)):
                raise HTTPException(409, "Account already exists")
            user = User(email=email, password=password_hash(body.password))
            s.add(user)
            s.flush()
            return session_for(s, user, response)

    @router.post("/auth/login")
    def login(body: Credentials, response: Response):
        key = body.email.lower().strip()
        with store.tx() as s:
            count, until = store.failures.get(key, (0, 0))
            if until > time.time() and count >= 5:
                raise HTTPException(429, "Too many attempts; retry in 5 minutes")
            if until <= time.time():
                count = 0
            user = s.scalar(select(User).where(User.email == key))
            stored = user.password if user else password_hash("nonexistent-user")
            valid = secrets.compare_digest(
                password_hash(body.password, stored.split(":")[0]), stored
            )
            if not user or not valid:
                store.failures[key] = (count + 1, time.time() + 300)
                raise HTTPException(401, "Invalid email or password")
            store.failures.pop(key, None)
            return session_for(s, user, response)

    @router.post("/auth/logout")
    def logout(request: Request, response: Response):
        token = request.cookies.get("orchestra_session", "")
        with store.tx() as s:
            row = s.get(Login, hashlib.sha256(token.encode()).hexdigest())
            if row:
                s.delete(row)
        response.delete_cookie("orchestra_session", path="/")
        return {"signed_out": True}

    @router.get("/me")
    def me(request: Request):
        return who(request)

    @router.get("/companies")
    def companies(request: Request):
        user = who(request)
        with store.tx() as s:
            return [
                {"id": c.id, "name": c.name, "role": m.role}
                for c, m in s.execute(
                    select(Company, Membership)
                    .join(Membership, Company.id == Membership.company)
                    .where(Membership.user == user["id"])
                )
            ]

    @router.post("/companies", status_code=201)
    def company_create(body: CompanyInput, request: Request):
        user = who(request)
        with store.tx() as s:
            c = Company(name=body.name.strip())
            s.add(c)
            s.flush()
            s.add(Membership(company=c.id, user=user["id"], role="Owner"))
            store.audit(s, c.id, user["id"], "company.created", {"name": c.name})
            return {"id": c.id, "name": c.name, "role": "Owner"}

    @router.get("/companies/{company}/members")
    def members(company: str, request: Request):
        who(request, company, ["Owner"])
        with store.tx() as s:
            return [
                {"email": u.email, "role": m.role}
                for u, m in s.execute(
                    select(User, Membership)
                    .join(Membership, User.id == Membership.user)
                    .where(Membership.company == company)
                )
            ]

    @router.post("/companies/{company}/members")
    def member_add(company: str, body: MemberInput, request: Request):
        actor = who(request, company, ["Owner"])
        with store.tx() as s:
            user = s.scalar(
                select(User).where(User.email == body.email.lower().strip())
            )
            if not user:
                raise HTTPException(404, "Ask this person to register an account first")
            member = s.scalar(
                select(Membership).where(
                    Membership.company == company, Membership.user == user.id
                )
            )
            if member:
                owners = s.scalars(
                    select(Membership).where(
                        Membership.company == company, Membership.role == "Owner"
                    )
                ).all()
                if member.role == "Owner" and body.role != "Owner" and len(owners) == 1:
                    raise HTTPException(409, "Keep at least one Owner")
                member.role = body.role
            else:
                s.add(Membership(company=company, user=user.id, role=body.role))
            store.audit(
                s,
                company,
                actor["id"],
                "membership.changed",
                {"user": user.id, "role": body.role},
            )
            return {"email": user.email, "role": body.role}

    @router.post("/companies/{company}/demo")
    def demo(company: str, request: Request):
        user = who(request, company, ["Owner", "Manager"])
        with store.tx() as s:
            return seed(store, s, company, user["id"])

    @router.get("/companies/{company}/overview")
    def overview(company: str, request: Request):
        who(request, company)
        issues = [i for i in store.items(company, "issue") if i["status"] == "open"]
        datasets = store.items(company, "dataset")
        return {
            "datasets": len(datasets),
            "rows": sum(len(d["rows"]) for d in datasets),
            "documents": len(store.items(company, "document")),
            "open_issues": len(issues),
            "health": max(
                0, 100 - sum(8 if i["severity"] == "high" else 3 for i in issues)
            )
            if store.items(company, "issue")
            else None,
            "health_note": "Run a scan first. Score = max(0, 100 − 8×high − 3×other detected conditions). Draft POs and escalations do not close conditions.",
            "sales": analytics(datasets),
            "notifications": store.items(company, "notification")[-10:],
        }

    @router.get("/companies/{company}/datasets")
    def datasets(company: str, request: Request):
        who(request, company)
        return [
            {k: v for k, v in d.items() if k != "rows"}
            for d in store.items(company, "dataset")
        ]

    @router.get("/companies/{company}/datasets/{key}")
    def dataset(company: str, key: str, request: Request, offset: int = 0):
        who(request, company)
        if offset < 0:
            raise HTTPException(400, "Invalid offset")
        with store.tx() as s:
            d = pack(store.get(s, company, key, "dataset"))
            d["total_rows"] = len(d["rows"])
            d["rows"] = d["rows"][offset : offset + 100]
            d["offset"] = offset
            return d

    @router.post("/companies/{company}/datasets/{key}/record")
    def edit_record(company: str, key: str, body: RowInput, request: Request):
        actor = who(request, company, ["Owner", "Manager"])
        with store.tx() as s:
            d = store.get(s, company, key, "dataset")
            if d.version != body.version:
                raise HTTPException(409, "Dataset changed; refresh first")
            rows = [dict(r) for r in d.data["rows"]]
            if body.row_index >= len(rows):
                raise HTTPException(404, "Row not found")
            before = dict(rows[body.row_index])
            if set(body.values) - set(before):
                raise HTTPException(400, "Cannot add unknown columns")
            if any(
                not isinstance(v, (str, int, float, bool, type(None)))
                or len(str(v)) > 5000
                for v in body.values.values()
            ):
                raise HTTPException(400, "Use scalar cell values below 5000 characters")
            import math

            if any(
                isinstance(v, float) and not math.isfinite(v)
                for v in body.values.values()
            ):
                raise HTTPException(400, "Numbers must be finite")
            rows[body.row_index].update(body.values)
            d.data = {**d.data, "rows": rows, "profile": profile(rows)}
            d.version += 1
            store.audit(
                s,
                company,
                actor["id"],
                "record.edited",
                {
                    "dataset": key,
                    "row": body.row_index,
                    "before": before,
                    "after": rows[body.row_index],
                },
            )
            return {"version": d.version, "record": rows[body.row_index]}

    @router.post("/companies/{company}/upload", status_code=201)
    async def upload(
        company: str,
        request: Request,
        file: UploadFile = File(...),
        category: str = Form("other"),
    ):
        actor = who(request, company, ["Owner", "Manager"])
        if category not in {
            "sales",
            "inventory",
            "customers",
            "refunds",
            "invoices",
            "leave",
            "other",
        }:
            raise HTTPException(400, "Unknown dataset category")
        raw = await file.read(MAX_BYTES + 1)
        name = Path(file.filename or "upload").name[:200]
        parsed = await asyncio.to_thread(parse, name, raw)
        with store.tx() as s:
            item = store.put(
                s,
                company,
                "dataset" if "rows" in parsed else "document",
                {
                    "name": name,
                    **parsed,
                    **(
                        {"category": category} if "rows" in parsed else {"active": True}
                    ),
                },
            )
            store.audit(
                s,
                company,
                actor["id"],
                "file.uploaded",
                {
                    "id": item.id,
                    "name": name,
                    "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                },
            )
            return {
                "id": item.id,
                "kind": item.kind,
                "name": name,
                "profile": parsed.get("profile"),
                "chunks": len(parsed.get("chunks", [])),
            }

    @router.get("/companies/{company}/documents")
    def documents(company: str, request: Request):
        who(request, company)
        return [
            {k: v for k, v in d.items() if k not in {"pages", "chunks"}}
            | {
                "chunk_count": len(d["chunks"]),
                "injection_flags": sum(c["injection_flag"] for c in d["chunks"]),
            }
            for d in store.items(company, "document")
        ]

    @router.get("/companies/{company}/documents/{key}")
    def document(company: str, key: str, request: Request):
        who(request, company)
        with store.tx() as s:
            return pack(store.get(s, company, key, "document"))

    @router.post("/companies/{company}/documents/{key}/edit")
    def document_edit(company: str, key: str, body: DocumentEdit, request: Request):
        actor = who(request, company, ["Owner", "Manager"])
        with store.tx() as s:
            doc = store.get(s, company, key, "document")
            if doc.version != body.version:
                raise HTTPException(409, "Document changed; refresh before saving")
            store.put(
                s,
                company,
                "document_revision",
                {"document_id": key, "snapshot": pack(doc)},
            )
            pages = [{"page": None, "text": body.text}]
            doc.data = {
                **doc.data,
                "pages": pages,
                "chunks": chunk(pages),
                "review_date": datetime.now(timezone.utc).date().isoformat(),
            }
            doc.version += 1
            store.audit(
                s,
                company,
                actor["id"],
                "document.edited",
                {"id": key, "version": doc.version},
            )
            return {
                "id": key,
                "version": doc.version,
                "chunks": len(doc.data["chunks"]),
            }

    @router.get("/companies/{company}/documents/{key}/rule-draft")
    def rule_draft(company: str, key: str, request: Request):
        who(request, company)
        from .policies import extract_supported

        with store.tx() as s:
            doc = store.get(s, company, key, "document")
            return {
                "document_id": key,
                "version": doc.version,
                **extract_supported(" ".join(p["text"] for p in doc.data["pages"])),
            }

    @router.post("/companies/{company}/documents/{key}/reindex")
    def reindex(company: str, key: str, request: Request):
        actor = who(request, company, ["Owner", "Manager"])
        with store.tx() as s:
            d = store.get(s, company, key, "document")
            d.data = {**d.data, "chunks": chunk(d.data["pages"])}
            d.version += 1
            store.audit(
                s,
                company,
                actor["id"],
                "document.reindexed",
                {"id": key, "version": d.version},
            )
            return {"chunks": len(d.data["chunks"]), "version": d.version}

    @router.post("/companies/{company}/ask")
    def ask(company: str, body: Question, request: Request):
        who(request, company)
        q = body.question.lower()
        if any(
            t in q for t in ["total sales", "sales trend", "monthly sales", "revenue"]
        ):
            return {
                "mode": "allowlisted sales aggregation",
                "analytics": analytics(store.items(company, "dataset")),
                "answer": "Sales values are aggregated from your workspace records; inspect the chart and data-quality note.",
                "citations": [],
                "abstained": False,
            }
        return store.answer(company, body.question)

    @router.get("/companies/{company}/policies")
    def policies(company: str, request: Request):
        who(request, company)
        result = store.items(company, "policy")
        docs = {d["id"]: d for d in store.items(company, "document")}
        for p in result:
            d = docs.get(p["source_document"])
            p["source_stale"] = not d or d["version"] != p["source_version"]
            p["review_overdue"] = bool(
                d
                and d.get("review_date")
                and (
                    datetime.now(timezone.utc).date()
                    - datetime.fromisoformat(d["review_date"]).date()
                ).days
                > 365
            )
            p["conflicts"] = [
                other["id"]
                for other in result
                if other["id"] != p["id"]
                and other.get("priority", 100) == p.get("priority", 100)
                and other["rules"] != p["rules"]
            ]
        return result

    @router.post("/companies/{company}/policies")
    def publish(company: str, body: PolicyInput, request: Request):
        actor = who(request, company, ["Owner"])
        with store.tx() as s:
            doc = store.get(s, company, body.source_document, "document")
            values = body.rules.model_dump()
            policies = store.items(company, "policy", s)
            p = active_policy(store, s, company) if policies else None
            if (p.version if p else 0) != body.expected_version:
                raise HTTPException(409, "Policy changed; refresh before publishing")
            if p:
                store.put(
                    s, company, "policy_revision", {"policy": p.id, "snapshot": pack(p)}
                )
                p.data = {
                    **p.data,
                    "rules": values,
                    "source_document": doc.id,
                    "source_version": doc.version,
                    "rationale": body.rationale,
                    "published_by": actor["id"],
                }
                p.version += 1
            else:
                p = store.put(
                    s,
                    company,
                    "policy",
                    {
                        "name": "Operating policy",
                        "rules": values,
                        "source_document": doc.id,
                        "source_version": doc.version,
                        "rationale": body.rationale,
                        "priority": 100,
                        "published_by": actor["id"],
                    },
                )
            store.audit(
                s,
                company,
                actor["id"],
                "policy.published",
                {
                    "policy": p.id,
                    "version": p.version,
                    "rules": values,
                    "source": doc.id,
                    "rationale": body.rationale,
                },
            )
            return pack(p)

    @router.get("/companies/{company}/policy-history")
    def history(company: str, request: Request):
        who(request, company)
        return store.items(company, "policy_revision")

    @router.get("/companies/{company}/issues")
    def issues(company: str, request: Request):
        who(request, company)
        return store.items(company, "issue")

    @router.post("/companies/{company}/issues/{key}/review")
    def review(company: str, key: str, body: ReviewInput, request: Request):
        user = who(request, company, ["Owner", "Manager"])
        return approve(store, company, user["id"], key, body.decision, body.version)

    @router.post("/companies/{company}/autopilot")
    def autopilot(company: str, body: AutopilotInput, request: Request):
        user = who(request, company, ["Owner"])
        with store.tx() as s:
            configs = store.items(company, "config", s)
            if configs:
                configs[0].data = {"autopilot": body.enabled}
            else:
                store.put(s, company, "config", {"autopilot": body.enabled})
            store.audit(
                s,
                company,
                user["id"],
                "autopilot.configured",
                {"enabled": body.enabled, "allowlist": ["trim"]},
            )
        outcomes = []
        if body.enabled:
            for issue in store.items(company, "issue"):
                if issue["status"] == "open" and issue["action"] == "trim":
                    try:
                        outcomes.append(
                            approve(
                                store,
                                company,
                                user["id"],
                                issue["id"],
                                "approve",
                                issue["version"],
                                True,
                            )
                        )
                    except HTTPException as error:
                        outcomes.append({"skipped": error.detail})
        return {
            "enabled": body.enabled,
            "allowlist": ["trim"],
            "results": outcomes,
            "mode": "Run-on-enable; enable again after a new scan to apply further whitespace fixes",
        }

    @router.post("/companies/{company}/runs", status_code=202)
    def run(company: str, body: RunInput, request: Request):
        user = who(request, company)
        if (
            body.workflow in {"scan", "refund", "inventory"}
            and user["role"] == "Analyst"
        ):
            raise HTTPException(
                403, "A Manager or Owner must create operational proposals"
            )
        if body.workflow == "simulate":
            body.proposed = Rules.model_validate(body.proposed).model_dump()
        return engine.submit(company, user["id"], body)

    @router.get("/companies/{company}/runs")
    def runs(company: str, request: Request):
        who(request, company)
        return [
            {k: v for k, v in r.items() if k != "result"}
            for r in store.items(company, "run")
        ][-100:][::-1]

    @router.get("/companies/{company}/runs/{key}")
    def run_get(company: str, key: str, request: Request):
        who(request, company)
        with store.tx() as s:
            return pack(store.get(s, company, key, "run"))

    @router.get("/companies/{company}/runs/{key}/events")
    async def events(company: str, key: str, request: Request, after: int = 0):
        who(request, company)
        with store.tx() as s:
            store.get(s, company, key, "run")
        try:
            cursor = max(after, int(request.headers.get("last-event-id", "0")))
        except ValueError:
            raise HTTPException(400, "Invalid event cursor")

        async def stream():
            nonlocal cursor
            while not await request.is_disconnected():
                who(request, company)
                with store.tx() as s:
                    run = store.get(s, company, key, "run")
                    terminal = run.data["status"] in {"done", "error", "interrupted"}
                    records = [
                        pack(e)
                        for e in store.items(company, "event", s)
                        if e.data["run_id"] == key and e.data["seq"] > cursor
                    ]
                for e in records:
                    cursor = e["seq"]
                    yield f"id: {cursor}\ndata: {canonical(e)}\n\n"
                if terminal:
                    break
                yield ": heartbeat\n\n"
                await asyncio.sleep(0.2)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @router.get("/companies/{company}/runs/{key}/replay")
    def replay(company: str, key: str, request: Request):
        who(request, company)
        with store.tx() as s:
            store.get(s, company, key, "run")
        return [e for e in store.items(company, "event") if e["run_id"] == key]

    @router.get("/companies/{company}/reports")
    def reports(company: str, request: Request):
        who(request, company)
        return store.items(company, "report")[::-1]

    @router.get("/companies/{company}/drafts")
    def drafts(company: str, request: Request):
        who(request, company)
        return store.items(company, "draft")

    @router.get("/companies/{company}/reports/{key}/pdf")
    def report_pdf(company: str, key: str, request: Request):
        who(request, company)
        with store.tx() as s:
            r = pack(store.get(s, company, key, "report"))
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet

        buffer = io.BytesIO()
        styles = getSampleStyleSheet()
        story = [
            Paragraph(escape(r["title"]), styles["Title"]),
            Spacer(1, 16),
            Paragraph(
                "OrchestraAI · " + escape(r["status"]) + " · " + escape(r["created"]),
                styles["Normal"],
            ),
        ]
        for field, value in r["content"].items():
            text = canonical(value) if isinstance(value, (list, dict)) else str(value)
            # Wrap long machine identifiers and avoid markup injection.
            story += [
                Spacer(1, 10),
                Paragraph(escape(field.replace("_", " ").title()), styles["Heading3"]),
                Paragraph(escape(text), styles["BodyText"]),
            ]
        SimpleDocTemplate(buffer).build(story)
        return Response(
            buffer.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="report-{key}.pdf"'},
        )

    @router.get("/companies/{company}/handbook.pdf")
    def handbook_pdf(company: str, request: Request):
        who(request, company)
        from .demo import SECTIONS
        from reportlab.platypus import SimpleDocTemplate, Paragraph, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet

        buffer = io.BytesIO()
        styles = getSampleStyleSheet()
        story = []
        for i, (title, text) in enumerate(SECTIONS):
            if i:
                story.append(PageBreak())
            story.extend(
                [
                    Paragraph(
                        "Synthetic SME handbook / " + str(i + 1), styles["Normal"]
                    ),
                    Paragraph(title, styles["Title"]),
                    Paragraph(escape(text), styles["BodyText"]),
                ]
            )
        SimpleDocTemplate(buffer).build(story)
        return Response(
            buffer.getvalue(),
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="synthetic-sme-handbook.pdf"'
            },
        )

    @router.get("/companies/{company}/audit")
    def audit(company: str, request: Request):
        who(request, company)
        with store.tx() as s:
            return [
                {"seq": r.seq, **r.body, "previous": r.previous, "hash": r.digest}
                for r in s.scalars(
                    select(Audit)
                    .where(Audit.company == company)
                    .order_by(Audit.seq.desc())
                    .limit(300)
                )
            ]

    @router.get("/companies/{company}/audit/verify")
    def verify(company: str, request: Request):
        who(request, company)
        return store.verify(company)

    @router.post("/companies/{company}/schedules")
    def schedule(company: str, body: ScheduleInput, request: Request):
        actor = who(request, company, ["Owner", "Manager"])
        with store.tx() as s:
            value = {
                "workflow": "weekly",
                **body.model_dump(),
                "actor": actor["id"],
                "next_at": time.time() + body.interval_minutes * 60,
            }
            existing = store.items(company, "schedule", s)
            if existing:
                existing[0].data = value
                r = existing[0]
            else:
                r = store.put(s, company, "schedule", value)
            store.audit(s, company, actor["id"], "schedule.saved", value)
            return pack(r)

    @router.get("/companies/{company}/schedules")
    def schedules(company: str, request: Request):
        who(request, company)
        return store.items(company, "schedule")

    @router.post("/companies/{company}/evaluate")
    def evaluate(company: str, request: Request):
        user = who(request, company)
        from .evaluation import evaluate_workspace

        result = evaluate_workspace(store, company)
        with store.tx() as s:
            r = store.put(s, company, "evaluation", result)
            store.audit(
                s, company, user["id"], "evaluation.completed", {"evaluation": r.id}
            )
            return pack(r)

    @router.get("/companies/{company}/evaluations")
    def evaluations(company: str, request: Request):
        who(request, company)
        return store.items(company, "evaluation")[::-1]

    return router


def tick_schedules(store, engine):
    """Coalesce missed intervals; read-only report jobs only. Never replay mutations."""
    due = []
    with store.tx() as s:
        for row in s.scalars(select(Item).where(Item.kind == "schedule")).all():
            if row.data["enabled"] and row.data["next_at"] <= time.time():
                due.append((row.company, row.data["actor"], row.id))
                row.data = {
                    **row.data,
                    "next_at": time.time() + row.data["interval_minutes"] * 60,
                    "last_attempt": time.time(),
                }
    for company, actor, key in due:
        try:
            # Membership must still exist; revoked members cannot schedule jobs.
            with store.tx() as s:
                membership = s.scalar(
                    select(Membership).where(
                        Membership.company == company, Membership.user == actor
                    )
                )
                if not membership or membership.role not in {"Owner", "Manager"}:
                    continue
            result = engine.submit(company, actor, RunInput(workflow="weekly"))
            with store.tx() as s:
                r = store.get(s, company, key, "schedule")
                r.data = {**r.data, "last_run": result["id"]}
        except HTTPException:
            with store.tx() as s:
                r = store.get(s, company, key, "schedule")
                r.data = {
                    **r.data,
                    "last_error": "Queue full; next interval will retry",
                }
