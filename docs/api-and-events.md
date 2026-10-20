# API, roles and events

Interactive OpenAPI documentation is served at `/docs`. The final API prefix is `/v1`; the legacy sandbox is disabled by default. All examples below use `C` for a company ID and `K` for a tenant-owned item ID.

## Identity

Register with `POST /v1/auth/register` or sign in with `POST /v1/auth/login` using `{ "email": "you@example.com", "password": "at-least-10-characters" }`. The response sets an HttpOnly, SameSite=Strict cookie. `GET /v1/me` checks identity; `POST /v1/auth/logout` revokes that session. Tokens are random and stored as SHA-256 digests; passwords use salted PBKDF2-HMAC-SHA256 with 310,000 iterations. Sessions expire after 12 hours. Five failed sign-ins for an account trigger an in-process five-minute delay.

| Role | Permitted workspace operations |
|---|---|
| Analyst | Read records/documents/policies/audit; ask questions; run Q&A, sales reports, simulation and evaluation |
| Manager | Analyst operations plus uploads, source/record edits, operational proposal runs, approvals/rejections and schedules |
| Owner | Manager operations plus memberships, policy publication and explicit whitespace autopilot |

An authenticated user may create a new company and becomes its Owner. Adding someone to an existing workspace requires that person's registered email and an Owner. The final Owner cannot demote themselves. Every data route resolves membership before querying tenant-owned objects. Client-provided role labels are not trusted.

## Endpoint map

| Method | Path after `/v1` | Purpose |
|---|---|---|
| GET/POST | `/companies` | List memberships / create company |
| GET/POST | `/companies/C/members` | Owner membership administration |
| POST | `/companies/C/demo` | Idempotently seed an empty dataset workspace |
| GET | `/companies/C/overview` | Actual counts, heuristic and sales aggregation |
| GET | `/companies/C/datasets` | Dataset profiles without full row arrays |
| GET | `/companies/C/datasets/K?offset=0` | Up to 100 rows and profile |
| POST | `/companies/C/datasets/K/record` | Version-checked record correction |
| POST | `/companies/C/upload` | Multipart `file`, category field |
| GET | `/companies/C/documents` | Source metadata and trust flags |
| GET | `/companies/C/documents/K` | Source text, real page/section metadata and chunks |
| POST | `/companies/C/documents/K/edit` | Reviewed text revision and reindex |
| POST | `/companies/C/documents/K/reindex` | Recreate chunk index and increment source version |
| GET | `/companies/C/documents/K/rule-draft` | Conservative supported-clause extraction |
| GET/POST | `/companies/C/policies` | Published policy / Owner publication |
| GET | `/companies/C/policy-history` | Previous published snapshots |
| POST | `/companies/C/ask` | Cited extracts or fixed sales aggregation |
| GET | `/companies/C/issues` | Conditions, proposals and prior review evidence |
| POST | `/companies/C/issues/K/review` | Approve/reject with expected issue version |
| POST | `/companies/C/autopilot` | Explicit whitespace-only run-on-enable |
| POST/GET | `/companies/C/runs` | Submit allowlisted DAG / list runs |
| GET | `/companies/C/runs/K` | Run status and result |
| GET | `/companies/C/runs/K/events` | Authorized SSE with Last-Event-ID or `after` cursor |
| GET | `/companies/C/runs/K/replay` | Persisted event array, no execution |
| GET | `/companies/C/reports` | Published/draft report records |
| GET | `/companies/C/reports/K/pdf` | Download generated PDF |
| GET | `/companies/C/handbook.pdf` | Download twelve-page synthetic handbook |
| GET | `/companies/C/drafts` | PO drafts and internal escalations |
| GET/POST | `/companies/C/schedules` | Persisted weekly-window report interval |
| GET | `/companies/C/audit` | Latest 300 entries for inspection |
| GET | `/companies/C/audit/verify` | Verify the complete tenant chain |
| POST | `/companies/C/evaluate` | Measure the small golden benchmark |
| GET | `/companies/C/evaluations` | Saved measurement runs |

## Command examples

Run request:

```json
{"workflow":"weekly","fail_once":true}
```

`workflow` is one of `weekly`, `qa`, `scan`, `refund`, `inventory`, `simulate`. Q&A takes `question`; simulation takes the `proposed` rule object. The server returns HTTP 202 with an ID. The bounded executor returns 429 when its ten outstanding slots are occupied.

Review request:

```json
{"decision":"approve","version":1}
```

The version comes from the current issue. Repeating the same review version returns the recorded outcome rather than applying it again. Changed issue/dataset/policy/source state returns 409. An action requiring known data rejects automatic execution and exposes a record-edit path instead.

Policy publication requires `rules`, `source_document`, `expected_version`, and `rationale`. An initial publication uses expected version 0. No text draft automatically publishes itself.

## Event contract

Each persisted event contains `id`, `company` scope enforced by its storage row, `run_id`, run-local monotonic `seq`, `type`, `agent`, JSON `detail`, and UTC `at`. Company is not repeated in the response payload; it is part of the authorized route and database filter.

Event types include `run_started`, `message_sent`, `agent_state_changed`, `agent_started`, `step_completed`, `agent_completed`, `retry`, `error`, `run_done`, and `run_error`. The nested message envelope includes request/reply identity and causation. SSE `id:` is the run sequence; reconnect reads only later events. Heartbeats are comments. Terminal events are persisted before terminal run status becomes visible.

Replay reads the event array only. Compute durations are measured around actual handler invocation; timeline widths show elapsed wall time and include storage/orchestration overhead. No animation timer creates synthetic progress or confidence values.

## Status and error behavior

401 means no valid session; 403 means a denied role or cross-origin mutation; tenant-scoped missing objects use 404; unsupported files use 415; byte/row/archive/page limits use 413; stale versions use 409. Invalid Pydantic request fields return 422. Unhandled agent errors store a safe run error and retain detailed server logs.
