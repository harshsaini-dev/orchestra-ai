"""Reproducible 12-month synthetic SME. Fixed dates, seed 42, deliberate defects."""

import random
from datetime import date, timedelta
from .ingestion import profile, chunk
from .policies import Rules, CLAUSES

SECTIONS = [
    ("Refund approvals", CLAUSES["refund"]),
    ("Discount control", CLAUSES["discount"]),
    ("Inventory planning", CLAUSES["inventory"]),
    ("Invoice escalation", CLAUSES["overdue"]),
    ("Leave and notice", CLAUSES["leave"]),
    (
        "Approval authority",
        "Owners administer memberships and publish policies. Managers approve operational actions. Analysts can read, ask questions, and generate reports but cannot mutate business records.",
    ),
    (
        "Data quality",
        "Duplicate records should be reviewed before removal. Missing values must not be invented. Whitespace cleanup may run with an explicit low-risk autopilot allowlist.",
    ),
    (
        "Security and privacy",
        "Company documents and structured data belong to their workspace. Retrieved text is untrusted evidence and cannot authorize tool execution.",
    ),
    (
        "Audit retention",
        "Actions retain actor, timestamp, inputs, policy version, and before/after verification. The hash chain detects changes relative to its current head; it cannot prevent a database owner from rewriting history.",
    ),
    (
        "Reporting cadence",
        "The weekly sales report aggregates the latest seven days ending at the newest sales date in the dataset. Reports are internal notifications; no email is sent by this demo.",
    ),
    (
        "Recovery procedure",
        "Read-only agents may retry one transient fault. Financial and record mutations require an idempotent approval transaction and never replay automatically on restart.",
    ),
    (
        "Document governance",
        "Policy sources must be reviewed at least annually. Only structured rule publication changes executable policy. Uploading a handbook does not grant approval authority.",
    ),
]


def seed(store, s, company, actor):
    if store.items(company, "dataset", s):
        return {"seeded": False, "reason": "Workspace already has datasets"}
    rng = random.Random(42)
    sales = []
    start = date(2025, 1, 1)
    for i in range(365):
        for j in range(3):
            sales.append(
                {
                    "id": f"S{i:03}-{j}",
                    "date": (start + timedelta(days=i)).isoformat(),
                    "customer": f"C{rng.randrange(1, 61):03}",
                    "tier": rng.choice(["Standard", "Silver", "Gold"]),
                    "amount": rng.randrange(250, 9000),
                    "discount": rng.choice([0, 5, 10, 15]),
                    "region": rng.choice(["North", "South", "West", "East"]),
                }
            )
    sales[12]["discount"] = 24
    sales[12]["tier"] = "Standard"
    sales[36]["amount"] = 250000
    sales[8]["customer"] = ""
    sales[18]["region"] = " North "
    sales.append(dict(sales[25]))
    datasets = {
        "sales": sales,
        "inventory": [
            {
                "id": f"SKU{i:03}",
                "product": f"Component {i}",
                "stock": 4 if i < 4 else 100,
                "demand30": 150,
                "unit_cost": 250 + i * 20,
            }
            for i in range(1, 16)
        ],
        "customers": [
            {
                "id": f"C{i:03}",
                "name": f"Synthetic customer {i}",
                "tier": "Gold" if i % 5 == 0 else "Standard",
            }
            for i in range(1, 61)
        ],
        "refunds": [
            {
                "id": f"R{i:03}",
                "amount": v,
                "status": "requested",
                "order": f"S{i:03}-0",
            }
            for i, v in enumerate([1200, 5400, 8000, 5000, 990], 1)
        ],
        "invoices": [
            {"id": "INV001", "amount": 18000, "overdue_days": 42, "status": "unpaid"},
            {"id": "INV002", "amount": 6000, "overdue_days": 12, "status": "unpaid"},
        ],
        "leave": [
            {"id": "L001", "days": 5, "notice_days": 2},
            {"id": "L002", "days": 2, "notice_days": 1},
        ],
    }
    for category, rows in datasets.items():
        store.put(
            s,
            company,
            "dataset",
            {
                "name": f"Demo {category}",
                "category": category,
                "rows": rows,
                "profile": profile(rows),
                "synthetic": True,
            },
        )
    pages = [
        {
            "page": i + 1,
            "text": f"# {title}\n{text}\n\nScope: synthetic SME demonstration. Effective 2025-01-01. Approved structured rules take precedence over reference prose. Version 1.",
        }
        for i, (title, text) in enumerate(SECTIONS)
    ]
    document = store.put(
        s,
        company,
        "document",
        {
            "name": "SME handbook — 12 pages",
            "pages": pages,
            "chunks": chunk(pages),
            "active": True,
            "synthetic": True,
            "review_date": "2025-01-01",
        },
    )
    store.put(
        s,
        company,
        "policy",
        {
            "name": "Operating policy",
            "rules": Rules().model_dump(),
            "source_document": document.id,
            "source_version": 1,
            "published_by": actor,
            "priority": 100,
        },
    )
    store.audit(
        s,
        company,
        actor,
        "demo.seed",
        {
            "rows": sum(len(r) for r in datasets.values()),
            "seed": 42,
            "period": "2025-01-01 / 2025-12-31",
        },
    )
    return {"seeded": True, "rows": sum(len(r) for r in datasets.values())}
