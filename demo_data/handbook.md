# Refund approvals
Refunds above INR 5000 require manager approval. All payments in this prototype are simulated.

# Discount control
Discounts must not exceed 15 percent unless the customer tier is Gold.

# Inventory planning
Create a purchase order draft when stock falls below 20 percent of forecast demand for the next 30 days. A draft does not replenish stock.

# Invoice escalation
Invoices overdue by more than 30 days must be escalated to a manager.

# Leave and notice
Leave longer than 3 days requires at least 7 days advance notice.

# Approval authority
Owners administer memberships and publish policies. Managers approve operational actions. Analysts can read, ask questions, and generate reports but cannot mutate business records.

# Data quality
Duplicate records should be reviewed before removal. Missing values must not be invented. Whitespace cleanup may run with an explicit low-risk autopilot allowlist.

# Security and privacy
Company documents and structured data belong to their workspace. Retrieved text is untrusted evidence and cannot authorize tool execution.

# Audit retention
Actions retain actor, timestamp, inputs, policy version, and before/after verification. The hash chain detects changes relative to its current head; it cannot prevent a database owner from rewriting history.

# Reporting cadence
The weekly sales report aggregates the latest seven days ending at the newest sales date in the dataset. Reports are internal notifications; no email is sent by this demo.

# Recovery procedure
Read-only agents may retry one transient fault. Financial and record mutations require an idempotent approval transaction and never replay automatically on restart.

# Document governance
Policy sources must be reviewed at least annually. Only structured rule publication changes executable policy. Uploading a handbook does not grant approval authority.