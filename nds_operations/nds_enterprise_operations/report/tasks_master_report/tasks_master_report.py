from nds_operations.reports import col, get_tasks, link


def task_columns():
	return [
		link("name", "Task", "Task", 110),
		col("subject", "Subject", "Data", 220),
		col("status", "Status", "Data", 110),
		col("priority", "Priority", "Data", 80),
		link("project", "Project", "Project", 130),
		link("department", "Department", "Department", 140),
		link("current_owner", "Current Owner", "User", 170),
		col("exp_start_date", "Start", "Date", 95),
		col("exp_end_date", "Due", "Date", 95),
		col("days_overdue", "Days Overdue", "Int", 100),
		col("progress", "Progress %", "Percent", 90),
		link("open_handover", "Open Handover", "NDS Task Handover", 140),
		col("handover_status", "Handover Status", "Data", 150),
	]


def execute(filters=None):
	rows = get_tasks(filters)
	summary = [
		{"label": "Tasks", "value": len(rows), "datatype": "Int", "indicator": "Blue"},
		{
			"label": "Overdue",
			"value": sum(1 for r in rows if r.days_overdue),
			"datatype": "Int",
			"indicator": "Red",
		},
		{
			"label": "With open handover",
			"value": sum(1 for r in rows if r.open_handover),
			"datatype": "Int",
			"indicator": "Orange",
		},
	]
	return task_columns(), rows, None, None, summary
