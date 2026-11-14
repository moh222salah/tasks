"""Shared helpers for the handover script reports.

Rows are read with frappe.get_list, so the same row scoping as the lists and APIs applies:
a user only ever reports on handovers he is allowed to read.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, getdate, now_datetime, nowdate

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


CLOSED_TASKS = ("Completed", "Cancelled", "Template")
TASK_FIELDS = [
	"name",
	"subject",
	"status",
	"priority",
	"project",
	"department",
	"exp_start_date",
	"exp_end_date",
	"progress",
	"expected_time",
	"modified",
]


def get_tasks(filters, open_only=False, overdue_only=False):
	"""Tasks the user may read (ERPNext Task permissions apply), with the current owner and any open handover."""
	filters = frappe._dict(filters or {})
	conditions = {}
	if open_only or overdue_only:
		conditions["status"] = ("not in", CLOSED_TASKS)
	elif filters.status:
		conditions["status"] = filters.status
	if overdue_only:
		conditions["exp_end_date"] = ("<", getdate(nowdate()))
	for key in ("project", "department", "priority"):
		if filters.get(key):
			conditions[key] = filters[key]
	if filters.from_date and filters.to_date:
		conditions["exp_end_date"] = ("between", [filters.from_date, filters.to_date])
	tasks = frappe.get_list(
		"Task",
		filters=conditions,
		fields=TASK_FIELDS,
		order_by="exp_end_date asc, modified desc",
		limit_page_length=0,
	)
	owners = current_owners([t.name for t in tasks])
	open_handovers = open_handovers_of([t.name for t in tasks])
	for task in tasks:
		task.current_owner = owners.get(task.name)
		handover = open_handovers.get(task.name)
		task.open_handover = handover.name if handover else None
		task.handover_status = handover.handover_status if handover else None
		task.waiting_on = handover.receiver_name if handover else None
		task.days_overdue = (
			max((getdate(nowdate()) - getdate(task.exp_end_date)).days, 0)
			if task.exp_end_date and task.status not in CLOSED_TASKS
			else 0
		)
	if filters.owner:
		tasks = [t for t in tasks if t.current_owner == filters.owner]
	return tasks


def current_owners(tasks):
	"""Same rule as services.ownership.get_current_owner, batched: last ledger row, else the first open
	ToDo, else the task creator."""
	if not tasks:
		return {}
	owners = {
		r.name: r.owner
		for r in frappe.get_all("Task", filters={"name": ("in", tasks)}, fields=["name", "owner"])
	}
	for row in frappe.get_all(
		"ToDo",
		filters={"reference_type": "Task", "reference_name": ("in", tasks), "status": "Open"},
		fields=["reference_name", "allocated_to"],
		order_by="creation desc",
	):
		owners[row.reference_name] = row.allocated_to
	ledger = frappe.db.sql(
		"select h.task, h.to_user from `tabNDS Ownership History` h join "
		"(select task, max(sequence) seq from `tabNDS Ownership History` where task in %s group by task) m "
		"on m.task = h.task and m.seq = h.sequence",
		(tuple(tasks),),
		as_dict=True,
	)
	owners.update({r.task: r.to_user for r in ledger})
	return owners


def open_handovers_of(tasks):
	if not tasks:
		return {}
	rows = frappe.get_all(
		HANDOVER,
		filters={
			"task": ("in", tasks),
			"docstatus": 1,
			"handover_status": ("in", ("Pending Acceptance", "Under Review", "Clarification Requested")),
			"superseded_by": ("is", "not set"),
		},
		fields=["name", "task", "handover_status", "receiver_name"],
	)
	return {r.task: r for r in rows}
