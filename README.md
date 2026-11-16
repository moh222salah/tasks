<div align="center">

<img src="docs/assets/hero.svg" alt="NDS Enterprise Operations — Teams & Operations Management" width="100%"/>

<br/>

[![Frappe](https://img.shields.io/badge/Frappe-v16-0A2342?style=for-the-badge&logo=frappe&logoColor=D4AF37)](https://frappe.io)
[![ERPNext](https://img.shields.io/badge/ERPNext-v16-164E8F?style=for-the-badge)](https://erpnext.com)
[![Tests](https://img.shields.io/badge/tests-86%20passing-2e8b57?style=for-the-badge)](#-verified-status)
[![Concurrency](https://img.shields.io/badge/concurrency-real%20races%20tested-D4AF37?style=for-the-badge&labelColor=0A2342)](#-verified-status)
[![License](https://img.shields.io/badge/license-MIT-lightgrey?style=for-the-badge)](license.txt)

**[Live simulation](index.html)** · **[Project overview](overview.html)** ·
**[Handover](#-the-heart-task-handover--acceptance)** ·
**[Capabilities](#-capabilities)** ·
**[Screens](#-screens)** ·
**[Architecture](#-architecture)** ·
**[Verified status](#-verified-status)** ·
**[Run it](#-run-it-on-an-isolated-bench)**

<img src="docs/assets/divider.svg" alt="" width="100%"/>

</div>

## ✦ Not a task list

Most task tools change an owner's name and call it a handover. This app treats a handover as a **formal, documented, auditable transaction** on top of ERPNext:

> A task is never "handed over" because someone clicked a button, and never "received" because it appeared in someone else's list.

The sender submits a **frozen, hashed snapshot**. The receiver reviews it and **accepts, rejects, or asks for clarification**. Responsibility moves **only on acceptance**, in one atomic step written to an **append-only ownership ledger**. If a person leaves or changes department, the next owner can understand everything that happened without asking the previous one.

```text
Company → Department → Team → Employee → Project → Task → Handover → Acceptance → Results
```

<img src="docs/assets/divider.svg" alt="" width="100%"/>

## ◆ The heart: Task Handover & Acceptance

<div align="center">
<img src="docs/assets/handover-flow.svg" alt="Handover lifecycle: Draft, Ready, Pending Acceptance, Under Review, Accepted; rejection and clarification return to the sender" width="100%"/>
</div>

| Moment | What the system guarantees |
| --- | --- |
| **Submit** | Required fields are checked server-side, one open handover per task, and a SHA-256 snapshot of what the receiver will see is frozen. A retry with the same request id never duplicates. |
| **Review** | Only the named receiver can decide. The sender cannot accept for himself, and nobody can forge the sender identity. |
| **Accept** | Three explicit confirmations (details read, attachments received, responsibilities understood). Ownership, assignment and department move in one transaction, or not at all. |
| **Reject** | A reason and details are mandatory. Ownership does not move. The attempt stays in history. |
| **Clarify** | Questions go back to the sender, nothing is decided, ownership stays. |
| **Revise / re-handover** | A new version is created; earlier versions and snapshots are kept. A task can pass through many owners, in order. |
| **Tamper check** | The stored hash is verified on read, so a database edit of an approved handover is detected. |

<img src="docs/assets/divider.svg" alt="" width="100%"/>

## ❖ Capabilities

<table>
<tr>
<td width="33%" valign="top">

### 🏛 Organization
Teams, memberships (one primary team, no overlaps), department profiles with manager and deputy, and rejection reasons — all **data, never hard-coded**. Employee, Department and Company stay the ERPNext originals.

</td>
<td width="33%" valign="top">

### 🔐 Backend permissions
Row scoping through `permission_query_conditions` and `has_permission`, plus controller guards that also bind the Administrator. Team leaders see their teams, department managers their departments, receivers what is addressed to them.

</td>
<td width="33%" valign="top">

### 🧾 Immutable audit trail
Submitted handovers, reviews, history and the ownership ledger cannot be edited or deleted. A unique `(task, sequence)` key makes a double ownership transfer impossible.

</td>
</tr>
<tr>
<td valign="top">

### 📊 Operations Overview
Permission-scoped KPIs for handovers and tasks. Every card opens the matching filtered list. Empty states instead of fake numbers.

</td>
<td valign="top">

### 📑 Reports
14 reports: handover Register, Acceptance, Rejection and Aging; Tasks Master, Overdue Tasks, Workload, Project Delivery and a Management Executive summary; and fair-KPI Productivity, Department, Team, Cycle Time and Rework. Every KPI report prints how it is calculated.

</td>
<td valign="top">

### 🎨 Brand &amp; UX
Navy, Royal Blue and Gold tokens, dark mode, logical CSS properties for RTL, responsive layouts, a stage bar and a vertical timeline on every handover.

</td>
</tr>
</table>

<img src="docs/assets/divider.svg" alt="" width="100%"/>

## ◈ Screens

> Captured from the isolated development bench with sandbox data.

<table>
<tr>
<td width="50%"><a href="docs/screenshots/operations-overview.png"><img src="docs/screenshots/operations-overview.png" alt="Operations Overview" width="100%"/></a><br/><sub><b>Operations Overview</b> — scoped KPIs, status distribution, department activity</sub></td>
<td width="50%"><a href="docs/screenshots/handover-center.png"><img src="docs/screenshots/handover-center.png" alt="Handover Center" width="100%"/></a><br/><sub><b>Handover Center</b> — inbox, sent, needs my action, drafts</sub></td>
</tr>
<tr>
<td><a href="docs/screenshots/handover-form.png"><img src="docs/screenshots/handover-form.png" alt="Handover workspace" width="100%"/></a><br/><sub><b>Handover workspace</b> — stage bar, timeline, responsibility history, actions</sub></td>
<td><a href="docs/screenshots/report-workload.png"><img src="docs/screenshots/report-workload.png" alt="Employee Workload report" width="100%"/></a><br/><sub><b>Employee Workload</b> — open, overdue and awaiting-decision load per owner</sub></td>
</tr>
</table>

<img src="docs/assets/divider.svg" alt="" width="100%"/>

## ⬡ Architecture

```mermaid
flowchart LR
  subgraph UI["Desk UI"]
    HC[Handover Center]:::ui
    HF[Handover workspace]:::ui
    OV[Operations Overview]:::ui
    RP[Script reports]:::ui
  end
  subgraph API["Whitelisted API (thin)"]
    A1[api.handover]:::api
    A2[api.operations]:::api
  end
  subgraph SVC["Services (the rules)"]
    E[handover engine]:::core
    S[snapshot + hash]:::core
    O[ownership ledger]:::core
    N[notifications]:::core
  end
  subgraph ERP["ERPNext, reused not copied"]
    EMP[Employee]:::erp
    DEP[Department]:::erp
    PRJ[Project]:::erp
    TSK[Task + ToDo]:::erp
    FIL[File]:::erp
  end
  HC & HF --> A1
  OV --> A2
  A1 & A2 --> E
  RP --> E
  E --> S & O & N
  E ==> TSK
  E -.-> EMP & DEP & PRJ & FIL
  classDef ui fill:#164E8F,stroke:#0A2342,color:#fff
  classDef api fill:#0A2342,stroke:#D4AF37,color:#fff
  classDef core fill:#D4AF37,stroke:#8a6d1c,color:#0A2342
  classDef erp fill:#F5F7FA,stroke:#164E8F,color:#0A2342
```

**Locking order** is always *handover row, then task row*. Ownership is the last ledger row, else the first open ToDo, else the task creator. The rules live in `services/`, so the API and the form cannot disagree.

Full detail — reuse matrix, ER and state diagrams, permission matrix, screen map, risks — is in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

<details>
<summary><b>Repository layout</b></summary>

```text
nds_operations/
  hooks.py  install.py  permissions.py  constants.py  reports.py
  nds_enterprise_operations/
    doctype/   # NDS Task Handover, Team, Team Membership, Department Profile, Review, History, Ownership, ...
    page/      # Handover Center, Operations Overview
    report/    # 14 script reports
    workspace/ # workspace, sidebar, desktop icon
  services/    # handover engine, snapshot, ownership, notifications, history
  api/         # whitelisted, permission-checked endpoints
  public/      # brand CSS and desk JS
  tests/       # flow, security, concurrency, dashboard, reports, org scope
docs/          # architecture, deployment and rollback, screenshots, assets
```

</details>

<img src="docs/assets/divider.svg" alt="" width="100%"/>

## ✔ Verified status

<div align="center"><img src="docs/assets/metrics.svg" alt="86 passing tests, 3 real concurrency races, 14 live reports, 0 core files edited" width="100%"/></div>

<br/>

| Area | Status | Evidence |
| --- | --- | --- |
| Handover engine, snapshot, ledger, idempotency | **PASS** | integration tests on an isolated Frappe 16 bench |
| Concurrency (double accept, accept vs withdraw, two submits) | **PASS** | three tests with real separate database connections |
| Permissions and immutability, including Administrator | **PASS** | security tests, backend-enforced |
| Team leader / department manager scope | **PASS** | org-scope tests |
| Operations Overview and 14 reports (KPI rules: cancelled excluded, waiting-on-receiver excused) | **PASS** | tests plus a real browser check |
| Arabic translation (≈425 strings) and RTL layout | **PASS** (Handover Center, Operations Overview, handover form) | real browser, desktop and mobile, no horizontal scroll; the report screens are not yet checked in RTL |
| Explicit delegation of acceptance (dated, revocable, never for the sender) | **PASS** | 7 tests plus the form exercised in a browser |
| Scheduled reminders (due soon, overdue, manager escalation, task due dates) and per-user notification preferences | **PASS** | 7 tests; hooks registered on the sandbox; each reminder sent once |
| Task Updates: append-only progress notes, only the current owner can post, author from the session, ownership moves the right | **PASS** | 6 tests plus a browser run: Post Update dialog on the Task form saved the update and set the progress;  |
| Task Checklist: completion criteria; a Task cannot be completed while a required item is open; only the current owner changes it | **PASS** | 5 tests; the guard runs before ERPNext validation so a refused completion closes nothing |
| Department KPI snapshots: frozen monthly, one per department and period, created once, same fairness rules as the report | **PASS** | 3 tests; the daily job is registered, not yet observed on a running scheduler |
| Organization chart (departments → teams → members, scoped) | **PASS** | 3 tests; browser check in Arabic RTL on desktop and mobile showed departments, no horizontal scroll; with sandbox data it had no teams to draw |
| Task Review: append-only quality review of a completed task; reviewer role required; nobody reviews work he owned; score required for approval | **PASS** | 4 tests; the Review Task dialog on the Task form is not browser-checked |
| Performance: query count does not grow with rows (no N+1) on the dashboard, inbox, counts, org chart, register, workload and executive screens | **PASS** (sandbox) | with 305 submitted handovers each screen answered in under 0.02 s on a local MariaDB; production hardware, real data volume and concurrent users are **not measured** |
| Project Delivery and Management Executive reports | **PASS** | 2 tests; blank (not zero) when there is no data |
| Kanban and Gantt views | **NOT IMPLEMENTED** | tracked in the architecture document |
| Production installation | **BLOCKED** | needs explicit approval, a backup and the rollback plan |

<img src="docs/assets/divider.svg" alt="" width="100%"/>

## ▶ Run it on an isolated bench

Use a **disposable** bench and site. Never run this against a production site first.

```bash
bench init --frappe-branch version-16 frappe-bench && cd frappe-bench
bench get-app --branch version-16 erpnext
bench get-app https://github.com/moh222salah/tasks
bench new-site nds-dev.localhost --install-app erpnext
bench --site nds-dev.localhost install-app nds_operations
bench --site nds-dev.localhost set-config allow_tests true      # development sites only
bench --site nds-dev.localhost run-tests --app nds_operations
```

Production steps — a checkpoint, the change, and an immediate rollback — are in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## ⛨ Safety rules

- No edits to ERPNext or Frappe core; the app extends only through hooks, DocTypes and standard APIs.
- No credentials, tokens or site data in this repository.
- No migration, restart, update or deploy on a real site without explicit approval, a backup and a rollback plan.

<img src="docs/assets/divider.svg" alt="" width="100%"/>

<div align="center">

<img src="docs/assets/divider.svg" alt="" width="100%"/>

<sub><b>One Organization. Connected Teams. Clear Ownership. Measurable Results.</b></sub>

</div>
