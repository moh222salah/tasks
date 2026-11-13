# Deployment, verification and rollback

**Nothing in this repository has been deployed anywhere except an isolated test bench.** Installing on a real site
needs an explicit approval, a fresh backup and the steps below. Replace `SITE` with the exact site name and run the
audit on the *Saudi* bench only — never on the Egyptian one.

## 0. Read-only audit (no changes)

```bash
bench version
bench --site SITE list-apps
bench --site SITE console <<'PY'
import frappe
print("User Permissions on Employee:", frappe.db.count("User Permission", {"allow": "Employee"}))
print("Client Scripts on Task:", frappe.get_all("Client Script", filters={"dt": "Task", "enabled": 1}, pluck="name"))
print("Workflows on Task:", frappe.get_all("Workflow", filters={"document_type": "Task", "is_active": 1}, pluck="name"))
print("Existing NDS doctypes:", frappe.get_all("DocType", filters={"name": ("like", "NDS %")}, pluck="name"))
PY
```

Stop and review if any of the last three lists is non-empty: they are the places a conflict could hide.

## 1. Safe checkpoint

```bash
cd ~/frappe-bench
bench --site SITE backup --with-files
ls -t sites/SITE/private/backups | head -4          # note the newest .sql.gz and files archives
for a in frappe erpnext; do echo $a $(git -C apps/$a rev-parse --short HEAD); done > ~/pre-nds-ops-versions.txt
```

## 2. The change

```bash
bench get-app https://github.com/moh222salah/tasks --branch main      # app name: nds_operations
bench --site SITE install-app nds_operations                           # creates tables, 10 roles, rejection reasons
bench build --app nds_operations
bench --site SITE clear-cache
sudo supervisorctl restart all                                         # or your process manager's equivalent
```

What it adds: 10 DocTypes, 10 roles, a workspace, a sidebar, one page, one desktop icon, CSS/JS bundles.
What it does **not** do: edit Frappe/ERPNext code, add Custom Fields to Task/Employee, change existing records.

## 3. Immediate rollback

Preferred, if the install misbehaves and no real handovers exist yet:

```bash
bench --site SITE uninstall-app nds_operations --yes     # drops the NDS tables and removes the app's records
bench remove-app nds_operations
bench build && bench --site SITE clear-cache && sudo supervisorctl restart all
```

If anything else looks wrong (or real handovers exist): restore the checkpoint from step 1.

```bash
bench --site SITE restore sites/SITE/private/backups/<TIMESTAMP>-SITE-database.sql.gz \
  --with-public-files <files.tar> --with-private-files <private-files.tar>
```

## 4. Verification after install (read-only)

Open `/desk/nds-handover-center` as a user with the *NDS Task Sender* role, create a draft on a throw-away Task,
submit it to a second user, and confirm the Task's assignee does **not** change until that user accepts.

## Test bench

Tests create and roll back their own data and refuse to run outside the test runner. Enable them only on a throw-away
bench: `bench --site SITE set-config allow_tests true` — never on a real site.
