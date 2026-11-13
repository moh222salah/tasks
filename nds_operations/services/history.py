import frappe
from frappe.utils import get_fullname, now_datetime

from nds_operations.constants import HANDOVER_HISTORY


def log_event(
	handover, event_type, *, from_status=None, to_status=None, remarks=None, review=None, request_id=None
):
	"""Append one row to the handover timeline. Rows are never edited or deleted."""
	frappe.get_doc(
		{
			"doctype": HANDOVER_HISTORY,
			"handover": handover.name,
			"task": handover.task,
			"version_no": handover.version_no,
			"event_type": event_type,
			"from_status": from_status,
			"to_status": to_status,
			"actor": frappe.session.user,
			"actor_name": get_fullname(frappe.session.user),
			"event_time": now_datetime(),
			"remarks": remarks,
			"review": review,
			"request_id": request_id,
			"ip_address": getattr(frappe.local, "request_ip", None),
		}
	).insert(ignore_permissions=True)
