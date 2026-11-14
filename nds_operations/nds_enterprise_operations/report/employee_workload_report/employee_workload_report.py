import frappe
from frappe.utils import add_days, getdate, nowdate

from nds_operations.constants import HANDOVER
from nds_operations.reports import col, get_tasks, link


def execute(filters=None):
	tasks = get_tasks(filters, open_only=True)
	soon = add_days(getdate(nowdate()), 7)
	people = {}
	for task in tasks:
		row = people.setdefault(
			task.current_owner or "",
			frappe._dict(
				user=task.current_owner,
				open_tasks=0,
				overdue=0,
				due_in_7_days=0,
				estimated_hours=0.0,
				urgent=0,
				awaiting_my_decision=0,
			),
		)
		row.open_tasks += 1
		row.overdue += 1 if task.days_overdue else 0
		row.due_in_7_days += (
			1 if task.exp_end_date and getdate(nowdate()) <= getdate(task.exp_end_date) <= soon else 0
		)
		row.estimated_hours += task.expected_time or 0
		row.urgent += 1 if task.priority in ("High", "Urgent") else 0

	# handovers waiting for each person's decision are workload too
	for r in frappe.get_list(
		HANDOVER,
		filters={"docstatus": 1, "handover_status": ("in", ("Pending Acceptance", "Under Review"))},
		fields=["receiver_user", {"COUNT": "name", "as": "total"}],
		group_by="receiver_user",
	):
		row = people.setdefault(
			r.receiver_user,
			frappe._dict(
				user=r.receiver_user,
				open_tasks=0,
				overdue=0,
				due_in_7_days=0,
				estimated_hours=0.0,
				urgent=0,
				awaiting_my_decision=0,
			),
		)
		row.awaiting_my_decision = r.total

	rows = sorted(people.values(), key=lambda r: r.open_tasks + r.awaiting_my_decision, reverse=True)
	for row in rows:
		row.user = row.user or None
		row.load = row.open_tasks + row.awaiting_my_decision
	columns = [
		link("user", "Owner", "User", 200),
		col("open_tasks", "Open Tasks", "Int", 100),
		col("overdue", "Overdue", "Int", 90),
		col("due_in_7_days", "Due in 7 Days", "Int", 110),
		col("urgent", "High / Urgent", "Int", 110),
		col("estimated_hours", "Estimated Hours", "Float", 120),
		col("awaiting_my_decision", "Handovers Awaiting Decision", "Int", 190),
	]
	chart = {
		"data": {
			"labels": [r.user or "Unassigned" for r in rows[:15]],
			"datasets": [{"name": "Open tasks", "values": [r.open_tasks for r in rows[:15]]}],
		},
		"type": "bar",
	}
	return columns, rows, None, chart
