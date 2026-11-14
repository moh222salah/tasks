import frappe

from nds_operations.reports import col, date_conditions, link
from nds_operations.services.kpi import (
	METHODOLOGY,
	completed_tasks,
	get_handovers,
	handover_group_stats,
	mean,
	on_time_rate,
)


def execute(filters=None):
	handovers = get_handovers(date_conditions(filters, "submitted_at"))
	stats = handover_group_stats(handovers, "sender_department", "receiver_department")
	tasks = completed_tasks(date_conditions(filters, "completed_on"))
	by_department = {}
	for task in tasks:
		by_department.setdefault(task.department, []).append(task)
	open_tasks = frappe.get_list(
		"Task",
		filters={"status": ("not in", ("Completed", "Cancelled", "Template"))},
		fields=["department", {"COUNT": "name", "as": "total"}],
		group_by="department",
		limit_page_length=0,
	)
	open_by_department = {r.department: r.total for r in open_tasks}

	rows = []
	for department in sorted(
		set(stats) | {d for d in by_department if d} | {d for d in open_by_department if d}
	):
		h = stats.get(department, frappe._dict())
		mine = by_department.get(department, [])
		rows.append(
			frappe._dict(
				department=department,
				open_tasks=open_by_department.get(department, 0),
				completed=len(mine),
				on_time_rate=on_time_rate(mine),
				avg_cycle_days=mean([t.cycle_days for t in mine]),
				sent=h.get("sent", 0),
				first_pass_rate=h.get("first_pass_rate"),
				rejection_rate=h.get("rejection_rate"),
				quality_score=h.get("quality_score"),
				avg_response_hours=h.get("avg_response_hours"),
				pending=h.get("pending", 0),
			)
		)
	columns = [
		link("department", "Department", "Department", 190),
		col("open_tasks", "Open Tasks", "Int", 100),
		col("completed", "Completed Tasks", "Int", 120),
		col("on_time_rate", "On-Time Rate %", "Percent", 120),
		col("avg_cycle_days", "Avg Cycle (days)", "Float", 120),
		col("sent", "Handovers Sent", "Int", 120),
		col("first_pass_rate", "First-Pass Rate %", "Percent", 130),
		col("rejection_rate", "Rejection Rate %", "Percent", 130),
		col("quality_score", "Handover Quality Score", "Float", 150),
		col("avg_response_hours", "Avg Response (hours)", "Float", 150),
		col("pending", "Awaiting Decision", "Int", 130),
	]
	return columns, rows, METHODOLOGY
