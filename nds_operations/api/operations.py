"""Permission-scoped operational dashboard data for NDS Operations."""
import frappe
from frappe.utils import cint, now_datetime

from nds_operations.constants import ACCEPTED, CLARIFICATION, HANDOVER, NDS_ROLES, PENDING, REJECTED, UNDER_REVIEW

ACTIVE_STATES = (PENDING, UNDER_REVIEW, CLARIFICATION)


def _assert_dashboard_access():
    roles = set(frappe.get_roles())
    if frappe.session.user == "Administrator" or "System Manager" in roles:
        return
    if not roles.intersection(NDS_ROLES) or not frappe.has_permission(HANDOVER, "read"):
        frappe.throw("You do not have access to the NDS Operations dashboard.", frappe.PermissionError)


def _count(filters):
    rows = frappe.get_list(HANDOVER, filters=filters, fields=["count(name) as total"], page_length=1)
    return cint(rows[0].get("total")) if rows else 0


@frappe.whitelist(methods=["GET"])
def get_dashboard():
    """Summarize only handovers visible to the current session user."""
    _assert_dashboard_access()
    grouped = frappe.get_list(
        HANDOVER,
        filters={"docstatus": 1},
        fields=["handover_status", "count(name) as total"],
        group_by="handover_status",
        page_length=100,
    )
    status_counts = {row.handover_status: cint(row.total) for row in grouped}
    accepted = status_counts.get(ACCEPTED, 0)
    rejected = status_counts.get(REJECTED, 0)
    decided = accepted + rejected
    overdue = _count({
        "docstatus": 1,
        "handover_status": ("in", ACTIVE_STATES),
        "response_due": ("<", now_datetime()),
    })
    recent = frappe.get_list(
        HANDOVER,
        filters={"docstatus": 1},
        fields=[
            "name", "task", "task_title", "handover_status", "sender_name", "receiver_name",
            "sender_department", "receiver_department", "modified",
        ],
        order_by="modified desc",
        page_length=8,
    )
    departments = frappe.get_list(
        HANDOVER,
        filters={"docstatus": 1, "receiver_department": ("is", "set")},
        fields=["receiver_department", "count(name) as total"],
        group_by="receiver_department",
        order_by="total desc",
        page_length=8,
    )
    return {
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
