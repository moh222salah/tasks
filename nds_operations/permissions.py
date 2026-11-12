"""Server-side scoping for the handover module.

Who sees what (enforced in list queries and on single documents, never only in the UI):
- the sender sees his own handovers, including drafts (drafts are private to the sender);
- the receiver sees handovers addressed to him once they are submitted;
- a Team Leader sees submitted handovers of the teams he leads;
- a Department Manager sees submitted handovers of the departments he manages (and sub-departments);
- Executive Management and Read Only Auditor see every submitted handover;
- System Manager and Operations Manager see everything.

Nobody edits or deletes a submitted handover, its reviews, its history or the ownership ledger.
Frappe lets the Administrator bypass has_permission hooks, so the controllers enforce the same rules.
"""

import frappe

from nds_operations.constants import (
	HANDOVER,
	NDS_ROLES,
	ROLE_AUDITOR,
	ROLE_DEPT_MANAGER,
	ROLE_EXECUTIVE,
	ROLE_OPS_MANAGER,
	ROLE_TEAM_LEADER,
)
from nds_operations.utils.people import get_active_memberships

WRITE_PTYPES = {"write", "create", "delete", "submit", "cancel", "amend"}
H = "`tabNDS Task Handover`"


def has_app_permission():
	if frappe.session.user == "Administrator":
		return True
	roles = set(frappe.get_roles())
	return bool(roles & ({"System Manager", "Employee"} | set(NDS_ROLES)))


def clear_scope_cache():
	frappe.local.nds_scope_cache = {}


def get_scope(user=None):
	"""What a user may see. Cached per request; call clear_scope_cache() after changing roles or teams."""
	user = user or frappe.session.user
	cache = getattr(frappe.local, "nds_scope_cache", None)
	if cache is None:
		cache = frappe.local.nds_scope_cache = {}
	if user not in cache:
		cache[user] = _build_scope(user)
	return cache[user]


def _build_scope(user):
	roles = set(frappe.get_roles(user))
	scope = frappe._dict(
		user=user,
		roles=roles,
		full=user == "Administrator" or bool(roles & {"System Manager", ROLE_OPS_MANAGER}),
		submitted_all=bool(roles & {ROLE_EXECUTIVE, ROLE_AUDITOR}),
		departments=[],
		teams=[],
	)
	if ROLE_DEPT_MANAGER in roles:
		scope.departments = get_managed_departments(user)
	if ROLE_TEAM_LEADER in roles:
		scope.teams = get_led_teams(user)
	return scope


def _employees_of(user):
	"""Active Employee records linked to the user. Resolved live so that scope never goes stale
	when an Employee is re-linked to another user."""
	return frappe.get_all("Employee", filters={"user_id": user, "status": "Active"}, pluck="name")


def _sub_departments(department):
	row = frappe.db.get_value("Department", department, ["lft", "rgt"], as_dict=True)
	if not row or row.lft is None or row.rgt is None or row.rgt - row.lft <= 1:
		return []
	return frappe.get_all(
		"Department", filters={"lft": (">", row.lft), "rgt": ("<", row.rgt)}, pluck="name"
	)


def get_managed_departments(user):
	"""Departments where the user is manager or deputy (active profiles), plus their sub-departments."""
	employees = _employees_of(user)
	if not employees:
		return []
	own = frappe.get_all(
		"NDS Department Profile",
		filters={"is_active": 1},
		or_filters={"department_manager": ("in", employees), "deputy_manager": ("in", employees)},
		pluck="department",
	)
	departments = set(own)
	for department in own:
		departments.update(_sub_departments(department))
	return sorted(departments)


def get_led_teams(user):
	"""Active teams the user leads (team lead, deputy lead, or a Leader/Deputy Leader membership)."""
	employees = _employees_of(user)
	if not employees:
		return []
	teams = set(
		frappe.get_all(
			"NDS Team",
			filters={"is_active": 1},
			or_filters={"team_lead": ("in", employees), "deputy_lead": ("in", employees)},
			pluck="name",
		)
	)
	for employee in employees:
		for row in get_active_memberships(employee=employee, fields=["team", "role_in_team"]):
			if row.role_in_team in ("Leader", "Deputy Leader"):
				teams.add(row.team)
	# keep only teams that are still active
	if teams:
		teams = set(
			frappe.get_all("NDS Team", filters={"name": ("in", list(teams)), "is_active": 1}, pluck="name")
		)
	return sorted(teams)


def _in(values):
	return ", ".join(frappe.db.escape(v) for v in values)


def handover_query_conditions(user=None, doctype=None):
	user = user or frappe.session.user
	scope = get_scope(user)
	if scope.full:
		return ""

	me = frappe.db.escape(user)
	visible = [f"{H}.receiver_user = {me}"]
	if scope.submitted_all:
		visible.append("1 = 1")
	if scope.departments:
		departments = _in(scope.departments)
		visible += [
			f"{H}.department in ({departments})",
			f"{H}.sender_department in ({departments})",
			f"{H}.receiver_department in ({departments})",
		]
	if scope.teams:
		teams = _in(scope.teams)
		visible += [
			f"{H}.team in ({teams})",
			f"{H}.sender_team in ({teams})",
			f"{H}.receiver_team in ({teams})",
		]
	# Drafts (docstatus 0) are visible to the sender only; submitted records follow the scope above.
	return f"({H}.sender_user = {me} or ({H}.docstatus = 1 and ({' or '.join(visible)})))"


def _by_handover(table, user):
	condition = handover_query_conditions(user)
	if not condition:
		return ""
	return f"{table}.`handover` in (select `name` from {H} where {condition})"


def review_query_conditions(user=None, doctype=None):
	return _by_handover("`tabNDS Handover Review`", user or frappe.session.user)


def history_query_conditions(user=None, doctype=None):
	return _by_handover("`tabNDS Handover History`", user or frappe.session.user)


def ownership_query_conditions(user=None, doctype=None):
	user = user or frappe.session.user
	by_handover = _by_handover("`tabNDS Ownership History`", user)
	if not by_handover:
		return ""
	me = frappe.db.escape(user)
	return f"(`tabNDS Ownership History`.from_user = {me} or `tabNDS Ownership History`.to_user = {me} or {by_handover})"


def handover_has_permission(doc, ptype=None, user=None, debug=False):
	"""Hooks can only deny: role permissions decide first, this narrows them to the user's scope."""
	user = user or frappe.session.user
	if ptype == "create" or doc.is_new():
		return True

	if ptype in WRITE_PTYPES:
		# a submitted handover is immutable; only the sender touches his own drafts
		return doc.docstatus == 0 and doc.sender_user == user

	scope = get_scope(user)
	if scope.full or doc.sender_user == user:
		return True
	if doc.docstatus != 1:
		return False
	if doc.receiver_user == user or scope.submitted_all:
		return True
	if scope.departments and {doc.department, doc.sender_department, doc.receiver_department} & set(
		scope.departments
	):
		return True
	if scope.teams and {doc.team, doc.sender_team, doc.receiver_team} & set(scope.teams):
		return True
	return False


def record_has_permission(doc, ptype=None, user=None, debug=False):
	"""Reviews and history rows: read-only, visible to whoever can read their handover."""
	user = user or frappe.session.user
	if ptype in WRITE_PTYPES:
		return False
	if not doc.get("handover"):
		return False
	return frappe.has_permission(HANDOVER, "read", doc=doc.handover, user=user)


def ownership_has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if ptype in WRITE_PTYPES:
		return False
	if user in (doc.get("from_user"), doc.get("to_user")):
		return True
	if doc.get("handover"):
		return frappe.has_permission(HANDOVER, "read", doc=doc.handover, user=user)
	return bool(get_scope(user).full)
