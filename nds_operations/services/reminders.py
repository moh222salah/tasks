"""Scheduled reminders. Each reminder is sent once per handover; the history row is the proof and the guard."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_datetime, getdate, now_datetime, nowdate

from nds_operations.constants import (
	DECIDABLE_STATUSES,
	HANDOVER,
	HANDOVER_HISTORY,
	SETTINGS,
)
from nds_operations.reports import CLOSED_TASKS, current_owners
from nds_operations.services.history import log_event
from nds_operations.services.notifications import REMINDER, manager_users, notify, notify_document

DUE_SOON = "Reminder Sent"
OVERDUE = "Overdue Alert"
ESCALATED = "Escalated"


def _enabled(settings=None):
	"""A Single's new Check field loads as 0 on a site that existed before it. Only a stored value counts:
	never saved means the default, which is on."""
	rows = frappe.db.sql(
		"select `value` from `tabSingles` where `doctype` = %s and `field` = 'enable_reminders'", SETTINGS
	)
	stored = rows[0][0] if rows else None
	return True if stored in (None, "") else bool(cint(stored))


def _already(handover, event):
	return frappe.db.exists(HANDOVER_HISTORY, {"handover": handover, "event_type": event})


def run_handover_reminders(now=None):
	"""Hourly. Returns what it sent, so the result can be tested and inspected."""
	settings = frappe.get_cached_doc(SETTINGS)
	sent = {"due_soon": 0, "overdue": 0, "escalated": 0}
	if not _enabled():
		return sent
	now = get_datetime(now) if now else now_datetime()
	lead = cint(settings.reminder_lead_hours) or 4
	escalate_after = cint(settings.escalate_overdue_after_hours) or 24

	rows = frappe.get_all(
		HANDOVER,
		filters={
			"docstatus": 1,
			"handover_status": ("in", DECIDABLE_STATUSES),
			"superseded_by": ("is", "not set"),
			"response_due": ("is", "set"),
		},
		fields=[
			"name",
			"task",
			"task_title",
			"version_no",
			"sender_user",
			"receiver_user",
			"receiver_department",
			"receiver_team",
			"response_due",
		],
	)
	for row in rows:
		hours_left = (get_datetime(row.response_due) - now).total_seconds() / 3600
		if 0 < hours_left <= lead and not _already(row.name, DUE_SOON):
			notify(
				[row.receiver_user],
				_("Handover {0} must be answered within {1} hours: {2}").format(
					row.name, lead, row.task_title
				),
				row,
				REMINDER,
			)
			log_event(row, DUE_SOON, remarks=str(row.response_due))
			sent["due_soon"] += 1
		if hours_left <= 0 and not _already(row.name, OVERDUE):
			notify(
				[row.receiver_user, row.sender_user],
				_("Handover {0} was not answered by its deadline: {1}").format(row.name, row.task_title),
				row,
				REMINDER,
			)
			log_event(row, OVERDUE, remarks=str(row.response_due))
			sent["overdue"] += 1
		if -hours_left >= escalate_after and not _already(row.name, ESCALATED):
			managers = manager_users([row.receiver_department], [row.receiver_team])
			notify(
				managers,
				_("Escalation: handover {0} has waited {1}+ hours past its deadline.").format(
					row.name, escalate_after
				),
				row,
			)
			log_event(row, ESCALATED, remarks=", ".join(managers) or _("No manager configured"))
			sent["escalated"] += 1
	return sent


def run_task_reminders(today=None):
	"""Daily. Owners of open tasks due tomorrow, or overdue, are reminded once per task and day."""
	if not _enabled():
		return 0
	today = getdate(today or nowdate())
	tasks = frappe.get_all(
		"Task",
		filters={"status": ("not in", CLOSED_TASKS), "exp_end_date": ("<=", add_days(today, 1))},
		fields=["name", "subject", "exp_end_date"],
	)
	owners = current_owners([t.name for t in tasks])
	count = 0
	for task in tasks:
		owner = owners.get(task.name)
		if not owner:
			continue
		if getdate(task.exp_end_date) < today:
			subject = _("Task {0} is overdue (due {1}): {2}")
		else:
			subject = _("Task {0} is due {1}: {2}")
		notify_document(
			[owner],
			subject.format(task.name, task.exp_end_date, task.subject),
			"Task",
			task.name,
			REMINDER,
		)
		count += 1
	return count
