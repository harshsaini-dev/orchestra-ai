"""Explicit decision tables. Scores are rule outcomes, never confidence probabilities."""

from pydantic import BaseModel, Field, ConfigDict


class Rules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refund_threshold: float = Field(default=5000, ge=0, le=10000000)
    discount_cap: float = Field(default=15, ge=0, le=100)
    reorder_ratio: float = Field(default=0.2, ge=0, le=2)
    overdue_days: int = Field(default=30, ge=1, le=365)
    leave_days: int = Field(default=3, ge=0, le=100)
    notice_days: int = Field(default=7, ge=0, le=365)


CLAUSES = {
    "refund": "Refunds above INR 5000 require manager approval. All payments in this prototype are simulated.",
    "discount": "Discounts must not exceed 15 percent unless the customer tier is Gold.",
    "inventory": "Create a purchase order draft when stock falls below 20 percent of forecast demand for the next 30 days. A draft does not replenish stock.",
    "overdue": "Invoices overdue by more than 30 days must be escalated to a manager.",
    "leave": "Leave longer than 3 days requires at least 7 days advance notice.",
}


def decide(kind, row, rules):
    r = Rules.model_validate(rules)

    def numeric(key, default=0):
        import math

        value = float(row.get(key, default))
        if not math.isfinite(value) or value < 0:
            raise ValueError("Rule inputs must be finite non-negative numbers")
        return value

    if kind == "refund":
        flagged = numeric("amount") > r.refund_threshold
        outcome = "manager_approval" if flagged else "eligible"
        used = {"refund_threshold": r.refund_threshold}
    elif kind == "discount":
        flagged = numeric("discount") > r.discount_cap and row.get("tier") != "Gold"
        outcome = "violation" if flagged else "compliant"
        used = {"discount_cap": r.discount_cap, "gold_exception": True}
    elif kind == "inventory":
        flagged = numeric("stock") < r.reorder_ratio * numeric("demand30")
        outcome = "purchase_order_draft" if flagged else "sufficient"
        used = {"reorder_ratio": r.reorder_ratio}
    elif kind == "overdue":
        flagged = numeric("overdue_days") > r.overdue_days
        outcome = "escalate" if flagged else "within_sla"
        used = {"overdue_days": r.overdue_days}
    elif kind == "leave":
        flagged = (
            numeric("days") > r.leave_days and numeric("notice_days") < r.notice_days
        )
        outcome = "insufficient_notice" if flagged else "eligible"
        used = {"leave_days": r.leave_days, "notice_days": r.notice_days}
    else:
        raise ValueError("Unsupported rule category")
    return {
        "category": kind,
        "inputs": row,
        "rule_values": used,
        "outcome": outcome,
        "flagged": flagged,
        "clause": explain(kind, r),
    }


def explain(kind, r):
    return {
        "refund": f"Refunds above INR {r.refund_threshold:g} require manager approval.",
        "discount": f"Discounts above {r.discount_cap:g}% violate policy unless the customer tier is Gold.",
        "inventory": f"Stock below {r.reorder_ratio * 100:g}% of 30-day demand requires a purchase order draft.",
        "overdue": f"Invoices overdue more than {r.overdue_days} days require escalation.",
        "leave": f"Leave longer than {r.leave_days} days requires at least {r.notice_days} days notice.",
    }[kind]


def simulate(datasets, current, proposed):
    changes = []
    checked = 0
    amount = 0
    for dataset in datasets:
        kind = {
            "sales": "discount",
            "refunds": "refund",
            "inventory": "inventory",
            "invoices": "overdue",
            "leave": "leave",
        }.get(dataset["category"])
        if not kind:
            continue
        for row in dataset["rows"]:
            checked += 1
            before = decide(kind, row, current)
            after = decide(kind, row, proposed)
            if before["outcome"] != after["outcome"]:
                changes.append(
                    {
                        "dataset": dataset["name"],
                        "record": row.get("id"),
                        "before": before["outcome"],
                        "after": after["outcome"],
                        "amount": float(row.get("amount", 0)),
                    }
                )
                amount += float(row.get("amount", 0))
    return {
        "records_checked": checked,
        "decision_flips": len(changes),
        "affected_amount": round(amount, 2),
        "changes": changes,
        "meaning": "Affected amount is record value, not savings or recovered revenue.",
    }


def extract_supported(text):
    """Conservative patterns produce reviewable drafts, never executable authority."""
    import re

    patterns = {
        "refund_threshold": r"refunds?\s+(?:above|over)\s+(?:INR\s*|Rs\.?\s*)?([\d,]+(?:\.\d+)?)",
        "discount_cap": r"discounts?\s+(?:must not exceed|cap(?:ped)? (?:at|is))\s+([\d.]+)\s*(?:percent|%)",
        "reorder_ratio": r"stock\s+falls?\s+below\s+([\d.]+)\s*(?:percent|%)",
        "overdue_days": r"overdue\s+(?:by\s+)?(?:more than|over)\s+(\d+)\s+days",
        "leave_days": r"leave\s+longer than\s+(\d+)\s+days",
        "notice_days": r"(?:at least|requires?)\s+(\d+)\s+days\s+(?:advance\s+)?notice",
    }
    found = {}
    evidence = {}
    conflicts = []
    for key, pattern in patterns.items():
        matches = list(re.finditer(pattern, text, re.I))
        values = []
        for match in matches:
            value = float(match.group(1).replace(",", ""))
            if key == "reorder_ratio":
                value /= 100
            if key in {"overdue_days", "leave_days", "notice_days"}:
                value = int(value)
            values.append(value)
        if values:
            found[key] = values[0]
            evidence[key] = [m.group(0) for m in matches]
            if len(set(values)) > 1:
                conflicts.append({"field": key, "values": values})
    return {
        "values": found,
        "evidence": evidence,
        "conflicts": conflicts,
        "unparsed_fields": sorted(set(Rules.model_fields) - set(found)),
        "requires_owner_review": True,
        "note": "Limited phrase parser. Unsupported clauses are not compiled. Review exceptions and source context before publishing.",
    }
