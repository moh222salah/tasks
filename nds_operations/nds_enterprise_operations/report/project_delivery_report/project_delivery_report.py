import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from nds_operations.reports import CLOSED_TASKS, col, link, open_handovers_of

METHOD = _(
	"Cancelled tasks are excluded. On-time rate = completed tasks finished on or before their due date, "
	"out of completed tasks that have a due date and a completion date; blank when there are none. "
	"Tasks whose handover is waiting on the receiver are not counted as late work of the owner."
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {"status": ("!=", "Cancelled")}
	if filters.department:
		conditions["department"] = filters.department
	conditions["project"] = filters.project or ("is", "set")
	tasks = frappe.get_list(
		"Task",
		filters=conditions,
		fields=["name", "project", "status", "exp_end_date", "completed_on", "progress"],
		limit_page_length=0,
	)
	waiting = open_handovers_of([t.name for t in tasks])
	today = getdate(nowdate())
	stats = {}
	for task in tasks:
		row = stats.setdefault(
			task.project,
			frappe._dict(
				project=task.project,
				total=0,
				completed=0,
				open=0,
				overdue=0,
				waiting_handover=0,
				dated_done=0,
				on_time=0,
				progress_sum=0,
			),
		)
		row.total += 1
		row.progress_sum += flt(task.progress)
		if task.name in waiting:
			row.waiting_handover += 1
		if task.status == "Completed":
			row.completed += 1
			if task.exp_end_date and task.completed_on:
				row.dated_done += 1
				row.on_time += getdate(task.completed_on) <= getdate(task.exp_end_date)
		elif task.status not in CLOSED_TASKS:
			row.open += 1
			if task.exp_end_date and getdate(task.exp_end_date) < today and task.name not in waiting:
				row.overdue += 1
	rows = []
	for row in sorted(stats.values(), key=lambda r: r.project):
		row.completion_rate = round(100 * row.completed / row.total, 1) if row.total else None
		row.on_time_rate = round(100 * row.on_time / row.dated_done, 1) if row.dated_done else None
		row.avg_progress = round(row.progress_sum / row.total, 1) if row.total else None
		rows.append(row)
	columns = [
		link("project", "Project", "Project", 200),
		col("total", "Tasks", "Int", 80),
		col("completed", "Completed", "Int", 90),
		col("open", "Open", "Int", 80),
		col("overdue", "Overdue", "Int", 80),
		col("waiting_handover", "Waiting on Handover", "Int", 140),
		col("completion_rate", "Completion %", "Percent", 110),
		col("on_time_rate", "On-Time %", "Percent", 100),
		col("avg_progress", "Avg Progress %", "Percent", 120),
	]
	summary = [
		{"label": "Projects", "value": len(rows), "datatype": "Int", "indicator": "Blue"},
		{"label": "Overdue tasks", "value": sum(r.overdue for r in rows), "datatype": "Int", "indicator": "Red"},
	]
	return columns, rows, METHOD, None, summary
