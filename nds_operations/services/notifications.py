import frappe
from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
from frappe.utils import cint

from nds_operations.constants import DEPARTMENT_PROFILE, HANDOVER, SETTINGS, TEAM


def notify(users, subject, handover):
	"""One in-app notification per user with a deep link to the handover; repeats are dropped."""
	if not cint(frappe.get_cached_doc(SETTINGS).enable_handover_notifications):
		return
	users = sorted({user for user in users if user and user != frappe.session.user})
	if not users:
		return
	enqueue_create_notification(
		users,
		{
			"type": "Alert",
			"subject": subject,
			"document_type": HANDOVER,
			"document_name": handover.name,
			"from_user": frappe.session.user,
		},
		dedupe_on=["document_type", "document_name", "subject"],
	)


def manager_users(departments=(), teams=()):
	"""Users of the managers / leads responsible for the given departments and teams."""
	employees = set()
	for department in filter(None, set(departments)):
		profile = frappe.db.get_value(
			DEPARTMENT_PROFILE,
			{"department": department, "is_active": 1},
			["department_manager", "deputy_manager"],
			as_dict=True,
		)
		if profile:
			employees.update(filter(None, (profile.department_manager, profile.deputy_manager)))
	for team in filter(None, set(teams)):
		row = frappe.db.get_value(
			TEAM, {"name": team, "is_active": 1}, ["team_lead", "deputy_lead"], as_dict=True
		)
		if row:
			employees.update(filter(None, (row.team_lead, row.deputy_lead)))
	if not employees:
		return []
	return frappe.get_all(
		"Employee", filters={"name": ("in", list(employees)), "user_id": ("is", "set")}, pluck="user_id"
	)
