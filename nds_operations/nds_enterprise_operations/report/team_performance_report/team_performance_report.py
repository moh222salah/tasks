import frappe

from nds_operations.reports import col, date_conditions, link
from nds_operations.services.kpi import METHODOLOGY, get_handovers, handover_group_stats


def execute(filters=None):
	handovers = get_handovers(date_conditions(filters, "submitted_at"))
	stats = handover_group_stats(handovers, "sender_team", "receiver_team")
	rows = []
	for team in sorted(stats):
		h = stats[team]
		rows.append(
			frappe._dict(
				team=team,
				sent=h.sent,
				first_pass_rate=h.first_pass_rate,
				rework_rate=h.rework_rate,
				rejection_rate=h.rejection_rate,
				quality_score=h.quality_score,
				received_decided=h.received_decided,
				avg_response_hours=h.avg_response_hours,
				pending=h.pending,
			)
		)
	columns = [
		link("team", "Team", "NDS Team", 180),
		col("sent", "Handovers Sent", "Int", 120),
		col("first_pass_rate", "First-Pass Rate %", "Percent", 130),
		col("rework_rate", "Rework Rate %", "Percent", 120),
		col("rejection_rate", "Rejection Rate %", "Percent", 130),
		col("quality_score", "Handover Quality Score", "Float", 150),
		col("received_decided", "Decisions Given", "Int", 110),
		col("avg_response_hours", "Avg Response (hours)", "Float", 150),
		col("pending", "Awaiting Decision", "Int", 130),
	]
	return columns, rows, METHODOLOGY
