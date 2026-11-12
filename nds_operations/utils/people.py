import frappe
from frappe.utils import getdate, nowdate

from nds_operations.constants import TEAM_MEMBERSHIP


def get_employee_for_user(user=None, fieldname="name"):
	"""Active Employee linked to a user, or None."""
	user = user or frappe.session.user
	return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, fieldname)


def get_active_memberships(employee=None, team=None, on_date=None, fields=None, extra_filters=None):
	"""Memberships that are in force on a date (from_date <= date and no end date or end date >= date)."""
	on_date = getdate(on_date or nowdate())
	filters = {"from_date": ("<=", on_date)}
	if employee:
		filters["employee"] = employee
	if team:
		filters["team"] = team
	if extra_filters:
		filters.update(extra_filters)
	return frappe.get_all(
		TEAM_MEMBERSHIP,
		filters=filters,
		or_filters=[["to_date", "is", "not set"], ["to_date", ">=", on_date]],
		fields=fields or ["name", "team", "employee", "role_in_team", "is_primary"],
		order_by="is_primary desc, from_date asc",
	)


def get_primary_team(employee):
	"""The employee's primary active team, or the earliest active team when none is flagged."""
	rows = get_active_memberships(employee=employee)
	return rows[0].team if rows else None


def is_active_member(employee, team):
	return bool(get_active_memberships(employee=employee, team=team))


def get_employee_snapshot(employee):
	"""Display data of an employee used to fill sender/receiver blocks."""
	if not employee:
		return frappe._dict()
	row = frappe.db.get_value(
		"Employee",
		employee,
		["name", "employee_name", "department", "designation", "user_id", "status", "company"],
		as_dict=True,
	)
	if not row:
		return frappe._dict()
	row.email = frappe.db.get_value("User", row.user_id, "email") if row.user_id else None
	return row
