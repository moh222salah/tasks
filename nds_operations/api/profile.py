"""Employee and team profiles: identity, workload and fair KPIs, read through permission-scoped queries.

A viewer only gets figures for records he may read, so the same profile shows a manager the whole picture and
a colleague only what is shared with him."""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from nds_operations.constants import HANDOVER, NDS_ROLES, TEAM, TEAM_MEMBERSHIP
from nds_operations.reports import CLOSED_TASKS, current_owners
from nds_operations.services import kpi

OPEN_HANDOVERS = ("Pending Acceptance", "Under Review")
TASK_LIMIT = 25
HANDOVER_LIMIT = 10


def _assert_access():
	roles = set(frappe.get_roles())
	if frappe.session.user == "Administrator" or roles & ({"System Manager", "Employee"} | set(NDS_ROLES)):
		return
	frappe.throw(_("You do not have access to profiles."), frappe.PermissionError)


def _employee(employee):
	if not employee:
		employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	if not employee or not frappe.db.exists("Employee", employee):
		frappe.throw(_("Employee not found."), frappe.DoesNotExistError)
	own = frappe.db.get_value("Employee", employee, "user_id") == frappe.session.user
	if not own and not frappe.has_permission("Employee", "read", employee):
		frappe.throw(_("You cannot open this employee profile."), frappe.PermissionError)
	return frappe.db.get_value(
		"Employee",
		employee,
		["name", "employee_name", "designation", "department", "user_id", "image", "reports_to"],
		as_dict=True,
	)


def _stats(users):
	"""Per user: workload, delivery and handover quality. Same rules and helpers as the reports."""
	users = {u for u in users if u}
	if not users:
		return {}, {}
	today = getdate(nowdate())
	open_tasks = frappe.get_list(
		"Task",
		filters={"status": ("not in", CLOSED_TASKS)},
		fields=["name", "subject", "exp_end_date", "project", "status"],
		limit_page_length=0,
	)
	names = [t.name for t in open_tasks]
	owners = current_owners(names)
	waiting = set()
	if names:
		waiting = set(
			frappe.get_list(
				HANDOVER,
				filters={"task": ("in", names), "docstatus": 1, "handover_status": ("in", OPEN_HANDOVERS)},
				pluck="task",
				limit_page_length=0,
			)
		)
	completed = kpi.completed_tasks()
	rows = kpi.get_handovers()
	by_user = kpi.handover_group_stats(rows, "sender_user", "receiver_user")
	scores = kpi.review_scores_by_owner()

	stats, task_rows = {}, {}
	for user in users:
		mine = [t for t in open_tasks if owners.get(t.name) == user]
		late = [t for t in mine if t.exp_end_date and getdate(t.exp_end_date) < today and t.name not in waiting]
		done = [t for t in completed if t.owner_user == user]
		g = by_user.get(user)
		stats[user] = {
			"open_tasks": len(mine),
			"overdue_tasks": len(late),
			"waiting_on_handover": sum(1 for t in mine if t.name in waiting),
			"completed_tasks": len(done),
			"on_time_rate": kpi.on_time_rate(done),
			"avg_cycle_days": kpi.mean([t.cycle_days for t in done]),
			"handovers_sent": g.sent if g else 0,
			"handovers_pending_decision": g.pending if g else 0,
			"first_pass_rate": g.first_pass_rate if g else None,
			"rejection_rate": g.rejection_rate if g else None,
			"rework_rate": g.rework_rate if g else None,
			"quality_score": g.quality_score if g else None,
			"avg_response_hours": g.avg_response_hours if g else None,
			"review_score": scores.get(user),
		}
		late_names = {t.name for t in late}
		task_rows[user] = [
			{
				"name": t.name,
				"subject": t.subject,
				"project": t.project,
				"status": t.status,
				"due": t.exp_end_date,
				"overdue": t.name in late_names,
				"waiting": t.name in waiting,
			}
			for t in sorted(mine, key=lambda x: (x.exp_end_date is None, x.exp_end_date))[:TASK_LIMIT]
		]
	return stats, task_rows


def _teams_of(employee):
	today = getdate(nowdate())
	memberships = frappe.get_list(
		TEAM_MEMBERSHIP,
		filters={"employee": employee, "from_date": ("<=", today)},
		or_filters=[["to_date", "is", "not set"], ["to_date", ">=", today]],
		fields=["team", "role_in_team", "is_primary"],
		limit_page_length=0,
	)
	titles = {
		t.name: t.team_name
		for t in frappe.get_list(
			TEAM, filters={"name": ("in", [m.team for m in memberships] or ["-"])}, fields=["name", "team_name"]
		)
	}
	return [
		{"team": m.team, "title": titles.get(m.team, m.team), "role": m.role_in_team, "primary": m.is_primary}
		for m in memberships
		if m.team in titles
	]


def _recent_handovers(user):
	return frappe.get_list(
		HANDOVER,
		filters={"docstatus": 1},
		or_filters={"sender_user": user, "receiver_user": user},
		fields=["name", "task", "handover_status", "sender_user", "receiver_user", "submitted_at"],
		order_by="submitted_at desc",
		limit_page_length=HANDOVER_LIMIT,
	)


@frappe.whitelist(methods=["GET"])
def get_employee_profile(employee=None):
	"""Profile of one employee; without an argument, the caller's own."""
	_assert_access()
	emp = _employee(employee)
	if not emp.user_id:
		return {"employee": emp, "teams": _teams_of(emp.name), "stats": None, "tasks": [], "handovers": []}
	stats, tasks = _stats([emp.user_id])
	manager = frappe.db.get_value("Employee", emp.reports_to, "employee_name") if emp.reports_to else None
	return {
		"employee": emp,
		"manager": manager,
		"teams": _teams_of(emp.name),
		"stats": stats[emp.user_id],
		"tasks": tasks[emp.user_id],
		"handovers": _recent_handovers(emp.user_id),
	}


@frappe.whitelist(methods=["GET"])
def get_team_profile(team):
	"""Profile of one team: members, workload balance and handover quality of the team as a whole."""
	_assert_access()
	if not team or not frappe.db.exists(TEAM, team):
		frappe.throw(_("Team not found."), frappe.DoesNotExistError)
	if not frappe.has_permission(TEAM, "read", team):
		frappe.throw(_("You cannot open this team."), frappe.PermissionError)
	doc = frappe.db.get_value(
		TEAM, team, ["name", "team_name", "department", "team_lead", "team_lead_name"], as_dict=True
	)
	today = getdate(nowdate())
	members = frappe.get_list(
		TEAM_MEMBERSHIP,
		filters={"team": team, "from_date": ("<=", today)},
		or_filters=[["to_date", "is", "not set"], ["to_date", ">=", today]],
		fields=["employee", "employee_name", "role_in_team"],
		limit_page_length=0,
	)
	user_of = {
		e.name: e.user_id
		for e in frappe.get_all(
			"Employee",
			filters={"name": ("in", [m.employee for m in members] or ["-"])},
			fields=["name", "user_id"],
			limit_page_length=0,
		)
	}
	stats, _tasks = _stats([user_of.get(m.employee) for m in members])
	rows = kpi.get_handovers()
	group = kpi.handover_group_stats(rows, "sender_team", "receiver_team").get(team)
	people = []
	for m in members:
		s = stats.get(user_of.get(m.employee))
		people.append(
			{
				"employee": m.employee,
				"name": m.employee_name,
				"role": m.role_in_team,
				"open_tasks": s["open_tasks"] if s else None,
				"overdue_tasks": s["overdue_tasks"] if s else None,
				"completed_tasks": s["completed_tasks"] if s else None,
				"on_time_rate": s["on_time_rate"] if s else None,
			}
		)
	loads = [p["open_tasks"] for p in people if p["open_tasks"] is not None]
	average = sum(loads) / len(loads) if loads else 0
	for p in people:
		# a member is "heavy" when he carries clearly more than the team average (and at least 3 open tasks)
		p["heavy"] = bool(p["open_tasks"] is not None and p["open_tasks"] >= 3 and p["open_tasks"] > 1.5 * average)
	return {
		"team": doc,
		"members": people,
		"totals": {
			"open_tasks": sum(loads),
			"overdue_tasks": sum(p["overdue_tasks"] or 0 for p in people),
			"completed_tasks": sum(p["completed_tasks"] or 0 for p in people),
			"average_open_per_member": round(average, 1) if loads else None,
		},
		"handovers": {
			"sent": group.sent if group else 0,
			"pending_decision": group.pending if group else 0,
			"first_pass_rate": group.first_pass_rate if group else None,
			"rejection_rate": group.rejection_rate if group else None,
			"quality_score": group.quality_score if group else None,
			"avg_response_hours": group.avg_response_hours if group else None,
		},
	}
