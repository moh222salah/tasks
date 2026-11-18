# Deployment, verification and rollback

Pinned commit: `7b8e31b874c8c34397c1057b13476ea3402d3bef` (branch `main` of `moh222salah/tasks`).
Nothing has been deployed anywhere except an isolated test bench. Run the stages in order, first with
`SITE=test.next.nds-technology.com`, then (only after the test site passes) with `SITE=ndserpsa.nds-sa.com`.
Never run any of this on the Egyptian bench. Each block starts with `SITE=` and finds the bench by itself, so no
variable has to survive between blocks. Blocks run in a subshell: a failure stops the block and never closes SSH.

| Stage | Block | Effect |
| --- | --- | --- |
| 1 | Discovery | read-only |
| 2A | Checkpoint and backup | writes a backup and a checkpoint folder |
| 2B | Get the code at the pinned commit and build assets | disk only: `apps/`, pip environment, assets |
| 2C | Restart | brief interruption for every site on the bench (approval needed) |
| 2D | Install on the site | DB writes for this site only |
| 3A | Verify | read-only |
| 3B | Recovery R1 / R2 / R3 | only when a stop condition is met |

Verification on a real site is read-only. Create throw-away handovers only on the test site, never on production.
What the install adds: 16 DocTypes, 10 roles (`NDS ...`), 14 reports, 4 Desk pages, a workspace and sidebar, one Kanban
board, CSS/JS bundles, two scheduler jobs. It does not edit Frappe/ERPNext code, add Custom Fields, or change existing records.

See the chat message that accompanies this commit for the copy-ready blocks; they are reproduced here.

## Stage 1: discovery (read-only)

```bash
( SITE=test.next.nds-technology.com
B=$(for d in ~/frappe-bench /home/*/frappe-bench /opt/*/frappe-bench; do [ -d "$d/sites/$SITE" ] && echo "$d"; done | head -1)
echo "BENCH=$B SITE=$SITE"
if [ -z "$B" ]; then echo "STOP: site folder not found"; else
cd "$B"
echo "--- sites:"; ls -d sites/*/ | grep -v assets
echo "--- versions:"; bench version
echo "--- tools:"; ./env/bin/python -V; node -v; yarn -v
echo "--- apps on site:"; bench --site "$SITE" list-apps
echo "--- app repos:"; for a in apps/*/; do echo "$a $(git -C $a rev-parse --short HEAD 2>/dev/null) dirty=$(git -C $a status --porcelain 2>/dev/null | wc -l)"; done
echo "--- nds_operations on disk:"; ls -d apps/nds_operations 2>&1
echo "--- remote HEAD (expect 7b8e31b874c8...):"; GIT_TERMINAL_PROMPT=0 git ls-remote https://github.com/moh222salah/tasks refs/heads/main 2>&1 | head -1
echo "--- disk:"; df -h "$B" | tail -1
echo "--- processes:"; ps -eo args | grep -E "gunicorn|supervisord|bench (serve|schedule|worker)" | grep -v grep | cut -c1-150 | head -6
bench --site "$SITE" console <<'PY'
import frappe
print("COUNTS", {d: frappe.db.count(d) for d in ["Employee","Task","Project","Sales Invoice","GL Entry","User","Role","Workspace","Kanban Board"]})
print("Client Scripts on Task:", frappe.get_all("Client Script", filters={"dt":"Task","enabled":1}, pluck="name"))
print("Workflows on Task:", frappe.get_all("Workflow", filters={"document_type":"Task","is_active":1}, pluck="name"))
print("Custom Fields on Task:", frappe.get_all("Custom Field", filters={"dt":"Task"}, pluck="fieldname"))
print("Existing NDS doctypes:", frappe.get_all("DocType", filters={"name":["like","NDS %"]}, pluck="name"))
print("Existing NDS roles:", frappe.get_all("Role", filters={"name":["like","NDS %"]}, pluck="name"))
print("Pages:", frappe.get_all("Page", filters={"name":["like","nds-%"]}, pluck="name"), "Workspaces:", frappe.get_all("Workspace", filters={"name":["like","NDS%"]}, pluck="name"))
print("Kanban:", frappe.db.exists("Kanban Board","NDS Tasks by Status"))
hk = frappe.get_hooks()
print("doctype_js Task:", hk.get("doctype_js",{}).get("Task"))
print("doc_events Task:", hk.get("doc_events",{}).get("Task"))
print("installed:", frappe.get_installed_apps())
print("scheduler disabled:", frappe.is_scheduler_disabled())
PY
fi )
```

Stop and review if: another real site shares the bench besides the test copy and the Saudi site; Python is below 3.14;
Frappe/ERPNext are not v16; `apps/nds_operations` exists with other contents; the remote HEAD is not the pinned commit;
any of the Client Script, Workflow, Custom Field, NDS doctype or NDS role lists is non-empty; or `doc_events` /
`doctype_js` for Task already come from another app (check it does not clash).

## Stage 2A: checkpoint and backup

```bash
( set -euo pipefail
SITE=test.next.nds-technology.com
B=$(for d in ~/frappe-bench /home/*/frappe-bench /opt/*/frappe-bench; do [ -d "$d/sites/$SITE" ] && echo "$d"; done | head -1)
[ -n "$B" ] || { echo "STOP: site folder not found"; false; }
cd "$B"
if bench --site "$SITE" list-apps | grep -qE '^nds_operations'; then echo "STOP: already installed on $SITE"; false; fi
CK=~/nds-ops-checkpoint-$(date +%Y%m%d-%H%M%S); mkdir -p "$CK"; chmod 700 "$CK"
bench version > "$CK/versions.txt"; cp sites/apps.txt "$CK/apps.txt"
cp "sites/$SITE/site_config.json" "$CK/site_config.json"; chmod 600 "$CK/site_config.json"
./env/bin/pip freeze > "$CK/pip-freeze.txt"
for a in apps/*/; do echo "$a $(git -C $a rev-parse HEAD)"; done > "$CK/app-heads.txt"
bench --site "$SITE" backup --with-files
BK="sites/$SITE/private/backups"
DB=$(ls -t $BK/*-database.sql.gz | head -1); PU=$(ls -t $BK/*-private-files.tar | head -1); PB=$(ls -t $BK/*-files.tar | grep -v private | head -1)
gzip -t "$DB"; tar -tf "$PU" >/dev/null; tar -tf "$PB" >/dev/null
sha256sum "$DB" "$PU" "$PB" | tee "$CK/backup.sha256"
echo "CHECKPOINT OK: $CK" )
```

Condition: it must print `CHECKPOINT OK`. Otherwise stop; nothing was changed except the new backup files.

## Stage 2B: code at the pinned commit and assets (no database, no restart)

```bash
( set -euo pipefail
SITE=test.next.nds-technology.com
B=$(for d in ~/frappe-bench /home/*/frappe-bench /opt/*/frappe-bench; do [ -d "$d/sites/$SITE" ] && echo "$d"; done | head -1)
[ -n "$B" ] || { echo "STOP: site folder not found"; false; }
cd "$B"
PIN=7b8e31b874c8c34397c1057b13476ea3402d3bef
if [ -d apps/nds_operations ]; then echo "apps/nds_operations already on disk"; else GIT_TERMINAL_PROMPT=0 bench get-app https://github.com/moh222salah/tasks --branch main --skip-assets; fi
H=$(git -C apps/nds_operations rev-parse HEAD); echo "HEAD=$H"
[ "$H" = "$PIN" ] || { echo "STOP: HEAD is not the verified commit"; false; }
echo "dirty files: $(git -C apps/nds_operations status --porcelain | wc -l)"
bench build --app nds_operations
echo "2B OK" )
```

If the repository is private and the server has no credentials, the clone stops by itself (no prompt, no token in the command).

## Stage 2C: restart (approval needed; all sites on this bench blink for a few seconds)

Why before the install: the running workers started before the package existed, so they are restarted while the site
does not use the app yet. Skip this on the second site if the same bench was already restarted after 2B.

```bash
cd ~/frappe-bench && bench restart
```

Use your usual restart command instead if the process list in stage 1 shows something other than supervisor.

## Stage 2D: install on the site (the only database write)

```bash
( set -euo pipefail
SITE=test.next.nds-technology.com
B=$(for d in ~/frappe-bench /home/*/frappe-bench /opt/*/frappe-bench; do [ -d "$d/sites/$SITE" ] && echo "$d"; done | head -1)
[ -n "$B" ] || { echo "STOP: site folder not found"; false; }
cd "$B"
bench --site "$SITE" install-app nds_operations
bench --site "$SITE" clear-cache
bench --site "$SITE" list-apps )
```

## Stage 3A: verification (read-only)

```bash
( SITE=test.next.nds-technology.com; URL=https://test.next.nds-technology.com
B=$(for d in ~/frappe-bench /home/*/frappe-bench /opt/*/frappe-bench; do [ -d "$d/sites/$SITE" ] && echo "$d"; done | head -1)
cd "$B"
for p in /api/method/ping /login /assets/nds_operations/css/nds_operations.css /assets/nds_operations/js/nds_operations.js; do
  echo "$(curl -s -o /dev/null -w '%{http_code}' "$URL$p") $p"; done
echo "--- error logs (last 300 lines, NDS or Traceback):"
tail -n 300 logs/web.error.log logs/worker.error.log 2>/dev/null | grep -ciE "nds_operations|Traceback" || true
bench --site "$SITE" console <<'PY'
import frappe
print("COUNTS", {d: frappe.db.count(d) for d in ["Employee","Task","Project","Sales Invoice","GL Entry","User","Role","Workspace","Kanban Board"]})
print("NDS doctypes:", frappe.db.count("DocType", {"name": ["like", "NDS %"]}), "(expect 16)")
print("NDS roles:", frappe.db.count("Role", {"name": ["like", "NDS %"]}), "(expect 10)")
print("Reports:", frappe.db.count("Report", {"module": "NDS Enterprise Operations"}), "(expect 14)")
print("Pages:", frappe.get_all("Page", filters={"name": ["like", "nds-%"]}, pluck="name"))
print("Workspace:", frappe.db.exists("Workspace", "NDS Enterprise Operations"), "Kanban:", frappe.db.exists("Kanban Board", "NDS Tasks by Status"))
hk = frappe.get_hooks()
print("Task hooks:", hk.get("doctype_js", {}).get("Task"), hk.get("doc_events", {}).get("Task"))
print("installed:", frappe.get_installed_apps())
PY
)
```

Acceptance: the three `/assets` and `/api/method/ping` answers are 200; no new Traceback mentioning the app; counts of
Employee, Task, Project, Sales Invoice, GL Entry and User equal the stage 1 numbers (Role +10, Kanban Board +1, Workspace +1).
Then open as a System Manager: `/desk/nds-enterprise-operations`, `/desk/nds-handover-center`,
`/desk/nds-operations-dashboard`, `/desk/nds-org-chart`, `/desk/nds-profile`, and one ordinary Task form and Employee form
(they must look and save as before). On the test site only, run one throw-away handover end to end.

## Stage 3B: recovery

R1, first choice, before real handovers exist:

```bash
( set -euo pipefail
SITE=test.next.nds-technology.com
B=$(for d in ~/frappe-bench /home/*/frappe-bench /opt/*/frappe-bench; do [ -d "$d/sites/$SITE" ] && echo "$d"; done | head -1)
[ -n "$B" ] || { echo "STOP: site folder not found"; false; }
cd "$B"
bench --site "$SITE" uninstall-app nds_operations --yes
bench --site "$SITE" clear-cache
bench --site "$SITE" console <<'PY'
import frappe
for r in frappe.get_all("Role", filters={"name": ["like", "NDS %"]}, pluck="name"):
    if frappe.db.count("Has Role", {"role": r}) == 0:
        frappe.delete_doc("Role", r, force=1, ignore_permissions=True); print("deleted role", r)
    else:
        print("kept role (users hold it):", r)
if frappe.db.exists("Kanban Board", "NDS Tasks by Status"):
    frappe.delete_doc("Kanban Board", "NDS Tasks by Status", force=1, ignore_permissions=True); print("deleted kanban board")
frappe.db.commit()
print("installed:", frappe.get_installed_apps())
PY
)
```

R2, if anything else looks wrong or real handovers exist: restore the stage 2A backup. This discards everything written to
the site after the backup. It asks for the MariaDB root password at the prompt (do not put it in the command).

```bash
cd ~/frappe-bench && SITE=test.next.nds-technology.com
BK=sites/$SITE/private/backups
bench --site "$SITE" set-maintenance-mode on
bench --site "$SITE" restore "$(ls -t $BK/*-database.sql.gz | head -1)" \
  --with-private-files "$(ls -t $BK/*-private-files.tar | head -1)" \
  --with-public-files "$(ls -t $BK/*-files.tar | grep -v private | head -1)"
bench --site "$SITE" set-maintenance-mode off
bench --site "$SITE" clear-cache
```

R3, remove the code, only when no site still has the app installed (check each with `bench --site <s> list-apps`):

```bash
cd ~/frappe-bench && bench remove-app nds_operations && bench restart
```

After any recovery: compare `bench version` and `~/nds-ops-checkpoint-*/versions.txt`, rerun the 3A HTTP checks and
confirm the counts equal the stage 1 numbers.
