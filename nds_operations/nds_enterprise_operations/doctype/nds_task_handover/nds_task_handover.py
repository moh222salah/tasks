import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, cint, get_url_to_form, now_datetime

from nds_operations.constants import (
	DRAFT,
	HANDOVER,
	OPEN_STATUSES,
	PENDING,
	READY,
	SETTINGS,
)
from nds_operations.nds_enterprise_operations.doctype.nds_handover_attachment.nds_handover_attachment import (
	validate_attachment_rows,
)
from nds_operations.services.history import log_event
from nds_operations.services.notifications import notify
from nds_operations.services.ownership import assert_can_hand_over, get_current_owner, last_sequence
from nds_operations.services.snapshot import build_snapshot
from nds_operations.utils.people import (
	get_employee_for_user,
	get_employee_snapshot,
	get_primary_team,
	is_active_member,
)

# Set by the engine, never taken from a client. A draft saved from the form or the REST API keeps
# whatever the database holds for these, whatever the request says.
ENGINE_FIELDS = (
	"handover_type",
	"version_no",
	"previous_handover",
	"root_handover",
	"handover_status",
	"superseded_by",
	"client_request_id",
	"submit_request_id",
	"response_due",
	"submitted_at",
	"received_at",
	"received_by",
	"decided_at",
	"decided_by",
	"latest_review",
	"rejection_reason",
	"withdrawn_at",
	"withdraw_reason",
	"previous_owner",
	"new_owner",
	"responsibility_transferred_at",
	"previous_department",
	"new_department",
	"previous_team",
	"new_team",
	"ownership_seq_at_submit",
	"snapshot_hash",
	"submission_snapshot",
)
ENGINE_DEFAULTS = {"handover_type": "New", "version_no": 1, "handover_status": DRAFT}


class NDSTaskHandover(Document):
	# -- lifecycle -------------------------------------------------------------------------------

	def validate(self):
		# Runs for drafts and during submit (docstatus is already 1 but the stored row is still a draft).
		if not self._is_draft_phase():
			return
		self.guard_engine_fields()
		self.load_task_context()
		self.set_sender_identity()
		self.set_executor_identity()
		self.set_receiver_identity()
		self.validate_receiver()
		self.validate_sender_team()
		validate_attachment_rows(self.attachments)
		self.keep_ready_honest()

	def after_insert(self):
		if not self.root_handover:
			self.db_set("root_handover", self.name, update_modified=False)
		log_event(self, "Created", to_status=self.handover_status)

	def before_submit(self):
		if self.handover_status not in (DRAFT, READY):
			frappe.throw(_("Only a draft handover can be submitted."))
		self.was_ready = self.handover_status == READY
		self.validate_ready()

		# One lock on the task serialises every handover of that task (handover row, then task row).
		task = frappe.db.get_value(
			"Task", self.task, ["name", "department", "status"], as_dict=True, for_update=True
		)
		if not task:
			frappe.throw(_("Task {0} no longer exists.").format(self.task))
		if task.status in ("Cancelled", "Template"):
			frappe.throw(_("A {0} task cannot be handed over.").format(task.status))
		assert_can_hand_over(task, self.sender_user)

		other = frappe.db.sql(
			"select `name` from `tabNDS Task Handover` where `task` = %s and `docstatus` = 1 "
			"and `handover_status` in %s and ifnull(`superseded_by`, '') = '' and `name` != %s "
			"limit 1 for update",
			(self.task, OPEN_STATUSES, self.name),
		)
		if other:
			frappe.throw(
				_("Task {0} already has an open handover ({1}).").format(
					frappe.bold(self.task), frappe.bold(other[0][0])
				)
			)

		self.load_task_context()
		self.previous_owner = get_current_owner(self.task)
		self.ownership_seq_at_submit = last_sequence(self.task)
		self.previous_department = self.sender_department
		self.previous_team = self.sender_team
		now = now_datetime()
		self.submitted_at = now
		sla_hours = cint(frappe.get_cached_doc(SETTINGS).acceptance_sla_hours) or 48
		self.response_due = add_to_date(now, hours=sla_hours)
		self.handover_status = PENDING
		self.submission_snapshot, self.snapshot_hash = build_snapshot(self)

	def on_submit(self):
		if not self.was_ready:
			log_event(self, "Marked Ready", from_status=DRAFT, to_status=READY)
		log_event(
			self,
			"Submitted",
			from_status=READY,
			to_status=PENDING,
			remarks=self.snapshot_hash,
			request_id=self.submit_request_id,
		)
		notify(
			[self.receiver_user],
			_("Task handover {0} is waiting for your acceptance: {1}").format(self.name, self.task_title),
			self,
		)

	def before_update_after_submit(self):
		frappe.throw(
			_("A submitted handover is an approved record and cannot be edited."), frappe.PermissionError
		)

	def before_cancel(self):
		frappe.throw(
			_("A submitted handover cannot be cancelled. Withdraw it, or reject it as the receiver."),
			frappe.PermissionError,
		)

	def on_trash(self):
		if self.docstatus != 0:
			frappe.throw(
				_("Submitted handovers are part of the audit trail and cannot be deleted."),
				frappe.PermissionError,
			)

	# -- helpers ---------------------------------------------------------------------------------

	def _is_draft_phase(self):
		before = self.get_doc_before_save()
		return self.is_new() or before is None or before.docstatus == 0

	def guard_engine_fields(self):
		"""Engine-managed fields come from the database (or defaults), never from the request."""
		if self.flags.nds_engine:
			return
		before = None if self.is_new() else self.get_doc_before_save()
		for fieldname in ENGINE_FIELDS:
			if before is not None:
				self.set(fieldname, before.get(fieldname))
			else:
				self.set(fieldname, ENGINE_DEFAULTS.get(fieldname))

	def load_task_context(self):
		"""Copy the task facts a handover must carry. Refreshed while drafting, frozen at submission."""
		if not self.task:
			return  # the mandatory-field check reports it
		task = frappe.db.get_value(
			"Task",
			self.task,
			["subject", "status", "priority", "project", "department", "type", "description", "exp_end_date"],
			as_dict=True,
		)
		if not task:
			frappe.throw(_("Task {0} does not exist.").format(self.task))
		if self.is_new():
			assert_can_hand_over(
				frappe._dict(name=self.task, department=task.department), frappe.session.user
			)
			if task.status in ("Cancelled", "Template"):
				frappe.throw(_("A {0} task cannot be handed over.").format(task.status))
		self.task_title = task.subject
		self.task_status = task.status
		self.task_description = task.description
		self.task_due_date = task.exp_end_date
		self.project = self.project or task.project
		self.department = self.department or task.department
		self.task_category = self.task_category or task.type
		self.priority = self.priority or task.priority
		self.task_url = self.task_url or get_url_to_form("Task", self.task)

	def set_sender_identity(self):
		"""The sender is always the signed-in user; the request cannot choose who is sending."""
		user = frappe.session.user if self.is_new() else self.owner
		employee = get_employee_for_user(user)
		if not employee:
			frappe.throw(
				_("Your user account is not linked to an active Employee, so you cannot send handovers.")
			)
		info = get_employee_snapshot(employee)
		self.sender_user = user
		self.sender_employee = employee
		self.sender_name = info.employee_name
		self.sender_department = info.department
		self.sender_designation = info.designation
		self.sender_email = info.email
		if not self.sender_team:
			self.sender_team = get_primary_team(employee)

	def set_executor_identity(self):
		if not self.executor_employee:
			self.executor_employee = self.sender_employee
		info = get_employee_snapshot(self.executor_employee)
		self.executor_name = info.get("employee_name")
		self.executor_department = info.get("department")
		if not self.executor_team:
			self.executor_team = get_primary_team(self.executor_employee)

	def set_receiver_identity(self):
		info = get_employee_snapshot(self.receiver_employee)
		self.receiver_name = info.get("employee_name")
		self.receiver_user = info.get("user_id")
		self.receiver_department = info.get("department")
		self.receiver_designation = info.get("designation")
		self.receiver_email = info.get("email")
		if self.receiver_employee and not self.receiver_team:
			self.receiver_team = get_primary_team(self.receiver_employee)

	def validate_receiver(self):
		info = get_employee_snapshot(self.receiver_employee)
		if not info:
			frappe.throw(_("Choose the employee who will receive this handover."))
		if info.status != "Active":
			frappe.throw(_("{0} is not an active employee.").format(frappe.bold(info.employee_name)))
		if not info.user_id or not frappe.db.get_value("User", info.user_id, "enabled"):
			frappe.throw(
				_("{0} has no enabled user account and cannot receive handovers.").format(
					frappe.bold(info.employee_name)
				)
			)
		if info.user_id == self.sender_user:
			frappe.throw(_("You cannot hand a task over to yourself."))
		settings = frappe.get_cached_doc(SETTINGS)
		if not cint(settings.allow_cross_department_handover) and (
			self.sender_department != self.receiver_department
		):
			frappe.throw(_("Handovers between departments are disabled in NDS Operations Settings."))

	def validate_sender_team(self):
		for fieldname, employee in (
			("sender_team", self.sender_employee),
			("receiver_team", self.receiver_employee),
		):
			team = self.get(fieldname)
			if team and employee and not is_active_member(employee, team):
				frappe.throw(
					_("{0} is not an active member of team {1}.").format(
						frappe.bold(employee), frappe.bold(team)
					)
				)

	def keep_ready_honest(self):
		"""A draft that was marked Ready and then edited must be checked again."""
		before = self.get_doc_before_save()
		if self.flags.nds_engine or before is None or self.docstatus != 0:
			return
		if before.handover_status != READY:
			return
		if self.has_content_changed(before):
			self.handover_status = DRAFT

	def has_content_changed(self, before):
		for df in self.meta.fields:
			if df.read_only or df.fieldname in ENGINE_FIELDS or df.fieldtype == "Table":
				continue
			if (self.get(df.fieldname) or None) != (before.get(df.fieldname) or None):
				return True
		return [row.as_dict(no_default_fields=True) for row in self.attachments] != [
			row.as_dict(no_default_fields=True) for row in before.attachments
		]

	def validate_ready(self):
		"""Completeness rules for sending a handover; stricter ones are switchable in settings."""
		settings = frappe.get_cached_doc(SETTINGS)
		missing = []
		if not self.handover_reason:
			missing.append(_("Handover Reason"))
		if not self.receiver_employee:
			missing.append(_("Receiver"))
		if not (self.work_done or self.sender_notes or self.work_remaining):
			missing.append(_("Sender Notes (what was done / what is left)"))
		if cint(settings.require_attachment_on_submit) and not self.attachments:
			missing.append(_("Attachments"))
		if cint(settings.require_technical_diagnosis) and not self.technical_diagnosis:
			missing.append(_("Technical Diagnosis"))
		if cint(settings.require_solution_details) and not (
			self.solution_approach or self.implementation_steps
		):
			missing.append(_("Solution Approach"))
		if cint(settings.require_results) and not (self.completed_results or self.final_outcome):
			missing.append(_("Results"))
		if missing:
			frappe.throw(
				_("The handover is not ready. Missing: {0}").format(", ".join(missing)),
				title=_("Incomplete Handover"),
			)
