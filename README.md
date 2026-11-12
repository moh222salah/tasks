# NDS Enterprise Teams & Operations Management

**One Organization. Connected Teams. Clear Ownership. Measurable Results.**

إدارة الفرق والأقسام والعمليات المؤسسية — تطبيق Frappe/ERPNext v16 لشركة NDS.

This is **not** a task list. It is an operations layer on top of ERPNext whose centre of gravity is a formal
**Task Handover & Acceptance** process:

```
Company → Department → Team → Employee → Project → Task → Handover → Acceptance → Results
```

A task is never "handed over" because someone clicked a button, and it is never "received" because it
appeared in someone else's list. The sender submits a frozen, hashed snapshot; the receiver reviews it and
**accepts, rejects or asks for clarification**; responsibility moves **only on acceptance**, in one atomic
step that is written to an append-only ownership ledger.

## Design rules

| Rule | How it is met |
| --- | --- |
| No ERPNext / Frappe core edits | Stand-alone app; extends only through hooks, DocTypes and standard APIs |
| Reuse, don't duplicate | Employee, Department, Company, Project, Task, ToDo, File, Notification, Role are linked, never copied |
| Backend-enforced permissions | `permission_query_conditions` + `has_permission` + controller guards (the UI only mirrors them) |
| Immutable audit trail | Submitted handovers, reviews, history and the ownership ledger cannot be edited or deleted |
| Safe under concurrency | Row locks on handover then task, a unique `(task, sequence)` ledger key, idempotent request ids |
| Dynamic structure | Departments, teams, roles-in-team and rejection reasons are data, never hard-coded |

## Layout

```
nds_operations/
  hooks.py  install.py  permissions.py  constants.py
  nds_enterprise_operations/doctype/   # NDS Task Handover, Team, Team Membership, Department Profile, ...
  utils/                               # people lookups, immutable-record base class
  api/                                 # whitelisted, permission-checked endpoints
  tests/
docs/                                  # architecture, permission matrix, workflow, rollback guide
```

## Safety

* Develop and test on an isolated bench only. This repository contains no credentials, tokens or site data.
* Installing on a real site (`bench install-app`, `bench migrate`, restart) is a **deployment** step that needs
  an explicit approval, a backup, and the rollback plan in `docs/`.

## Status

Work in progress — see the commit history and `docs/` for what is implemented and what is verified.
