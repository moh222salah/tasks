import frappe
from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
from frappe.utils import cint

from nds_operations.constants import (
	DEPARTMENT_PROFILE,
	HANDOVER,
	NOTIFICATION_PREFERENCE,
	SETTINGS,
	TEAM,
)

REQUIRED = "required"  # carries responsibility: always delivered
PROGRESS = "progress"
REMINDER = "reminder"
PREFERENCE_FIELD = {PROGRESS: "receive_progress_updates", REMINDER: "receive_reminders"}


def _wants(users, category):
	"""Drop users who muted an optional category. Required notifications are never filtered."""
	field = PREFERENCE_FIELD.get(category)
	if not field or not users:
		return users
	muted = set(
		frappe.get_all(NOTIFICATION_PREFERENCE, filters={"user": ("in", users), field: 0}, pluck="user")
	)
	return [user for user in users if user not in muted]


def notify_document(users, subject, doctype, name, category=REQUIRED):
	"""One in-app notification per user with a deep link; repeats of the same subject are dropped."""
	if not cint(frappe.get_cached_doc(SETTINGS).enable_handover_notifications):
		return
	users = sorted({user for user in users if user and user != frappe.session.user})
	users = _wants(users, category)
	if not users:
		return
	enqueue_create_notification(
		users,
		{
			"type": "Alert",
			"subject": subject,
			"document_type": doctype,
			"document_name": name,
			"from_user": frappe.session.user,
		},
		dedupe_on=["document_type", "document_name", "subject"],
	)


def notify(users, subject, handover, category=REQUIRED):
	notify_document(users, subject, HANDOVER, handover.name, category)


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
