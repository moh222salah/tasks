import frappe

from nds_operations.constants import CLARIFICATION, HANDOVER_REVIEW, REJECTED
from nds_operations.reports import col, date_conditions, hours_between, link
from nds_operations.services.kpi import METHODOLOGY, get_handovers


def execute(filters=None):
	handovers = get_handovers(date_conditions(filters, "submitted_at"))
	chains = {}
	for h in handovers:
		chains.setdefault(h.root_handover or h.name, []).append(h)
	names = [h.name for h in handovers]
	reviews = frappe.get_list(
		HANDOVER_REVIEW,
		filters={"handover": ("in", names or ["__none__"])},
		fields=["handover", "decision"],
		limit_page_length=0,
	)
	by_handover = {}
	for r in reviews:
		by_handover.setdefault(r.handover, []).append(r.decision)

	rows = []
	for root, chain in chains.items():
		if len(chain) < 2:
			continue  # no revision: nothing was reworked
		chain.sort(key=lambda h: h.version_no or 1)
		decisions = [d for h in chain for d in by_handover.get(h.name, [])]
		last = chain[-1]
		rows.append(
			frappe._dict(
				root=root,
				task=last.task,
				versions=len(chain),
				rejections=sum(1 for d in decisions if d == REJECTED),
				clarifications=sum(1 for d in decisions if d == CLARIFICATION),
				sender_user=last.sender_user,
				receiver_user=last.receiver_user,
				latest=last.name,
				final_status=last.handover_status,
				span_hours=hours_between(chain[0].submitted_at, last.decided_at or last.submitted_at),
			)
		)
	rows.sort(key=lambda r: (r.versions, r.rejections), reverse=True)
	columns = [
		link("root", "First Handover", "NDS Task Handover", 150),
		link("task", "Task", "Task", 110),
		col("versions", "Versions", "Int", 90),
		col("rejections", "Rejections", "Int", 100),
		col("clarifications", "Clarifications", "Int", 110),
		link("sender_user", "Sender", "User", 170),
		link("receiver_user", "Receiver", "User", 170),
		link("latest", "Latest Version", "NDS Task Handover", 150),
		col("final_status", "Latest Status", "Data", 150),
		col("span_hours", "Span (hours)", "Float", 110),
	]
	summary = [
		{"label": "Handovers needing rework", "value": len(rows), "datatype": "Int", "indicator": "Orange"},
		{
			"label": "Repeated 3+ versions",
			"value": sum(1 for r in rows if r.versions >= 3),
			"datatype": "Int",
			"indicator": "Red",
		},
	]
	return columns, rows, METHODOLOGY, None, summary
