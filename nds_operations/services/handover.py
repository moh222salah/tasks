"""Handover engine: every state change of a submitted handover goes through here.

- a submitted handover is a frozen, hashed snapshot; only the engine moves its status;
- responsibility moves only when the receiver accepts, in the same transaction as the decision;
- lock order is always handover row first, Task row second, so concurrent actions neither deadlock
  nor transfer twice (the ledger also has a unique (task, sequence) key as the last line of defence);
- every action takes an optional request_id: a retried request returns the first result.
"""

import frappe
from frappe import _
from frappe.desk.form import assign_to
from frappe.model import no_value_fields
from frappe.utils import cint, get_fullname, now_datetime

from nds_operations.constants import (
	ACCEPTED,
	CLARIFICATION,
	DECIDABLE_STATUSES,
	DRAFT,
	HANDOVER,
	HANDOVER_REVIEW,
	OPEN_STATUSES,
	OWNERSHIP_HISTORY,
	PENDING,
	READY,
	REJECTED,
	SETTINGS,
	UNDER_REVIEW,
	WITHDRAWN,
)
from nds_operations.services.history import log_event
from nds_operations.services.notifications import manager_users, notify
from nds_operations.services.ownership import get_current_owner, last_sequence

NOT_COPIED_TO_REVISION = {"clarification_response"}
LEDGER_CONTENT = ("attachment_type", "title", "file", "url", "description")


# -- small helpers -----------------------------------------------------------------------------


def content_fieldnames():
	"""Fields a sender fills in. Identity, status and ledger fields belong to the engine."""
	skip = {"task", "receiver_employee", "attachments"}
	return [
		df.fieldname
		for df in frappe.get_meta(HANDOVER).fields
		if df.fieldtype not in no_value_fields and not df.read_only and df.fieldname not in skip
	]


def lock_handover(name):
	"""Load a handover under a row lock. Always the first lock of an action."""
	return frappe.get_doc(HANDOVER, name, for_update=True)


def _require_sender(doc):
	if frappe.session.user != doc.sender_user:
		frappe.throw(_("Only the sender of this handover can do that."), frappe.PermissionError)


def _require_receiver(doc):
	if frappe.session.user != doc.receiver_user:
		frappe.throw(
			_("Only {0}, the receiver of this handover, can respond to it.").format(
				frappe.bold(doc.receiver_name)
			),
			frappe.PermissionError,
		)


def _set(doc, values):
	"""Engine write on a submitted record (bypasses the controller guard on purpose)."""
	frappe.db.set_value(HANDOVER, doc.name, values)
	doc.update(values)


def _result(doc, **extra):
	return {"name": doc.name, "handover_status": doc.handover_status, "docstatus": doc.docstatus, **extra}


def _replayed(name, request_id):
	"""The review a previous call with the same request_id already recorded, if any (locking read)."""
	if not request_id:
		return None
	row = frappe.db.sql(
		"select `name`, `decision` from `tabNDS Handover Review` where `handover` = %s and `request_id` = %s "
		"for update",
		(name, request_id),
		as_dict=True,
	)
	return row[0] if row else None


# -- drafting ----------------------------------------------------------------------------------


def create_handover(task, receiver_employee, data=None, attachments=None, client_request_id=None):
	"""Create a draft handover for a task. Retrying with the same client_request_id returns the first draft."""
	user = frappe.session.user
	frappe.has_permission(HANDOVER, "create", throw=True)

	# Lock the task so two simultaneous creations (or a creation racing a submit) are serialised.
	task_row = frappe.db.get_value("Task", task, ["name", "status"], as_dict=True, for_update=True)
	if not task_row:
		frappe.throw(_("Task {0} does not exist.").format(task))

	if client_request_id:
		existing = frappe.db.get_value(
			HANDOVER, {"sender_user": user, "client_request_id": client_request_id}, "name"
		)
		if existing:
			return frappe.get_doc(HANDOVER, existing)

	open_handover = frappe.db.get_value(
		HANDOVER,
		{
			"task": task,
			"docstatus": 1,
			"handover_status": ("in", OPEN_STATUSES),
			"superseded_by": ("is", "not set"),
		},
		"name",
	)
	if open_handover:
		frappe.throw(
			_("Task {0} already has an open handover ({1}).").format(
				frappe.bold(task), frappe.bold(open_handover)
			)
		)

	handover_type, previous = "New", None
	last_accepted = frappe.db.get_value(
		HANDOVER,
		{"task": task, "docstatus": 1, "handover_status": ACCEPTED},
		"name",
		order_by="decided_at desc",
	)
	if last_accepted:
		handover_type, previous = "Re-handover", last_accepted

	allowed = set(content_fieldnames())
	values = {key: value for key, value in (data or {}).items() if key in allowed}
	doc = frappe.get_doc(
		{
			"doctype": HANDOVER,
			"task": task,
			"receiver_employee": receiver_employee,
			**values,
			"handover_type": handover_type,
			"previous_handover": previous,
			"client_request_id": client_request_id,
			"attachments": _clean_attachment_rows(attachments),
		}
	)
	doc.flags.nds_engine = True
	return doc.insert()


def _clean_attachment_rows(rows):
	return [{key: row.get(key) for key in LEDGER_CONTENT} for row in rows or []]


def update_draft(name, receiver_employee=None, data=None, attachments=None):
	doc = lock_handover(name)
	_require_sender(doc)
	if doc.docstatus != 0:
		frappe.throw(_("Only a draft can be edited. A submitted handover is a frozen record."))
	allowed = set(content_fieldnames())
	doc.update({key: value for key, value in (data or {}).items() if key in allowed})
	if receiver_employee:
		doc.receiver_employee = receiver_employee
	if attachments is not None:
		doc.set("attachments", _clean_attachment_rows(attachments))
	doc.save()
	return doc


def mark_ready(name):
	doc = lock_handover(name)
	_require_sender(doc)
	if doc.docstatus != 0:
		frappe.throw(_("This handover was already submitted."))
	if doc.handover_status == READY:
		return doc
	doc.validate_ready()
	_set(doc, {"handover_status": READY})
	log_event(doc, "Marked Ready", from_status=DRAFT, to_status=READY)
	return doc


def reopen_draft(name):
	doc = lock_handover(name)
	_require_sender(doc)
	if doc.docstatus != 0:
		frappe.throw(_("This handover was already submitted."))
	if doc.handover_status == DRAFT:
		return doc
	_set(doc, {"handover_status": DRAFT})
	log_event(doc, "Reopened As Draft", from_status=READY, to_status=DRAFT)
	return doc


# -- submission --------------------------------------------------------------------------------


def submit_handover(name, request_id=None):
	"""Send the handover to the receiver. A retry with the same request_id returns the first result."""
	doc = lock_handover(name)
	_require_sender(doc)
	if doc.docstatus == 1:
		if request_id and doc.submit_request_id == request_id:
			return _result(doc, replayed=True)
		frappe.throw(_("This handover was already submitted ({0}).").format(doc.handover_status))
	if doc.docstatus != 0:
		frappe.throw(_("This handover is cancelled."))
	frappe.has_permission(HANDOVER, "submit", throw=True)

	doc.flags.nds_engine = True
	doc.flags.ignore_permissions = True
	doc.submit_request_id = request_id
	doc.submit()
	return _result(doc, replayed=False)


def withdraw_handover(name, reason, request_id=None):
	"""The sender takes back a handover nobody has decided yet. Responsibility never moved."""
	doc = lock_handover(name)
	_require_sender(doc)
	if doc.docstatus != 1:
		frappe.throw(_("Only a submitted handover can be withdrawn."))
	if doc.handover_status == WITHDRAWN:
		return _result(doc, replayed=True)
	if doc.handover_status not in OPEN_STATUSES or doc.superseded_by:
		frappe.throw(_("A {0} handover cannot be withdrawn.").format(doc.handover_status))
	if not (reason or "").strip():
		frappe.throw(_("Please give a reason for withdrawing the handover."))

	old_status = doc.handover_status
	_set(doc, {"handover_status": WITHDRAWN, "withdrawn_at": now_datetime(), "withdraw_reason": reason})
	log_event(
		doc, "Withdrawn", from_status=old_status, to_status=WITHDRAWN, remarks=reason, request_id=request_id
	)
	notify([doc.receiver_user], _("Handover {0} was withdrawn by the sender.").format(doc.name), doc)
	return _result(doc, replayed=False)


# -- the receiver's side -----------------------------------------------------------------------


def start_review(name):
	"""The receiver opens the handover for review. Nothing moves; the sender can see it was received."""
	doc = lock_handover(name)
	_require_receiver(doc)
	if doc.docstatus != 1:
		frappe.throw(_("This handover has not been submitted."))
	if doc.handover_status == UNDER_REVIEW:
		return _result(doc, replayed=True)
	if doc.handover_status != PENDING:
		frappe.throw(_("A {0} handover cannot be opened for review.").format(doc.handover_status))
	_set(
		doc,
		{"handover_status": UNDER_REVIEW, "received_at": now_datetime(), "received_by": frappe.session.user},
	)
	log_event(doc, "Received", from_status=PENDING, to_status=UNDER_REVIEW)
	notify(
		[doc.sender_user], _("{0} started reviewing handover {1}.").format(doc.receiver_name, doc.name), doc
	)
	return _result(doc, replayed=False)


def accept_handover(
	name,
	*,
	confirmed_details_reviewed=0,
	confirmed_attachments_received=0,
	confirmed_responsibilities_understood=0,
	details=None,
	next_step=None,
	expected_start=None,
	request_id=None,
):
	doc = lock_handover(name)
	_require_receiver(doc)
	replay = _replayed(name, request_id)
	if replay:
		return _result(doc, review=replay.name, decision=replay.decision, replayed=True)
	_require_decidable(doc)

	if not (
		cint(confirmed_details_reviewed)
		and cint(confirmed_attachments_received)
		and cint(confirmed_responsibilities_understood)
	):
		frappe.throw(
			_("Confirm that you reviewed the details and attachments and understand the responsibilities.")
		)

	plan = _plan_transfer(doc)
	review = _record_review(
		doc,
		ACCEPTED,
		request_id=request_id,
		details=details,
		next_step=next_step,
		expected_start=expected_start,
		confirmations=(
			confirmed_details_reviewed,
			confirmed_attachments_received,
			confirmed_responsibilities_understood,
		),
	)
	now = now_datetime()
	old_status = doc.handover_status
	_set(
		doc,
		{
			"handover_status": ACCEPTED,
			"decided_at": now,
			"decided_by": frappe.session.user,
			"latest_review": review.name,
			"received_at": doc.received_at or now,
			"received_by": doc.received_by or frappe.session.user,
		},
	)
	log_event(
		doc,
		"Accepted",
		from_status=old_status,
		to_status=ACCEPTED,
		review=review.name,
		request_id=request_id,
		remarks=details,
	)
	_transfer_responsibility(doc, review, now, plan)

	recipients = [doc.sender_user, doc.previous_owner]
	if doc.sender_department != doc.receiver_department:
		recipients += manager_users([doc.sender_department, doc.receiver_department])
	notify(
		recipients,
		_("Handover {0} was accepted by {1}. Responsibility moved.").format(doc.name, doc.receiver_name),
		doc,
	)
	return _result(doc, review=review.name, decision=ACCEPTED, replayed=False)


def reject_handover(name, *, rejection_reason, details, request_id=None, evidence=None):
	doc = lock_handover(name)
	_require_receiver(doc)
	replay = _replayed(name, request_id)
	if replay:
		return _result(doc, review=replay.name, decision=replay.decision, replayed=True)
	_require_decidable(doc)

	if not rejection_reason:
		frappe.throw(_("A rejection reason is mandatory."))
	if not frappe.db.exists("NDS Rejection Reason", rejection_reason):
		frappe.throw(_("Unknown rejection reason {0}.").format(frappe.bold(rejection_reason)))
	if not (details or "").strip():
		frappe.throw(_("Explain what is wrong so the sender can fix it."))

	review = _record_review(
		doc,
		REJECTED,
		request_id=request_id,
		details=details,
		rejection_reason=rejection_reason,
		evidence=evidence,
	)
	now = now_datetime()
	old_status = doc.handover_status
	_set(
		doc,
		{
			"handover_status": REJECTED,
			"decided_at": now,
			"decided_by": frappe.session.user,
			"latest_review": review.name,
			"rejection_reason": rejection_reason,
		},
	)
	log_event(
		doc,
		"Rejected",
		from_status=old_status,
		to_status=REJECTED,
		review=review.name,
		request_id=request_id,
		remarks=details,
	)

	recipients = [doc.sender_user]
	settings = frappe.get_cached_doc(SETTINGS)
	if cint(settings.notify_managers_on_rejection):
		recipients += manager_users([doc.sender_department], [doc.sender_team])
	notify(recipients, _("Handover {0} was rejected: {1}").format(doc.name, _(rejection_reason)), doc)
	return _result(doc, review=review.name, decision=REJECTED, replayed=False)


def request_clarification(name, *, details, request_id=None, evidence=None):
	doc = lock_handover(name)
	_require_receiver(doc)
	replay = _replayed(name, request_id)
	if replay:
		return _result(doc, review=replay.name, decision=replay.decision, replayed=True)
	_require_decidable(doc)
	if not (details or "").strip():
		frappe.throw(_("Write the questions or the missing information you need."))

	review = _record_review(doc, CLARIFICATION, request_id=request_id, details=details, evidence=evidence)
	old_status = doc.handover_status
	_set(
		doc,
		{
			"handover_status": CLARIFICATION,
			"decided_at": now_datetime(),
			"decided_by": frappe.session.user,
			"latest_review": review.name,
		},
	)
	log_event(
		doc,
		"Clarification Requested",
		from_status=old_status,
		to_status=CLARIFICATION,
		review=review.name,
		request_id=request_id,
		remarks=details,
	)
	notify(
		[doc.sender_user],
		_("{0} needs clarification on handover {1}.").format(doc.receiver_name, doc.name),
		doc,
	)
	return _result(doc, review=review.name, decision=CLARIFICATION, replayed=False)


def _require_decidable(doc):
	_require_receiver(doc)
	if doc.docstatus != 1:
		frappe.throw(_("This handover has not been submitted."))
	if doc.handover_status not in DECIDABLE_STATUSES:
		frappe.throw(
			_("Handover {0} is {1}; it can no longer be decided.").format(
				frappe.bold(doc.name), frappe.bold(doc.handover_status)
			)
		)


def _record_review(
	doc,
	decision,
	*,
	request_id=None,
	details=None,
	rejection_reason=None,
	next_step=None,
	expected_start=None,
	confirmations=(0, 0, 0),
	evidence=None,
):
	user = frappe.session.user
	return frappe.get_doc(
		{
			"doctype": HANDOVER_REVIEW,
			"handover": doc.name,
			"task": doc.task,
			"version_no": doc.version_no,
			"decision": decision,
			"reviewer_user": user,
			"reviewer_employee": doc.receiver_employee,
			"reviewer_name": get_fullname(user),
			"reviewed_at": now_datetime(),
			"request_id": request_id,
			"rejection_reason": rejection_reason,
			"details": details,
			"next_step": next_step,
			"expected_start": expected_start,
			"confirmed_details_reviewed": cint(confirmations[0]),
			"confirmed_attachments_received": cint(confirmations[1]),
			"confirmed_responsibilities_understood": cint(confirmations[2]),
			"evidence": _clean_attachment_rows(evidence),
		}
	).insert(ignore_permissions=True)


# -- responsibility transfer -------------------------------------------------------------------


def _plan_transfer(doc):
	"""Lock the task and prove the transfer is still valid, before anything is written."""
	task = frappe.db.get_value(
		"Task", doc.task, ["name", "department", "status"], as_dict=True, for_update=True
	)
	if not task:
		frappe.throw(_("Task {0} no longer exists.").format(doc.task))

	sequence = last_sequence(doc.task)
	if sequence != cint(doc.ownership_seq_at_submit) or get_current_owner(doc.task) != doc.previous_owner:
		frappe.throw(
			_(
				"The ownership of task {0} changed after this handover was submitted. "
				"Ask the sender to submit a new handover."
			).format(frappe.bold(doc.task)),
			title=_("Ownership Changed"),
		)
	previous_employee = (
		doc.sender_employee
		if doc.previous_owner == doc.sender_user
		else frappe.db.get_value("Employee", {"user_id": doc.previous_owner, "status": "Active"}, "name")
	)
	return frappe._dict(task=task, sequence=sequence, previous_employee=previous_employee)


def _transfer_responsibility(doc, review, now, plan):
	"""Move the task to the receiver. Runs inside the accept transaction, after the handover row is locked."""
	task, sequence, previous_employee = plan.task, plan.sequence, plan.previous_employee
	previous_user = doc.previous_owner

	if sequence == 0:
		sequence += 1
		_ledger_row(
			doc.task,
			sequence,
			"Initial Assignment",
			to_user=previous_user,
			to_employee=previous_employee,
			to_department=doc.previous_department,
			to_team=doc.previous_team,
			transferred_at=frappe.db.get_value("Task", doc.task, "creation"),
			reason=_("Owner before the first handover"),
		)
	sequence += 1
	_ledger_row(
		doc.task,
		sequence,
		"Handover Accepted",
		handover=doc.name,
		from_user=previous_user,
		from_employee=previous_employee,
		from_department=doc.previous_department,
		from_team=doc.previous_team,
		to_user=doc.receiver_user,
		to_employee=doc.receiver_employee,
		to_department=doc.receiver_department,
		to_team=doc.receiver_team,
		accepted_by=frappe.session.user,
		transferred_at=now,
		reason=doc.handover_reason,
	)

	_move_assignment(doc, previous_user)
	if doc.receiver_department and doc.receiver_department != task.department:
		frappe.db.set_value("Task", doc.task, "department", doc.receiver_department)

	_set(
		doc,
		{
			"new_owner": doc.receiver_user,
			"new_department": doc.receiver_department,
			"new_team": doc.receiver_team,
			"responsibility_transferred_at": now,
		},
	)
	log_event(
		doc,
		"Responsibility Transferred",
		remarks=_("{0} → {1}").format(previous_user, doc.receiver_user),
		review=review.name,
	)
	frappe.get_doc("Task", doc.task).add_comment(
		"Info",
		_("Responsibility moved from {0} to {1} by accepted handover {2}.").format(
			previous_user, doc.receiver_user, doc.name
		),
	)


def _ledger_row(task, sequence, event_type, **values):
	frappe.get_doc(
		{"doctype": OWNERSHIP_HISTORY, "task": task, "sequence": sequence, "event_type": event_type, **values}
	).insert(ignore_permissions=True)


def _move_assignment(doc, previous_user):
	"""Mirror the transfer in the ToDo assignments the ERPNext Task already uses."""
	for todo in frappe.get_all(
		"ToDo",
		filters={
			"reference_type": "Task",
			"reference_name": doc.task,
			"allocated_to": previous_user,
			"status": "Open",
		},
		pluck="name",
	):
		assign_to.set_status(
			"Task", doc.task, todo=todo, assign_to=previous_user, status="Cancelled", ignore_permissions=True
		)
	# Share the task first, with the engine's authority: the receiver may not be allowed to share it,
	# and assign_to would otherwise check that permission as the receiver.
	if not frappe.has_permission("Task", "write", doc=doc.task, user=doc.receiver_user):
		frappe.share.add_docshare(
			"Task", doc.task, doc.receiver_user, read=1, write=1, flags={"ignore_share_permission": True}
		)
	assign_to._add(
		{
			"assign_to": [doc.receiver_user],
			"doctype": "Task",
			"name": doc.task,
			"description": _("Accepted handover {0} from {1}").format(doc.name, doc.sender_name),
			"assigned_by": doc.sender_user,
		},
		ignore_permissions=True,
	)


# -- after a rejection or a clarification request ----------------------------------------------


def revise_handover(name, request_id=None):
	"""The sender answers a rejection or clarification request: a new draft, version + 1, same content.

	The earlier version stays untouched as history and points to its successor with superseded_by.
	"""
	old = lock_handover(name)
	_require_sender(old)
	if old.docstatus != 1 or old.handover_status not in (REJECTED, CLARIFICATION):
		frappe.throw(_("Only a rejected handover or one needing clarification can be revised."))
	if old.superseded_by:
		if request_id and frappe.db.exists(
			"NDS Handover History",
			{"handover": old.name, "event_type": "Superseded", "request_id": request_id},
		):
			return frappe.get_doc(HANDOVER, old.superseded_by)
		frappe.throw(_("A newer version already exists: {0}.").format(frappe.bold(old.superseded_by)))

	skip = {
		"name",
		"owner",
		"creation",
		"modified",
		"modified_by",
		"docstatus",
		"idx",
		"attachments",
		"doctype",
	}
	values = {
		fieldname: old.get(fieldname)
		for fieldname in content_fieldnames()
		if fieldname not in skip | NOT_COPIED_TO_REVISION
	}
	new = frappe.get_doc(
		{
			"doctype": HANDOVER,
			"task": old.task,
			"receiver_employee": old.receiver_employee,
			**values,
			"handover_type": "Revision",
			"version_no": cint(old.version_no) + 1,
			"previous_handover": old.name,
			"root_handover": old.root_handover or old.name,
			"attachments": _clean_attachment_rows(old.attachments),
		}
	)
	new.flags.nds_engine = True
	new.insert()
	copy_attachment_files(old.name, new)

	frappe.db.set_value(HANDOVER, old.name, "superseded_by", new.name)
	log_event(old, "Superseded", remarks=new.name, request_id=request_id)
	log_event(new, "Revision Created", remarks=_("Revision of {0}").format(old.name))
	return new


def copy_attachment_files(source, target):
	"""Attach copies of the source handover's files to the target so private-file access follows the new draft."""
	files = frappe.get_all(
		"File",
		filters={"attached_to_doctype": HANDOVER, "attached_to_name": source},
		fields=["file_name", "file_url", "is_private", "attached_to_field"],
	)
	for item in files:
		frappe.get_doc(
			{
				"doctype": "File",
				"file_name": item.file_name,
				"file_url": item.file_url,
				"is_private": item.is_private,
				"attached_to_doctype": HANDOVER,
				"attached_to_name": target.name,
				"attached_to_field": item.attached_to_field,
			}
		).insert(ignore_permissions=True)


# -- what the UI may offer ---------------------------------------------------------------------


def get_allowed_actions(doc, user=None):
	"""Buttons the user may use right now. Advisory only: every action re-checks on the server."""
	user = user or frappe.session.user
	actions = []
	status = doc.handover_status
	if doc.docstatus == 0 and doc.sender_user == user:
		actions = ["save", "submit"] + (["mark_ready"] if status == DRAFT else ["reopen_draft"])
	elif doc.docstatus == 1:
		if doc.receiver_user == user and status in DECIDABLE_STATUSES:
			actions = ["accept", "reject", "request_clarification"]
			if status == PENDING:
				actions.insert(0, "start_review")
		if doc.sender_user == user:
			if status in OPEN_STATUSES and not doc.superseded_by:
				actions.append("withdraw")
			if status in (REJECTED, CLARIFICATION) and not doc.superseded_by:
				actions.append("revise")
		if status == ACCEPTED and doc.receiver_user == user and get_current_owner(doc.task) == user:
			actions.append("handover_again")
	return actions
