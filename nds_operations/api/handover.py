"""Whitelisted endpoints of the handover module.

Thin on purpose: they parse the request and call nds_operations.services.handover, which owns the rules.
Permissions are checked there and in the DocType controllers, never only here.
Call as /api/method/nds_operations.api.handover.<function>.
"""

import frappe
from frappe.utils import cint

from nds_operations.constants import (
	CLARIFICATION,
	DRAFT,
	HANDOVER,
	HANDOVER_HISTORY,
	HANDOVER_REVIEW,
	OPEN_STATUSES,
	OWNERSHIP_HISTORY,
	PENDING,
	READY,
	REJECTED,
	UNDER_REVIEW,
)
from nds_operations.services import handover as engine
from nds_operations.services.snapshot import verify_snapshot

LIST_FIELDS = [
	"name",
	"task",
	"task_title",
	"handover_status",
	"docstatus",
	"priority",
	"handover_type",
	"version_no",
	"handover_reason",
	"sender_user",
	"sender_name",
	"sender_department",
	"receiver_user",
	"receiver_name",
	"receiver_department",
	"submitted_at",
	"response_due",
	"modified",
]


def _json(value, default=None):
	return frappe.parse_json(value) if value else default


# -- drafting and sending ----------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def create_handover(task, receiver_employee, data=None, attachments=None, client_request_id=None):
	doc = engine.create_handover(
		task, receiver_employee, _json(data, {}), _json(attachments, []), client_request_id
	)
	return {"name": doc.name, "handover_status": doc.handover_status}


@frappe.whitelist(methods=["POST"])
def update_draft(name, receiver_employee=None, data=None, attachments=None):
	doc = engine.update_draft(name, receiver_employee, _json(data, {}), _json(attachments))
	return {"name": doc.name, "handover_status": doc.handover_status}


@frappe.whitelist(methods=["POST"])
def mark_ready(name):
	doc = engine.mark_ready(name)
	return {"name": doc.name, "handover_status": doc.handover_status}


@frappe.whitelist(methods=["POST"])
def reopen_draft(name):
	doc = engine.reopen_draft(name)
	return {"name": doc.name, "handover_status": doc.handover_status}


@frappe.whitelist(methods=["POST"])
def submit_handover(name, request_id=None):
	return engine.submit_handover(name, request_id)


@frappe.whitelist(methods=["POST"])
def withdraw_handover(name, reason, request_id=None):
	return engine.withdraw_handover(name, reason, request_id)


# -- receiving ---------------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def start_review(name):
	return engine.start_review(name)


@frappe.whitelist(methods=["POST"])
def accept_handover(
	name,
	confirmed_details_reviewed=0,
	confirmed_attachments_received=0,
	confirmed_responsibilities_understood=0,
	details=None,
	next_step=None,
	expected_start=None,
	request_id=None,
):
	return engine.accept_handover(
		name,
		confirmed_details_reviewed=confirmed_details_reviewed,
		confirmed_attachments_received=confirmed_attachments_received,
		confirmed_responsibilities_understood=confirmed_responsibilities_understood,
		details=details,
		next_step=next_step,
		expected_start=expected_start,
		request_id=request_id,
	)


@frappe.whitelist(methods=["POST"])
def reject_handover(name, rejection_reason, details, request_id=None, evidence=None):
	return engine.reject_handover(
		name,
		rejection_reason=rejection_reason,
		details=details,
		request_id=request_id,
		evidence=_json(evidence, []),
	)


@frappe.whitelist(methods=["POST"])
def request_clarification(name, details, request_id=None, evidence=None):
	return engine.request_clarification(
		name, details=details, request_id=request_id, evidence=_json(evidence, [])
	)


@frappe.whitelist(methods=["POST"])
def revise_handover(name, request_id=None):
	doc = engine.revise_handover(name, request_id)
	return {"name": doc.name, "handover_status": doc.handover_status, "version_no": doc.version_no}


# -- reading -----------------------------------------------------------------------------------


@frappe.whitelist(methods=["GET"])
def get_handover_details(name):
	"""Everything the Handover Workspace shows: the record, its timeline, reviews, versions and ledger."""
	doc = frappe.get_doc(HANDOVER, name)
	doc.check_permission("read")

	data = doc.as_dict()
	data.pop("submission_snapshot", None)

	history = frappe.get_all(
		HANDOVER_HISTORY,
		filters={"handover": name},
		fields=[
			"event_type",
			"from_status",
			"to_status",
			"actor",
			"actor_name",
			"event_time",
			"remarks",
			"version_no",
		],
		order_by="event_time asc, creation asc",
	)
	reviews = [
		frappe.get_doc(HANDOVER_REVIEW, review).as_dict()
		for review in frappe.get_all(
			HANDOVER_REVIEW, filters={"handover": name}, order_by="reviewed_at asc", pluck="name"
		)
	]
	versions = frappe.get_all(
		HANDOVER,
		filters={"root_handover": doc.root_handover or doc.name},
		fields=["name", "version_no", "handover_status", "docstatus", "handover_type", "submitted_at"],
		order_by="version_no asc",
	)
	ownership = frappe.get_all(
		OWNERSHIP_HISTORY,
		filters={"task": doc.task},
		fields=[
			"sequence",
			"event_type",
			"handover",
			"from_user",
			"from_department",
			"from_team",
			"to_user",
			"to_department",
			"to_team",
			"accepted_by",
			"transferred_at",
			"reason",
		],
		order_by="sequence asc",
	)
	return {
		"doc": data,
		"history": history,
		"reviews": reviews,
		"versions": versions,
		"ownership": ownership,
		"allowed_actions": engine.get_allowed_actions(doc),
		"snapshot_verified": verify_snapshot(name) if doc.docstatus == 1 else None,
	}


def _page(filters, status, search, page, page_size):
	page = max(cint(page), 1)
	page_size = min(max(cint(page_size) or 20, 1), 100)
	filters = dict(filters)
	if status:
		filters["handover_status"] = status
	or_filters = None
	if search:
		like = f"%{search.strip()}%"
		or_filters = [
			["task_title", "like", like],
			["name", "like", like],
			["sender_name", "like", like],
			["receiver_name", "like", like],
		]
	total = frappe.get_list(
		HANDOVER, filters=filters, or_filters=or_filters, fields=[{"COUNT": "name", "as": "total"}]
	)[0].total
	rows = frappe.get_list(
		HANDOVER,
		filters=filters,
		or_filters=or_filters,
		fields=LIST_FIELDS,
		order_by="modified desc",
		start=(page - 1) * page_size,
		page_length=page_size,
	)
	return {"rows": rows, "total": total, "page": page, "page_size": page_size}


@frappe.whitelist(methods=["GET"])
def get_inbox(status=None, search=None, page=1, page_size=20):
	"""Handovers addressed to me (submitted only), newest first, paginated on the server."""
	return _page(
		{"receiver_user": frappe.session.user, "docstatus": 1}, status, search, page, page_size
	)


@frappe.whitelist(methods=["GET"])
def get_outbox(view=None, status=None, search=None, page=1, page_size=20):
	"""Handovers I sent. view: drafts, attention (rejected / needs clarification), sent; default all."""
	filters = {"sender_user": frappe.session.user}
	if view == "drafts":
		filters["docstatus"] = 0
	elif view == "attention":
		filters.update(
			docstatus=1,
			handover_status=("in", (REJECTED, CLARIFICATION)),
			superseded_by=("is", "not set"),
		)
	elif view == "sent":
		filters["docstatus"] = 1
	return _page(filters, status, search, page, page_size)


@frappe.whitelist(methods=["GET"])
def get_counts():
	"""Badge numbers for the Handover Center: only my own items, so nothing leaks across users."""
	me = frappe.session.user

	def count(**filters):
		return frappe.db.count(HANDOVER, filters)

	return {
		"inbox_pending": count(receiver_user=me, docstatus=1, handover_status=PENDING),
		"inbox_review": count(receiver_user=me, docstatus=1, handover_status=UNDER_REVIEW),
		"outbox_open": count(sender_user=me, docstatus=1, handover_status=("in", OPEN_STATUSES)),
		"needs_my_action": count(
			sender_user=me,
			docstatus=1,
			handover_status=("in", (REJECTED, CLARIFICATION)),
			superseded_by=("is", "not set"),
		),
		"drafts": count(sender_user=me, docstatus=0, handover_status=("in", (DRAFT, READY))),
	}
