import frappe

from nds_operations.constants import HANDOVER_REVIEW, REJECTED
from nds_operations.reports import col, get_rows, link


def execute(filters=None):
	columns = [
		link("name", "Handover", "NDS Task Handover", 150),
		link("task", "Task", "Task", 110),
		col("task_title", "Task Title", "Data", 200),
		col("version_no", "Version", "Int", 70),
		col("sender_name", "Sender", "Data", 140),
		col("receiver_name", "Rejected By", "Data", 140),
		col("receiver_department", "Receiver Department", "Data", 150),
		col("decided_at", "Rejected At", "Datetime", 150),
		col("rejection_reason", "Reason", "Data", 160),
		col("details", "Details", "Small Text", 300),
	]
	rows = get_rows(filters, {"handover_status": REJECTED})
	details = {
		r.handover: r.details
		for r in frappe.get_all(
			HANDOVER_REVIEW,
			filters={"handover": ("in", [row.name for row in rows] or ["__none__"]), "decision": REJECTED},
			fields=["handover", "details"],
			order_by="reviewed_at asc",
		)
	}
	for row in rows:
		row.details = frappe.utils.strip_html(details.get(row.name) or "")

	# chart: how often each reason is used
	reasons = {}
	for row in rows:
		key = row.rejection_reason or "—"
		reasons[key] = reasons.get(key, 0) + 1
	chart = {
		"data": {
			"labels": list(reasons),
			"datasets": [{"name": "Rejections", "values": list(reasons.values())}],
		},
		"type": "bar",
	}
	summary = [{"label": "Rejected handovers", "value": len(rows), "datatype": "Int", "indicator": "Red"}]
	return columns, rows, None, chart, summary
