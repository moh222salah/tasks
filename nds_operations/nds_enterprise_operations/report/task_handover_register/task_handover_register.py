from frappe import _

from nds_operations.reports import col, get_rows, link


def execute(filters=None):
	columns = [
		link("name", "Handover", "NDS Task Handover", 150),
		link("task", "Task", "Task", 110),
		col("task_title", "Task Title", "Data", 200),
		col("version_no", "Version", "Int", 70),
		col("handover_status", "Status", "Data", 150),
		col("sender_name", "Sender", "Data", 140),
		col("sender_department", "Sender Department", "Data", 150),
		col("receiver_name", "Receiver", "Data", 140),
		col("receiver_department", "Receiver Department", "Data", 150),
		col("priority", "Priority", "Data", 80),
		col("submitted_at", "Submitted", "Datetime", 150),
		col("decided_at", "Decided", "Datetime", 150),
	]
	return columns, get_rows(filters)
