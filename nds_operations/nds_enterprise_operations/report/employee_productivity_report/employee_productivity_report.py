import frappe

from nds_operations.reports import col, date_conditions, link
from nds_operations.services.kpi import (
	METHODOLOGY,
	completed_tasks,
	get_handovers,
	handover_group_stats,
	mean,
	on_time_rate,
	review_scores_by_owner,
)


def execute(filters=None):
	handovers = get_handovers(date_conditions(filters, "submitted_at"))
	stats = handover_group_stats(handovers, "sender_user", "receiver_user")
	tasks = completed_tasks(date_conditions(filters, "completed_on"))
	review_scores = review_scores_by_owner(date_conditions(filters, "reviewed_at"))
	by_owner = {}
	for task in tasks:
		by_owner.setdefault(task.owner_user, []).append(task)

	rows = []
	for user in sorted(set(stats) | {u for u in by_owner if u} | set(review_scores)):
		h = stats.get(user, frappe._dict())
		mine = by_owner.get(user, [])
		rows.append(
			frappe._dict(
				user=user,
				completed=len(mine),
				on_time_rate=on_time_rate(mine),
				avg_cycle_days=mean([t.cycle_days for t in mine]),
				sent=h.get("sent", 0),
				first_pass_rate=h.get("first_pass_rate"),
				rework_rate=h.get("rework_rate"),
				rejection_rate=h.get("rejection_rate"),
				quality_score=h.get("quality_score"),
				review_score=review_scores.get(user),
				received_decided=h.get("received_decided", 0),
				avg_response_hours=h.get("avg_response_hours"),
				pending=h.get("pending", 0),
			)
		)
	columns = [
		link("user", "Employee", "User", 190),
		col("completed", "Completed Tasks", "Int", 120),
		col("on_time_rate", "On-Time Rate %", "Percent", 120),
		col("avg_cycle_days", "Avg Cycle (days)", "Float", 120),
		col("sent", "Handovers Sent", "Int", 120),
		col("first_pass_rate", "First-Pass Rate %", "Percent", 130),
		col("rework_rate", "Rework Rate %", "Percent", 120),
		col("rejection_rate", "Rejection Rate %", "Percent", 130),
		col("quality_score", "Handover Quality Score", "Float", 150),
		col("review_score", "Quality Review Score", "Float", 150),
		col("received_decided", "Decisions Given", "Int", 110),
		col("avg_response_hours", "Avg Response (hours)", "Float", 150),
		col("pending", "Awaiting My Decision", "Int", 150),
	]
	return columns, rows, METHODOLOGY
