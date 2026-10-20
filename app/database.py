"""SQLite persistence. Business mutations and audit writes share a transaction."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self, write=False):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            if write:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self):
        with self.connect() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript('''
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY, customer TEXT NOT NULL, product TEXT NOT NULL,
                amount_paise INTEGER NOT NULL CHECK(amount_paise > 0),
                status TEXT NOT NULL CHECK(status IN ('processing','shipped','delivered','cancelled')),
                payment_status TEXT NOT NULL CHECK(payment_status IN ('paid','unpaid','refunded')),
                due_at TEXT NOT NULL, delivered_at TEXT, version INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(id),
                status TEXT NOT NULL, intent TEXT NOT NULL, message TEXT NOT NULL,
                mode TEXT NOT NULL, decision_json TEXT NOT NULL, evidence_json TEXT NOT NULL,
                snapshot_json TEXT NOT NULL, policy_hash TEXT NOT NULL,
                response TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                request_key TEXT UNIQUE, request_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT NOT NULL REFERENCES workflows(id),
                agent TEXT NOT NULL, event TEXT NOT NULL, detail_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS approvals (
                workflow_id TEXT PRIMARY KEY REFERENCES workflows(id), approved INTEGER NOT NULL,
                reviewer TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS refunds (
                id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT UNIQUE NOT NULL REFERENCES orders(id),
                workflow_id TEXT UNIQUE NOT NULL REFERENCES workflows(id), amount_paise INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'simulated', created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS event_workflow ON events(workflow_id,id);
            ''')
        stamp = datetime.now(timezone.utc)
        due = (stamp - timedelta(days=2)).isoformat(timespec="seconds")
        future = (stamp + timedelta(days=3)).isoformat(timespec="seconds")
        recent = (stamp - timedelta(days=3)).isoformat(timespec="seconds")
        old = (stamp - timedelta(days=14)).isoformat(timespec="seconds")
        samples = [
            ("ORD-1001", "Aarav Sharma", "Wireless keyboard", 249900, "processing", "paid", due, None),
            ("ORD-1002", "Meera Kapoor", "Study lamp", 129900, "shipped", "paid", due, None),
            ("ORD-1003", "Rohan Verma", "Laptop sleeve", 89900, "delivered", "paid", due, recent),
            ("ORD-1004", "Ananya Rao", "Desk organiser", 69900, "delivered", "paid", due, old),
            ("ORD-1005", "Kabir Singh", "USB-C hub", 189900, "cancelled", "paid", due, None),
            ("ORD-1006", "Isha Gupta", "Notebook set", 49900, "processing", "unpaid", future, None),
            ("ORD-1007", "Dev Patel", "Monitor stand", 159900, "cancelled", "refunded", due, None),
            ("ORD-1008", "Sara Khan", "Webcam", 329900, "processing", "paid", future, None),
        ]
        with self.connect(write=True) as c:
            c.executemany("INSERT OR IGNORE INTO orders(id,customer,product,amount_paise,status,payment_status,due_at,delivered_at) VALUES(?,?,?,?,?,?,?,?)", samples)

        from .core.trace_store import TraceStore
        TraceStore(self).initialize()

    @staticmethod
    def event(c, workflow_id, agent, event, detail):
        c.execute("INSERT INTO events(workflow_id,agent,event,detail_json,created_at) VALUES(?,?,?,?,?)",
                  (workflow_id, agent, event, json.dumps(detail), now()))

    def orders(self):
        with self.connect() as c:
            return [dict(r) for r in c.execute("SELECT * FROM orders ORDER BY id")]

    def order(self, order_id):
        with self.connect() as c:
            row = c.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            return dict(row) if row else None

    def workflow(self, workflow_id):
        with self.connect() as c:
            row = c.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            for name in ("decision", "evidence", "snapshot"):
                result[name] = json.loads(result.pop(name + "_json"))
            result["events"] = []
            for event in c.execute("SELECT * FROM events WHERE workflow_id=? ORDER BY id", (workflow_id,)):
                item = dict(event)
                item["detail"] = json.loads(item.pop("detail_json"))
                result["events"].append(item)
            approval = c.execute("SELECT * FROM approvals WHERE workflow_id=?", (workflow_id,)).fetchone()
            result["approval"] = dict(approval) if approval else None
            return result

    def workflows(self):
        with self.connect() as c:
            return [dict(r) for r in c.execute("SELECT id,order_id,status,intent,mode,response,created_at FROM workflows ORDER BY created_at DESC,rowid DESC LIMIT 100")]

    def metrics(self):
        with self.connect() as c:
            counts = {r[0]: r[1] for r in c.execute("SELECT status,COUNT(*) FROM workflows GROUP BY status")}
            return {"orders": c.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
                    "workflows": sum(counts.values()), "pending": counts.get("pending_approval", 0),
                    "completed": counts.get("completed", 0), "escalated": counts.get("escalated", 0),
                    "refunds": c.execute("SELECT COUNT(*) FROM refunds").fetchone()[0],
                    "audit_events": c.execute("SELECT COUNT(*) FROM events").fetchone()[0]}
