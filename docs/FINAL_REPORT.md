# Final report

Date: 2026-11-16. Scope: the `nds_operations` Frappe app in this repository. Everything below was run on an isolated
development bench (Frappe 16.55, ERPNext v16). **Nothing was installed on the Saudi production site and the Egyptian
system was never touched.** Status words: PASS, FAIL, BLOCKED, NOT IMPLEMENTED. "PASS" always names its evidence.

## 1. ROOT CAUSE / BASELINE

| Item | Status | Evidence |
| --- | --- | --- |
| Baseline on an isolated bench (fresh Frappe 16.55 + ERPNext v16, test site) | PASS | all 95 tests run there; the module adds no core edits |
| Audit of the real Saudi site (installed apps, Client Scripts and Workflows on Task, User Permissions, existing customisations) | BLOCKED | needs an authorised session; the read-only commands are in `docs/DEPLOYMENT.md` section 0 |
| Official websites studied for the department list | PASS | departments are data, not code (Department and Team records are editable in the desk) |

## 2. ARCHITECTURE

PASS. `docs/ARCHITECTURE.md`: reuse matrix (Employee, Department, Company, Task, ToDo, File, Notification Log), module
architecture, DocTypes and relationships, handover workflow, permission matrix, screen map, risks, plan. The app adds its
own DocTypes and links to the standard ones; it does not replace any of them.

## 3. IMPLEMENTATION

| Area | Status | Evidence |
| --- | --- | --- |
| Handover engine: draft, ready, submit, review, accept, reject, clarify, withdraw, revise | PASS | `tests/test_handover_flow.py` (12), `test_handover_security.py` (9) |
| Ownership moves only on acceptance; append-only ownership ledger with unique (task, sequence) | PASS | scenarios 1, 2, 5, 7 |
| Frozen snapshot with SHA-256 and tamper detection | PASS | `test_snapshot_is_frozen_and_detects_tampering` |
| Idempotent submit (retry never duplicates) | PASS | scenario 10 test |
| Concurrency (3 real multi-connection races) | PASS | `tests/test_concurrency.py` |
| Explicit, dated, revocable delegation of decisions | PASS | `tests/test_delegation.py` (7) |
| Reminders, overdue alert, escalation; required and mutable notifications | PASS | `tests/test_reminders.py` (7); the hourly job was run by the test, a real scheduler tick was not observed |
| Tasks: updates, completion checklist with guard, quality review | PASS | 16 tests |
| Frozen monthly Department KPI snapshots | PASS | 3 tests; the monthly scheduler tick itself was not observed |
| Organization chart, employee profile, team profile | PASS | 12 tests plus browser runs |
| 14 reports with filters, method text and standard export | PASS | 11 report tests; every report opens in a browser |
| Operations Overview dashboard (real data, clickable cards, empty states) | PASS | 5 tests; browser desktop and mobile |
| Handover Center, handover workspace, dialogs, stage bar, timeline | PASS | browser |
| Kanban board, Gantt, Calendar for Tasks | PASS | Kanban seeded and tested; Gantt and Calendar are native ERPNext views |
| Curated workspace and sidebar (Frappe 16 format) | PASS | browser on the sandbox |
| Arabic (about 400 strings), RTL | PASS for the handover form and layout; partial elsewhere | see section 9 |
| Self-acceptance by approved exception | NOT IMPLEMENTED | self-handover is always refused (safer) |
| Automatic ledger row when someone reassigns a task by hand (ToDo) | NOT IMPLEMENTED | accept is refused if ownership no longer matches |
| Custom e-mail templates | NOT IMPLEMENTED | uses Notification Log and the user's own e-mail settings |
| A separate "Team Assignment" DocType | NOT IMPLEMENTED | covered by Team Membership |

## 4. FILES CREATED

198 files, 17,232 lines added since the scaffold commit (`git diff --stat f04f769..HEAD`). By kind:

- 16 DocTypes under `nds_operations/nds_enterprise_operations/doctype/`
- 14 script reports under `.../report/`
- 4 desk pages under `.../page/` (Handover Center, Operations Overview, Organization Chart, Profile)
- services (`handover`, `kpi`, `kpi_snapshot`, ...), APIs (`handover`, `operations`, `organization`, `profile`), `permissions.py`, `reports.py`, `install.py`, one patch
- workspace and Sidebar JSON, `locale/ar.po`, CSS and JS in `public/`
- 17 test modules, docs (`ARCHITECTURE.md`, `DEPLOYMENT.md`, this report), `README.md`, `overview.html`, `index.html`

## 5. FILES MODIFIED

No ERPNext or Frappe file was modified. The repository started as a scaffold, so apart from the README and docs the
files are new. The app hooks into standard documents only through `hooks.py`: a `doctype_js` file for the Task form, a
`before_validate` guard on Task completion (blocks completion while required checklist items are open), permission
query and `has_permission` hooks, and two scheduler jobs.

## 6. DATABASE CHANGES

Only on a bench where the app is installed (sandbox so far): the 16 DocTypes above, 10 roles (created only if
missing), one workspace and its sidebar, 4 pages, 14 reports, one Kanban board "NDS Tasks by Status" (created only if
absent), default rejection reasons. No Custom Fields, no change to existing records, no migration on production.

## 7. HANDOVER WORKFLOW VERIFICATION

| Scenario | Status | Test |
| --- | --- | --- |
| 1 Finished task handed over and accepted | PASS | `test_scenario_1_accept_moves_responsibility_only_after_acceptance` |
| 2 Rejection keeps responsibility | PASS | `test_scenario_2_reject_keeps_responsibility_and_revision_continues` |
| 3 Clarification, then resubmit | PASS | `test_scenario_3_clarification_then_resubmit` |
| 4 Between two departments | PASS | `test_scenario_4_cross_department_handover` |
| 5 Re-handover, full chain kept | PASS | `test_scenario_5_re_handover_keeps_the_whole_chain` |
| 6 Technical attachments and access | PASS | `test_scenario_6_private_attachments_follow_the_handover` |
| 7 Two simultaneous accepts | PASS | `test_scenario_7_two_simultaneous_accepts_transfer_once` (real parallel connections) |
| 8 Unauthorised accept or edit | PASS | `test_scenario_8_only_the_receiver_decides`, `..._submitted_records_are_immutable_even_for_administrator` |
| 9 Overdue tasks with owner and reason | PASS | `test_overdue_report_gives_a_visible_reason_only`, `test_master_shows_owner_overdue_and_open_handover` |
| 10 Retry after a lost connection | PASS | `test_scenario_10_retry_does_not_duplicate` |

`index.html` replays the same ten scenarios in the browser. That is a simulation of the rules, not evidence about the
Frappe app.

## 8. PERMISSIONS VERIFICATION

PASS. Checks run in the backend (DocPerm, `permission_query_conditions`, `has_permission`, engine guards, because
Administrator bypasses hooks): only the named receiver or an active delegate decides; the sender never decides; identity
fields cannot be forged; submitted records, reviews, history and ledger rows cannot be edited or deleted, Administrator
included; team leaders and department managers see their scope; auditors read only; a colleague's profile needs access
to that Employee record. Evidence: `test_handover_security.py`, `test_org_scope.py`, `test_delegation.py`,
`test_profile.py`. Not verified: every combination of the 12 roles on every screen.

## 9. UI/UX VERIFICATION

| Item | Status | Evidence |
| --- | --- | --- |
| Handover Center, workspace, dialogs, dashboard, org chart, profiles, 14 reports, Kanban, Gantt | PASS | opened in a browser on the sandbox with real records |
| Mobile (390 px) | PASS | dashboard, org chart, profile pages and 14 reports: no horizontal scroll |
| RTL layout | PASS | 17 pages at desktop and mobile with direction forced to RTL, no horizontal scroll (English strings) |
| Real Arabic session | PASS for the handover form; NOT VERIFIED for the report screens | screenshot `docs/screenshots/handover-form-rtl.png` |
| Dark mode | NOT VERIFIED | styles use theme variables; not screenshot-checked |
| Checklist and review dialogs in a browser | NOT VERIFIED | covered by tests only |
| Drag and drop on the Kanban board | NOT VERIFIED | |

## 10. PERFORMANCE RESULTS

PASS on the sandbox, with a small data set. `tests/test_performance.py` seeds 305 submitted handovers and compares the
number of SQL queries at 5 rows and at 5 plus N rows: the count stays flat on the list, the dashboard and the reports,
and the run stays under 0.02 s of query time. Server-side filtering and pagination are used. Not verified: production
data volumes and the Saudi server's hardware.

## 11. REGRESSION TEST RESULTS

| Item | Status | Evidence |
| --- | --- | --- |
| The app's own suite | PASS | 95 tests, OK |
| Standard ERPNext and Frappe test suites with the app installed | NOT RUN | would show impact on other modules; needs time on the sandbox |
| Task form with the app's JS and the completion guard | PASS | `test_task_checklist.py`; tasks without a checklist are unaffected |
| Other modules and customisations on the real Saudi site | BLOCKED | needs the audit in section 1 |

## 12. BACKUP & ROLLBACK

PASS as documentation, NOT EXECUTED on a real site. `docs/DEPLOYMENT.md`: read-only audit, safe checkpoint (backup with
files and recorded app versions), install, verification, immediate rollback (uninstall removes the app's tables, roles,
workspace and pages). All server commands are meant to be run only after explicit approval.

## 13. PRODUCTION DEPLOYMENT STATUS

BLOCKED. No install, migration, restart, update or deploy has been done on the Saudi site, and none will happen without
an explicit approval after the audit, a fresh backup and a review of this report.

## Summary against the acceptance list

Met with evidence: independent workspace, organization and teams, projects and tasks, real send and receive, accept,
reject and clarify, ownership moves only on acceptance, responsibility history, attachments, technical records,
notifications, backend permissions, dashboard on real data, 14 exportable reports, Arabic and English with an RTL layout,
no core edits, rollback document. Not met or not shown: production audit and deployment (BLOCKED), standard ERPNext
regression suite (NOT RUN), dark-mode and drag-and-drop checks (NOT VERIFIED), Arabic on every screen (partial).
