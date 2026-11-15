import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, now_datetime

from nds_operations.services.ownership import get_current_owner


def _assert_owner(task):
	if get_current_owner(task) != frappe.session.user:
		frappe.throw(
			_("Only the current owner of {0} can change its checklist.").format(frappe.bold(task)),
			frappe.PermissionError,
		)


class NDSTaskChecklist(Document):
	def validate(self):
		if not self.is_new() and self.task != self.get_doc_before_save().task:
			frappe.throw(_("A checklist item cannot move to another task."), frappe.PermissionError)
		_assert_owner(self.task)
		if frappe.db.get_value("Task", self.task, "status") in ("Completed", "Cancelled"):
			frappe.throw(_("The checklist of a closed task cannot be changed."))
		if cint(self.is_done):
			if self.is_new() or not cint(self.get_doc_before_save().is_done):
				self.done_by = frappe.session.user
				self.done_at = now_datetime()
		else:
			self.done_by = None
			self.done_at = None

	def on_trash(self):
		_assert_owner(self.task)
		if cint(self.is_done):
			frappe.throw(
				_("A completed checklist item is part of the record and cannot be deleted."),
				frappe.PermissionError,
			)


def guard_task_completion(doc, method=None):
	"""A Task cannot be completed while a required checklist item is still open."""
	if doc.is_new() or doc.status != "Completed":
		return
	open_items = frappe.get_all(
		"NDS Task Checklist",
		filters={"task": doc.name, "is_required": 1, "is_done": 0},
		pluck="title",
		limit=5,
	)
	if open_items:
		frappe.throw(
			_("Required checklist items are still open: {0}").format(", ".join(open_items)),
			title=_("Checklist incomplete"),
		)
