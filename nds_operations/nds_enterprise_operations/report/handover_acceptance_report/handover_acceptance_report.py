import frappe

from nds_operations.constants import ACCEPTED, CLARIFICATION, HANDOVER_REVIEW
from nds_operations.reports import average, col, get_rows, hours_between, link


def execute(filters=None):
	columns = [
		link("name", "Handover", "NDS Task Handover", 150),
		link("task", "Task", "Task", 110),
		col("task_title", "Task Title", "Data", 200),
		col("version_no", "Version", "Int", 70),
		col("sender_name", "Sender", "Data", 140),
		col("receiver_name", "Receiver", "Data", 140),
		col("receiver_department", "Receiver Department", "Data", 150),
		col("submitted_at", "Submitted", "Datetime", 150),
		col("decided_at", "Accepted", "Datetime", 150),
		col("hours_to_accept", "Hours to Accept", "Float", 110),
		col("first_pass", "First Pass", "Check", 80),
	]
	rows = get_rows(filters, {"handover_status": ACCEPTED})
	clarified = _clarified({row.name for row in rows})
	for row in rows:
		row.hours_to_accept = hours_between(row.submitted_at, row.decided_at)
		# accepted on the first version without any clarification round
		row.first_pass = int(row.version_no == 1 and row.name not in clarified)

	summary = [
		{"label": "Accepted handovers", "value": len(rows), "datatype": "Int", "indicator": "Green"},
		{
			"label": "First-pass acceptance rate (%)",
			"value": round(100 * sum(r.first_pass for r in rows) / len(rows), 1) if rows else 0,
			"datatype": "Float",
			"indicator": "Blue",
		},
		{
			"label": "Average hours to accept",
			"value": average([r.hours_to_accept for r in rows]) or 0,
			"datatype": "Float",
			"indicator": "Orange",
		},
	]
	return columns, rows, None, None, summary


def _clarified(names):
	if not names:
		return set()
	return set(
		frappe.get_all(
			HANDOVER_REVIEW,
			filters={"handover": ("in", list(names)), "decision": CLARIFICATION},
			pluck="handover",
		)
	)
