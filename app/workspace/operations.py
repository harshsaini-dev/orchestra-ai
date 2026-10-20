"""Business operations: allowlisted analytics, issue detection and atomic approval."""

import hashlib
from datetime import date, timedelta
from collections import defaultdict
from fastapi import HTTPException
from .store import pack, canonical
from .policies import decide
from .ingestion import profile, number


def active_policy(store, s, company):
    policies = store.items(company, "policy", s)
    if not policies:
        raise HTTPException(409, "Seed the demo or publish a policy first")
    return max(
        policies, key=lambda p: (p.data.get("priority", 100), p.version, p.created)
    )


def analytics(datasets, weekly=False):
    rows = [r for d in datasets if d["category"] == "sales" for r in d["rows"]]
    valid = [r for r in rows if number(r.get("amount")) is not None and r.get("date")]
    dates = []
    for row in valid:
        try:
            dates.append(date.fromisoformat(str(row["date"])[:10]))
        except ValueError:
            pass
    end = max(dates) if dates else None
    selected = []
    for row in valid:
        try:
            day = date.fromisoformat(str(row["date"])[:10])
        except ValueError:
            continue
        if not weekly or day >= end - timedelta(days=6):
            selected.append(row)
    series = defaultdict(float)
    for row in selected:
        series[str(row["date"])[:7]] += float(row["amount"])
    return {
        "metric": "sales",
        "period": "latest seven dataset days" if weekly else "all dataset dates",
        "as_of": str(end) if end else None,
        "records": len(selected),
        "total": round(sum(float(r["amount"]) for r in selected), 2),
        "series": [
            {"label": k, "value": round(v, 2)} for k, v in sorted(series.items())
        ],
        "excluded_invalid": len(rows) - len(valid),
        "quality_note": "Raw uploaded records; duplicates and outliers remain included until explicitly corrected.",
    }


def detect(datasets, rules):
    found = []

    def add(dataset, index, code, message, action=None, severity="medium", trace=None):
        row = dataset["rows"][index]
        key = hashlib.sha256(
            canonical([dataset["id"], code, row.get("id", index)]).encode()
        ).hexdigest()
        found.append(
            {
                "key": key,
                "dataset": dataset["id"],
                "dataset_version": dataset["version"],
                "row_index": index,
                "record": row,
                "code": code,
                "message": message,
                "action": action,
                "severity": severity,
                "trace": trace,
            }
        )

    for ds in datasets:
        seen = set()
        for i, row in enumerate(ds["rows"]):
            fingerprint = canonical(row)
            if fingerprint in seen:
                add(
                    ds,
                    i,
                    "duplicate",
                    "Duplicate row requires review",
                    "remove_duplicate",
                )
            seen.add(fingerprint)
            if any(v is None or str(v).strip() == "" for v in row.values()):
                add(ds, i, "missing", "Missing values require an informed record edit")
            if any(isinstance(v, str) and v != v.strip() for v in row.values()):
                add(ds, i, "whitespace", "Leading or trailing whitespace", "trim")
            category = {
                "sales": "discount",
                "refunds": "refund",
                "inventory": "inventory",
                "invoices": "overdue",
                "leave": "leave",
            }.get(ds["category"])
            if category:
                try:
                    trace = decide(category, row, rules)
                except (ValueError, TypeError):
                    add(
                        ds,
                        i,
                        "invalid_rule_input",
                        "Non-numeric rule input; correct the record",
                    )
                    continue
                if trace["flagged"] and not (
                    category == "refund" and row.get("status") == "approved"
                ):
                    action = {
                        "discount": "cap_discount",
                        "refund": "refund",
                        "inventory": "purchase_order",
                        "overdue": "escalate",
                        "leave": None,
                    }[category]
                    add(
                        ds,
                        i,
                        category,
                        f"{category.title()}: {trace['outcome'].replace('_', ' ')}",
                        action,
                        "high" if category in {"refund", "discount"} else "medium",
                        trace,
                    )
        numeric = ds.get("profile", {}).get("columns", {})
        for col, stats in numeric.items():
            if stats.get("outliers"):
                values = [number(r.get(col)) for r in ds["rows"]]
                nums = [v for v in values if v is not None]
                import statistics

                mean = statistics.mean(nums)
                sd = statistics.pstdev(nums)
                for i, v in enumerate(values):
                    if v is not None and sd and abs(v - mean) > 3 * sd:
                        add(
                            ds,
                            i,
                            "outlier_" + col,
                            f"{col} exceeds 3 population standard deviations; investigate, do not auto-delete",
                        )
    return found


def scan(store, company, actor):
    with store.tx() as s:
        policy = active_policy(store, s, company)
        datasets = [pack(d) for d in store.items(company, "dataset", s)]
        detected = detect(datasets, policy.data["rules"])
        docs = [pack(d) for d in store.items(company, "document", s)]
        from .policies import extract_supported
        from datetime import datetime, timezone

        for doc in docs:
            reasons = []
            draft = extract_supported(" ".join(p["text"] for p in doc["pages"]))
            if draft["conflicts"]:
                reasons.append(
                    (
                        "policy_conflict",
                        "Conflicting supported values in " + doc["name"],
                    )
                )
            if (
                doc["id"] == policy.data["source_document"]
                and doc["version"] != policy.data["source_version"]
            ):
                reasons.append(
                    (
                        "stale_policy_source",
                        "Policy source changed; review and publish an updated policy",
                    )
                )
            if (
                doc.get("review_date")
                and (
                    datetime.now(timezone.utc).date()
                    - datetime.fromisoformat(doc["review_date"]).date()
                ).days
                > 365
            ):
                reasons.append(
                    ("stale_document", "Annual source review overdue: " + doc["name"])
                )
            for code, message in reasons:
                detected.append(
                    {
                        "key": doc["id"] + ":" + code,
                        "dataset": None,
                        "dataset_version": None,
                        "document": doc["id"],
                        "row_index": 0,
                        "record": {"document": doc["name"], "version": doc["version"]},
                        "code": code,
                        "message": message,
                        "action": None,
                        "severity": "medium",
                        "trace": draft if code == "policy_conflict" else None,
                    }
                )
        existing = {i.data["key"]: i for i in store.items(company, "issue", s)}
        live = set()
        for issue in detected:
            live.add(issue["key"])
            issue.update(
                policy_id=policy.id, policy_version=policy.version, status="open"
            )
            if issue.get("trace"):
                issue["trace"]["source"] = {
                    "document_id": policy.data["source_document"],
                    "document_version": policy.data["source_version"],
                    "policy_version": policy.version,
                    "authority": "Published structured rule; source prose is reference evidence",
                }
            if issue["key"] in existing:
                old = existing[issue["key"]]
                issue.update(
                    {
                        k: old.data[k]
                        for k in ["mitigation", "last_action"]
                        if k in old.data
                    }
                )
                old.data = issue
                old.version += 1
            else:
                store.put(s, company, "issue", issue)
        for key, item in existing.items():
            if key not in live and item.data["status"] != "closed":
                item.data = {
                    **item.data,
                    "status": "closed",
                    "verification": "Underlying condition no longer detected",
                }
                item.version += 1
        store.audit(
            s, company, actor, "issues.scan", {"open_conditions": len(detected)}
        )
        return {
            "open_conditions": len(detected),
            "health_score": max(
                0, 100 - sum(8 if i["severity"] == "high" else 3 for i in detected)
            ),
            "formula": "max(0, 100 - 8 × high conditions - 3 × other conditions); heuristic, not a business KPI",
        }


def approve(
    store, company, actor, issue_id, decision, expected_version, autopilot=False
):
    with store.tx() as s:
        issue = store.get(s, company, issue_id, "issue")
        if issue.data.get("last_action", {}).get("issue_version") == expected_version:
            return {"idempotent": True, **issue.data["last_action"]}
        if issue.version != expected_version:
            raise HTTPException(409, "Issue changed; refresh before reviewing")
        if issue.data["status"] == "closed":
            raise HTTPException(409, "Issue already closed")
        if decision == "reject":
            issue.data = {
                **issue.data,
                "last_action": {
                    "decision": "rejected",
                    "actor": actor,
                    "issue_version": expected_version,
                },
            }
            issue.version += 1
            store.audit(s, company, actor, "issue.rejected", {"issue": issue.id})
            return pack(issue)
        action = issue.data["action"]
        if not action:
            raise HTTPException(
                400, "This issue needs an informed record edit, not an automated fix"
            )
        if autopilot and action != "trim":
            raise HTTPException(
                403, "Autopilot allowlist contains whitespace trimming only"
            )
        dataset = store.get(s, company, issue.data["dataset"], "dataset")
        policy = active_policy(store, s, company)
        if (
            dataset.version != issue.data["dataset_version"]
            or policy.id != issue.data["policy_id"]
            or policy.version != issue.data["policy_version"]
        ):
            raise HTTPException(409, "Dataset or policy changed; run issue scan again")
        source = store.get(s, company, policy.data["source_document"], "document")
        if source.version != policy.data["source_version"]:
            raise HTTPException(
                409,
                "Policy source changed; an Owner must review and republish before execution",
            )
        rows = [dict(r) for r in dataset.data["rows"]]
        idx = issue.data["row_index"]
        row = rows[idx]
        before = dict(row)
        effect = None
        if action == "remove_duplicate":
            if sum(r == row for r in rows) < 2:
                raise HTTPException(409, "Duplicate no longer exists")
            rows.pop(idx)
            verified = sum(r == before for r in rows) == 1
        elif action == "trim":
            rows[idx] = {
                k: v.strip() if isinstance(v, str) else v for k, v in row.items()
            }
            verified = all(
                not isinstance(v, str) or v == v.strip() for v in rows[idx].values()
            )
        elif action == "cap_discount":
            rows[idx]["discount"] = policy.data["rules"]["discount_cap"]
            verified = not decide("discount", rows[idx], policy.data["rules"])[
                "flagged"
            ]
        elif action == "refund":
            if row.get("status") == "approved":
                raise HTTPException(409, "Refund already approved")
            rows[idx]["status"] = "approved"
            rows[idx]["simulated"] = True
            verified = rows[idx]["status"] == "approved"
        else:
            kind = "purchase_order" if action == "purchase_order" else "escalation"
            drafts = store.items(company, "draft", s)
            prior = next((d for d in drafts if d.data.get("issue") == issue.id), None)
            if prior:
                effect = pack(prior)
            else:
                effect = pack(
                    store.put(
                        s,
                        company,
                        "draft",
                        {
                            "type": kind,
                            "issue": issue.id,
                            "record": before,
                            "status": "draft"
                            if kind == "purchase_order"
                            else "internal_escalation",
                            "quantity": max(
                                0,
                                float(row.get("demand30", 0))
                                - float(row.get("stock", 0)),
                            )
                            if kind == "purchase_order"
                            else None,
                        },
                    )
                )
            verified = bool(effect)
        if not verified:
            raise HTTPException(
                409, "Auditor postcondition failed; transaction rolled back"
            )
        if action in {"trim", "remove_duplicate", "cap_discount", "refund"}:
            dataset.data = {**dataset.data, "rows": rows, "profile": profile(rows)}
            dataset.version += 1
        result = {
            "decision": "approved",
            "action": action,
            "actor": actor,
            "issue_version": expected_version,
            "verified": verified,
            "effect": effect,
            "simulation": action == "refund",
            "condition_closed": action
            in {"trim", "remove_duplicate", "cap_discount", "refund"},
        }
        issue.data = {
            **issue.data,
            "status": "closed" if result["condition_closed"] else "open",
            "mitigation": effect,
            "last_action": result,
        }
        issue.version += 1
        store.audit(
            s,
            company,
            actor,
            "issue.executed",
            {
                "issue": issue.id,
                "before": before,
                "after": rows[idx]
                if idx < len(rows) and action != "remove_duplicate"
                else None,
                "policy_version": policy.version,
                "result": result,
            },
        )
        return result
