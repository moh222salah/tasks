"""Organization chart data: departments, their teams and members, as the current user may read them."""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from nds_operations.constants import DEPARTMENT_PROFILE, NDS_ROLES, TEAM, TEAM_MEMBERSHIP
from nds_operations.reports import CLOSED_TASKS

MEMBER_LIMIT = 12


def _assert_access():
	roles = set(frappe.get_roles())
	if frappe.session.user == "Administrator" or roles & ({"System Manager", "Employee"} | set(NDS_ROLES)):
		return
	frappe.throw(_("You do not have access to the organization chart."), frappe.PermissionError)


@frappe.whitelist(methods=["GET"])
def get_org_chart(company=None):
	_assert_access()
	today = getdate(nowdate())
	dept_filters = {"disabled": 0}
	if company:
		dept_filters["company"] = company
	# The structure itself (names and parents) is company-wide information; an Employee-role reader only gets
	# "select" on Department, which hides everything but the id from get_list. Teams, memberships and task
	# counts below stay permission-scoped.
	departments = frappe.get_all(
		"Department",
		filters=dept_filters,
		fields=["name", "department_name", "parent_department", "company", "is_group"],
		order_by="lft asc",
		limit_page_length=0,
	)
	profiles = {
		p.department: p
		for p in frappe.get_all(
			DEPARTMENT_PROFILE,
			filters={"is_active": 1},
			fields=["department", "department_manager", "manager_user"],
			limit_page_length=0,
		)
	}
	names = {
		e.name: e.employee_name
		for e in frappe.get_all(
			"Employee",
			filters={
				"name": (
					"in",
					[p.department_manager for p in profiles.values() if p.department_manager] or ["-"],
				)
			},
			fields=["name", "employee_name"],
			limit_page_length=0,
		)
	}
	teams = frappe.get_list(
		TEAM,
		filters={"is_active": 1},
		fields=["name", "team_name", "department", "team_lead", "team_lead_name"],
		order_by="team_name asc",
		limit_page_length=0,
	)
	members = {}
	for m in frappe.get_list(
		TEAM_MEMBERSHIP,
		filters={"from_date": ("<=", today)},
		or_filters=[["to_date", "is", "not set"], ["to_date", ">=", today]],
		fields=["team", "employee_name", "role_in_team"],
		limit_page_length=0,
	):
		members.setdefault(m.team, []).append({"name": m.employee_name, "role": m.role_in_team})
	open_tasks = {
		r.department: r.total
		for r in frappe.get_list(
			"Task",
			filters={"status": ("not in", CLOSED_TASKS), "department": ("is", "set")},
			fields=["department", {"COUNT": "name", "as": "total"}],
			group_by="department",
			limit_page_length=0,
		)
	}
	by_department = {}
	for team in teams:
		rows = members.get(team.name, [])
		by_department.setdefault(team.department, []).append(
			{
				"name": team.name,
				"title": team.team_name,
				"lead": team.team_lead_name,
				"member_count": len(rows),
				"members": rows[:MEMBER_LIMIT],
				"more": max(len(rows) - MEMBER_LIMIT, 0),
			}
		)
	return {
		"departments": [
			{
				"name": d.name,
				"title": d.department_name,
				"parent": d.parent_department if d.parent_department != "All Departments" else None,
				"company": d.company,
				"is_group": d.is_group,
				"manager": names.get((profiles.get(d.name) or {}).get("department_manager")),
				"open_tasks": open_tasks.get(d.name, 0),
				"teams": by_department.get(d.name, []),
			}
			for d in departments
			if d.name != "All Departments"
		]
	}
