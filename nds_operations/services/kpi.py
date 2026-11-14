"""KPI calculations for the performance reports.

Fairness rules (also printed under every report):
- Cancelled and Template tasks never count.
- A completed task is "excused" from on-time scoring when a handover was waiting on the receiver across its due
  date: that delay belongs to the other party, not to the owner.
- The task owner is the one in the ownership ledger now (see reports.current_owners), never the creator.
- Rates with no denominator are None (shown empty), never 0 or 100.
Everything is read through frappe.get_list, so a viewer only gets figures for records he may read.
"""

import frappe
from frappe.utils import date_diff, get_datetime, getdate

from nds_operations.constants import ACCEPTED, CLARIFICATION, HANDOVER, HANDOVER_REVIEW, REJECTED
from nds_operations.reports import current_owners, hours_between

DECIDED = (ACCEPTED, REJECTED)
HANDOVER_FIELDS = [
	"name",
	"task",
	"root_handover",
	"version_no",
	"handover_status",
	"sender_user",
	"receiver_user",
	"sender_department",
	"receiver_department",
	"sender_team",
	"receiver_team",
	"submitted_at",
	"decided_at",
]

METHODOLOGY = (
	"<b>How the numbers are calculated</b><ul>"
	"<li><b>First-pass rate</b> = accepted handovers that were version 1 and had no clarification round ÷ decided handovers "
	"(accepted + rejected).</li>"
	"<li><b>Rework rate</b> = handovers that are a revision (version 2 or later) ÷ all submitted handovers.</li>"
	"<li><b>Rejection rate</b> = rejected ÷ decided handovers.</li>"
	"<li><b>Handover quality score</b> = 50% first-pass rate + 30% (100 - rework rate) + 20% (100 - rejection rate); "
	"empty when nothing was decided.</li>"
	"<li><b>On-time rate</b> = completed tasks finished on or before the due date ÷ completed tasks that had a due date, "
	"after removing excused tasks (a handover was waiting on the receiver across the due date).</li>"
	"<li><b>Response hours</b> = submission to decision, for the receiver. Cancelled and withdrawn work is excluded. "
	"Owners come from the ownership ledger, so reassigning a task does not move past results onto someone else.</li></ul>"
)


def pct(part, whole):
	return round(100.0 * part / whole, 1) if whole else None


def mean(values):
	values = [v for v in values if v is not None]
	return round(sum(values) / len(values), 1) if values else None


def quality_score(first_pass, rework, rejection):
	if first_pass is None:
		return None
	return round(0.5 * first_pass + 0.3 * (100 - (rework or 0)) + 0.2 * (100 - (rejection or 0)), 1)


def get_handovers(filters=None):
	conditions = {"docstatus": 1, "handover_status": ("!=", "Withdrawn")}
	conditions.update(filters or {})
	return frappe.get_list(HANDOVER, filters=conditions, fields=HANDOVER_FIELDS, limit_page_length=0)


def clarified_handovers(names):
	if not names:
		return set()
	return set(
		frappe.get_list(
			HANDOVER_REVIEW,
			filters={"handover": ("in", list(names)), "decision": CLARIFICATION},
			pluck="handover",
			limit_page_length=0,
		)
	)


def is_first_pass(row, clarified):
	return row.handover_status == ACCEPTED and row.version_no == 1 and row.name not in clarified


def handover_group_stats(rows, sender_key, receiver_key):
	"""Per group (user, department or team): what it sent and how its receivers answered."""
	clarified = clarified_handovers({r.name for r in rows})
	groups = {}

	def group(key):
		return groups.setdefault(
			key,
			frappe._dict(
				sent=0,
				decided=0,
				accepted=0,
				rejected=0,
				first_pass=0,
				revisions=0,
				received_decided=0,
				response_hours=[],
				pending=0,
			),
		)

	for row in rows:
		sender = row.get(sender_key)
		if sender:
			g = group(sender)
			g.sent += 1
			g.revisions += 1 if (row.version_no or 1) > 1 else 0
			if row.handover_status in DECIDED:
				g.decided += 1
				g.accepted += 1 if row.handover_status == ACCEPTED else 0
				g.rejected += 1 if row.handover_status == REJECTED else 0
				g.first_pass += 1 if is_first_pass(row, clarified) else 0
		receiver = row.get(receiver_key)
		if receiver:
			g = group(receiver)
			if row.handover_status in DECIDED:
				g.received_decided += 1
				g.response_hours.append(hours_between(row.submitted_at, row.decided_at))
			elif row.handover_status in ("Pending Acceptance", "Under Review"):
				g.pending += 1

	for g in groups.values():
		g.first_pass_rate = pct(g.first_pass, g.decided)
		g.rework_rate = pct(g.revisions, g.sent)
		g.rejection_rate = pct(g.rejected, g.decided)
		g.quality_score = quality_score(g.first_pass_rate, g.rework_rate, g.rejection_rate)
		g.avg_response_hours = mean(g.response_hours)
	return groups


def completed_tasks(filters=None):
	"""Completed tasks (never Cancelled/Template) with owner, cycle time and on-time verdict."""
	conditions = {"status": "Completed", "completed_on": ("is", "set")}
	conditions.update(filters or {})
	tasks = frappe.get_list(
		"Task",
		filters=conditions,
		fields=["name", "subject", "department", "project", "exp_end_date", "completed_on", "creation"],
		limit_page_length=0,
	)
	names = [t.name for t in tasks]
	owners = current_owners(names)
	waits = {}
	if names:
		for h in frappe.get_list(
			HANDOVER,
			filters={"task": ("in", names), "docstatus": 1, "handover_status": ("!=", "Withdrawn")},
			fields=["task", "submitted_at", "decided_at"],
			limit_page_length=0,
		):
			waits.setdefault(h.task, []).append(h)

	for task in tasks:
		task.owner_user = owners.get(task.name)
		task.cycle_days = max(date_diff(task.completed_on, getdate(task.creation)), 0)
		task.has_due = bool(task.exp_end_date)
		task.late = bool(task.exp_end_date and getdate(task.completed_on) > getdate(task.exp_end_date))
		task.excused = bool(task.late and _waited_across(waits.get(task.name, []), task.exp_end_date))
		task.on_time = bool(task.has_due and not task.late)
	return tasks


def _waited_across(handovers, due):
	due = getdate(due)
	for h in handovers:
		start = getdate(h.submitted_at)
		end = getdate(h.decided_at) if h.decided_at else getdate()
		if start <= due <= end:
			return True
	return False


def on_time_rate(tasks):
	scored = [t for t in tasks if t.has_due and not t.excused]
	return pct(sum(1 for t in scored if t.on_time), len(scored))
