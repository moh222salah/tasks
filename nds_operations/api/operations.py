"""Permission-scoped operational dashboard data for NDS Operations."""

import frappe
from frappe import _
from frappe.utils import cint, getdate, now_datetime, nowdate

from nds_operations.constants import (
	ACCEPTED,
	HANDOVER,
	NDS_ROLES,
	PENDING,
	REJECTED,
	UNDER_REVIEW,
)

# Only the receiver owes an answer in these states; a clarification request waits for the sender.
AWAITING_RECEIVER = (PENDING, UNDER_REVIEW)
CLOSED_TASKS = ("Completed", "Cancelled", "Template")
TOTAL = {"COUNT": "name", "as": "total"}


def _assert_dashboard_access():
	roles = set(frappe.get_roles())
	if frappe.session.user == "Administrator" or "System Manager" in roles:
		return
	if not roles.intersection(NDS_ROLES) or not frappe.has_permission(HANDOVER, "read"):
		frappe.throw(_("You do not have access to the NDS Operations dashboard."), frappe.PermissionError)


def _count(filters, doctype=HANDOVER):
	rows = frappe.get_list(doctype, filters=filters, fields=[TOTAL])
	return cint(rows[0].get("total")) if rows else 0


@frappe.whitelist(methods=["GET"])
def get_dashboard():
	"""Summarize only handovers visible to the current session user."""
	_assert_dashboard_access()
	grouped = frappe.get_list(
		HANDOVER,
		filters={"docstatus": 1},
		fields=["handover_status", TOTAL],
		group_by="handover_status",
		limit_page_length=100,
	)
	status_counts = {row.handover_status: cint(row.total) for row in grouped}
	accepted = status_counts.get(ACCEPTED, 0)
	rejected = status_counts.get(REJECTED, 0)
	decided = accepted + rejected
	overdue = _count(
		{
			"docstatus": 1,
			"handover_status": ("in", AWAITING_RECEIVER),
			"response_due": ("<", now_datetime()),
		}
	)
	recent = frappe.get_list(
		HANDOVER,
		filters={"docstatus": 1},
		fields=[
			"name",
			"task",
			"task_title",
			"handover_status",
			"sender_name",
			"receiver_name",
			"sender_department",
			"receiver_department",
			"modified",
		],
		order_by="modified desc",
		limit_page_length=8,
	)
	departments = frappe.get_list(
		HANDOVER,
		filters={"docstatus": 1, "receiver_department": ("is", "set")},
		fields=["receiver_department", TOTAL],
		group_by="receiver_department",
		order_by="total desc",
		limit_page_length=8,
	)
	tasks = {
		"open": _count({"status": ("not in", CLOSED_TASKS)}, "Task"),
		"overdue": _count(
			{"status": ("not in", CLOSED_TASKS), "exp_end_date": ("<", getdate(nowdate()))}, "Task"
		),
		"completed": _count({"status": "Completed"}, "Task"),
	}
	return {
		"tasks": tasks,
		"kpis": {
			"total_submitted": sum(status_counts.values()),
			"pending_acceptance": status_counts.get(PENDING, 0),
			"under_review": status_counts.get(UNDER_REVIEW, 0),
			"overdue": overdue,
			"accepted": accepted,
			"rejected": rejected,
			"decision_acceptance_rate": round(accepted / decided * 100, 1) if decided else None,
		},
		"status_counts": status_counts,
		"departments": departments,
		"recent": recent,
		"scope": "permission_scoped",
		"generated_at": now_datetime(),
	}
