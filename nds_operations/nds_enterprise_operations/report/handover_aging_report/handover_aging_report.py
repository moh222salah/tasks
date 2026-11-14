import frappe

from nds_operations.constants import OPEN_STATUSES
from nds_operations.reports import age_bucket, col, get_rows, hours_between, link, now


def execute(filters=None):
	columns = [
		link("name", "Handover", "NDS Task Handover", 150),
		link("task", "Task", "Task", 110),
		col("task_title", "Task Title", "Data", 200),
		col("handover_status", "Status", "Data", 150),
		col("sender_name", "Sender", "Data", 140),
		col("receiver_name", "Waiting On Receiver", "Data", 140),
		col("receiver_department", "Receiver Department", "Data", 150),
		col("submitted_at", "Submitted", "Datetime", 150),
		col("response_due", "Reply By", "Datetime", 150),
		col("age_hours", "Age (hours)", "Float", 100),
		col("age_bucket", "Age Bucket", "Data", 100),
		col("overdue", "Overdue", "Check", 80),
	]
	rows = get_rows(filters, {"handover_status": ("in", OPEN_STATUSES)})
	current = now()
	for row in rows:
		row.age_hours = hours_between(row.submitted_at, current)
		row.age_bucket = age_bucket(row.age_hours)
		# only the receiver can be late; a clarification request waits for the sender
		row.overdue = int(
			row.handover_status in ("Pending Acceptance", "Under Review")
			and bool(row.response_due)
			and row.response_due < current
		)
	rows.sort(key=lambda r: r.age_hours or 0, reverse=True)

	buckets = {}
	for row in rows:
		buckets[row.age_bucket] = buckets.get(row.age_bucket, 0) + 1
	order = ["0-1 day", "1-3 days", "3-7 days", "7+ days"]
	chart = {
		"data": {
			"labels": order,
			"datasets": [{"name": "Open handovers", "values": [buckets.get(b, 0) for b in order]}],
		},
		"type": "bar",
	}
	summary = [
		{"label": "Open handovers", "value": len(rows), "datatype": "Int", "indicator": "Blue"},
		{"label": "Overdue", "value": sum(r.overdue for r in rows), "datatype": "Int", "indicator": "Red"},
	]
	return columns, rows, None, chart, summary
