from nds_operations.reports import col, date_conditions, link
from nds_operations.services.kpi import METHODOLOGY, completed_tasks, mean, on_time_rate


def execute(filters=None):
	rows = completed_tasks(date_conditions(filters, "completed_on"))
	rows.sort(key=lambda r: r.cycle_days, reverse=True)
	columns = [
		link("name", "Task", "Task", 110),
		col("subject", "Subject", "Data", 220),
		link("department", "Department", "Department", 150),
		link("project", "Project", "Project", 130),
		link("owner_user", "Owner", "User", 170),
		col("creation", "Created", "Date", 100),
		col("exp_end_date", "Due", "Date", 100),
		col("completed_on", "Completed", "Date", 100),
		col("cycle_days", "Cycle (days)", "Int", 100),
		col("on_time", "On Time", "Check", 80),
		col("excused", "Excused (waiting on receiver)", "Check", 160),
	]
	summary = [
		{"label": "Completed tasks", "value": len(rows), "datatype": "Int", "indicator": "Blue"},
		{
			"label": "Average cycle (days)",
			"value": mean([r.cycle_days for r in rows]) or 0,
			"datatype": "Float",
			"indicator": "Orange",
		},
		{
			"label": "On-time rate %",
			"value": on_time_rate(rows) or 0,
			"datatype": "Float",
			"indicator": "Green",
		},
	]
	return columns, rows, METHODOLOGY, None, summary
