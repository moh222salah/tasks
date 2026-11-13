import frappe
from frappe import _

from nds_operations.permissions import get_scope


def last_sequence(task):
	"""Highest ledger position of a task.

	A locking read: inside a transaction a plain SELECT may return a snapshot taken before another
	transfer committed, and this value decides whether a handover is still valid.
	"""
	return frappe.db.sql(
		"select coalesce(max(`sequence`), 0) from `tabNDS Ownership History` where `task` = %s for update",
		task,
	)[0][0]


def get_current_owner(task):
	"""Who is responsible now: the last ledger row, else the first open assignee, else the task creator."""
	row = frappe.db.sql(
		"select `to_user` from `tabNDS Ownership History` where `task` = %s "
		"order by `sequence` desc limit 1 for update",
		task,
	)
	if row:
		return row[0][0]
	row = frappe.db.sql(
		"select `allocated_to` from `tabToDo` where `reference_type` = 'Task' and `reference_name` = %s "
		"and `status` = 'Open' order by `creation` asc limit 1",
		task,
	)
	if row:
		return row[0][0]
	return frappe.db.get_value("Task", task, "owner")


def assert_can_hand_over(task, user=None):
	"""Only the current owner, or a manager whose scope covers the task, may hand a task over."""
	user = user or frappe.session.user
	scope = get_scope(user)
	if scope.full or get_current_owner(task.name) == user:
		return
	if task.get("department") and task.department in scope.departments:
		return
	frappe.throw(
		_("Only the current owner of {0} (or a manager of its department) can hand it over.").format(
			frappe.bold(task.name)
		),
		frappe.PermissionError,
	)
