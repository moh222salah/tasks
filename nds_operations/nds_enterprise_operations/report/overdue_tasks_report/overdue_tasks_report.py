from nds_operations.nds_enterprise_operations.report.tasks_master_report.tasks_master_report import (
	task_columns,
)
from nds_operations.reports import col, get_tasks


def reason(task):
	"""What is visible in the data; a missing reason is shown as blank, never guessed."""
	if task.open_handover:
		who = f" by {task.waiting_on}" if task.waiting_on else ""
		return f"Handover {task.open_handover} ({task.handover_status}) waiting{who}"
	if task.status == "Pending Review":
		return "Waiting for review"
	if not task.current_owner:
		return "No owner assigned"
	return ""


def execute(filters=None):
	rows = get_tasks(filters, overdue_only=True)
	for row in rows:
		row.reason = reason(row)
	rows.sort(key=lambda r: r.days_overdue, reverse=True)
	columns = [c for c in task_columns() if c["fieldname"] not in ("progress",)]
	columns.append(col("reason", "Visible Reason", "Data", 320))
	summary = [
		{"label": "Overdue tasks", "value": len(rows), "datatype": "Int", "indicator": "Red"},
		{
			"label": "Without owner",
			"value": sum(1 for r in rows if not r.current_owner),
			"datatype": "Int",
			"indicator": "Orange",
		},
	]
	return columns, rows, None, None, summary
