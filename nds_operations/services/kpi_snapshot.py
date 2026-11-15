"""Frozen monthly department KPI snapshots.

The figures are the ones of the Department Performance Report (same fairness rules, see services.kpi), computed
for a closed period and stored once. A snapshot is never rewritten, so a later change of task data or of an
owner cannot alter what management saw for that month. Open tasks are a count at generation time.
"""

import frappe
from frappe import _
from frappe.utils import add_months, get_first_day, get_last_day, getdate, now_datetime, today

from nds_operations.constants import ROLE_EXECUTIVE, ROLE_OPS_MANAGER
from nds_operations.reports import date_conditions
from nds_operations.services.kpi import (
	completed_tasks,
	get_handovers,
	handover_group_stats,
	mean,
	on_time_rate,
)

DOCTYPE = "NDS Department KPI"
CLOSED = ("Completed", "Cancelled", "Template")


def previous_month(day=None):
	first = get_first_day(add_months(getdate(day or today()), -1))
	return first, get_last_day(first)


def generate(period_start, period_end):
	"""Create the missing snapshots of a closed period. Returns the names created; existing ones are left alone."""
	period_start, period_end = getdate(period_start), getdate(period_end)
	if period_end < period_start:
		frappe.throw(_("The period end is before its start."))
	if period_end >= getdate(today()):
		frappe.throw(_("Only a finished period can be frozen."))
	filters = {"from_date": period_start, "to_date": period_end}
	stats = handover_group_stats(
		get_handovers(date_conditions(filters, "submitted_at")), "sender_department", "receiver_department"
	)
	done = {}
	for task in completed_tasks(date_conditions(filters, "completed_on")):
		if task.department:
			done.setdefault(task.department, []).append(task)
	open_now = {
		r.department: r.total
		for r in frappe.get_list(
			"Task",
			filters={"status": ("not in", CLOSED), "department": ("is", "set")},
			fields=["department", {"COUNT": "name", "as": "total"}],
			group_by="department",
			limit_page_length=0,
		)
	}
	created = []
	for department in sorted(set(stats) | set(done) | set(open_now)):
		if frappe.db.exists(
			DOCTYPE, {"department": department, "period_start": period_start, "period_end": period_end}
		):
			continue
		g = stats.get(department, frappe._dict())
		mine = done.get(department, [])
		doc = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"department": department,
				"period_start": period_start,
				"period_end": period_end,
				"generated_at": now_datetime(),
				"generated_by": frappe.session.user,
				"open_tasks": open_now.get(department, 0),
				"completed_tasks": len(mine),
				"on_time_rate": on_time_rate(mine),
				"avg_cycle_days": mean([t.cycle_days for t in mine]),
				"handovers_sent": g.get("sent", 0),
				"first_pass_rate": g.get("first_pass_rate"),
				"rejection_rate": g.get("rejection_rate"),
				"quality_score": g.get("quality_score"),
				"avg_response_hours": g.get("avg_response_hours"),
				"awaiting_decision": g.get("pending", 0),
			}
		)
		doc.insert(ignore_permissions=True)
		created.append(doc.name)
	return created


@frappe.whitelist(methods=["POST"])
def freeze_period(period_start, period_end):
	roles = set(frappe.get_roles())
	if not ({"System Manager", ROLE_OPS_MANAGER, ROLE_EXECUTIVE} & roles):
		frappe.throw(
			_("Only operations or executive management can freeze KPI snapshots."), frappe.PermissionError
		)
	return generate(period_start, period_end)


def run_monthly_snapshot():
	"""Daily job: freeze last month when it is not frozen yet (also catches up after a missed day)."""
	if getdate(today()).day > 7:
		return  # only the first week of a month; a month without any activity would otherwise be recomputed daily
	start, end = previous_month()
	if not frappe.db.exists(DOCTYPE, {"period_start": start, "period_end": end}):
		generate(start, end)
