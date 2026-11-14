"""Shared helpers for the handover script reports.

Rows are read with frappe.get_list, so the same row scoping as the lists and APIs applies:
a user only ever reports on handovers he is allowed to read.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime

from nds_operations.constants import HANDOVER

FIELDS = [
	"name",
	"task",
	"task_title",
	"handover_status",
	"version_no",
	"sender_name",
	"sender_department",
	"receiver_name",
	"receiver_department",
	"priority",
	"submitted_at",
	"response_due",
	"decided_at",
	"rejection_reason",
]


def hours_between(start, end):
	if not start or not end:
		return None
	return round((get_datetime(end) - get_datetime(start)).total_seconds() / 3600, 1)


def get_rows(filters, extra_filters=None, fields=None):
	filters = frappe._dict(filters or {})
	conditions = {"docstatus": 1}
	conditions.update(extra_filters or {})
	if filters.from_date and filters.to_date:
		conditions["submitted_at"] = ("between", [filters.from_date, f"{filters.to_date} 23:59:59"])
	elif filters.from_date:
		conditions["submitted_at"] = (">=", filters.from_date)
	elif filters.to_date:
		conditions["submitted_at"] = ("<=", f"{filters.to_date} 23:59:59")
	for key in ("sender_department", "receiver_department", "handover_status", "priority"):
		if filters.get(key):
			conditions[key] = filters[key]
	if filters.employee:
		conditions["name"] = ("in", _handover_names_of(filters.employee))
	return frappe.get_list(
		HANDOVER,
		filters=conditions,
		fields=fields or FIELDS,
		order_by="submitted_at desc",
		limit_page_length=0,
	)


def _handover_names_of(employee):
	names = set()
	for fieldname in ("sender_employee", "receiver_employee"):
		names.update(frappe.get_all(HANDOVER, filters={fieldname: employee, "docstatus": 1}, pluck="name"))
	return list(names) or ["__none__"]


def link(fieldname, label, options, width=140):
	return {
		"fieldname": fieldname,
		"label": _(label),
		"fieldtype": "Link",
		"options": options,
		"width": width,
	}


def col(fieldname, label, fieldtype="Data", width=120):
	return {"fieldname": fieldname, "label": _(label), "fieldtype": fieldtype, "width": width}


def age_bucket(hours):
	if hours is None:
		return ""
	if hours < 24:
		return "0-1 day"
	if hours < 72:
		return "1-3 days"
	if hours < 168:
		return "3-7 days"
	return "7+ days"


def average(values):
	values = [v for v in values if v is not None]
	return round(flt(sum(values)) / len(values), 1) if values else None


def now():
	return now_datetime()
