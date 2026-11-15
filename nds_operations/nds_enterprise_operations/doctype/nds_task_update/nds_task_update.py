import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from nds_operations.constants import OPEN_STATUSES
from nds_operations.services.ownership import get_current_owner
from nds_operations.utils.immutable import ImmutableRecord


class NDSTaskUpdate(ImmutableRecord):
	def validate(self):
		super().validate()
		# identity comes from the session, never from the request
		self.author = frappe.session.user
		self.posted_at = now_datetime()
		task = frappe.db.get_value("Task", self.task, ["status"], as_dict=True)
		if not task:
			frappe.throw(_("Task {0} does not exist.").format(self.task))
		if task.status in ("Completed", "Cancelled"):
			frappe.throw(_("{0} tasks cannot receive updates.").format(_(task.status)))
		if get_current_owner(self.task) != self.author:
			frappe.throw(
				_("Only the current owner of {0} can post updates on it.").format(frappe.bold(self.task)),
				frappe.PermissionError,
			)
		if self.progress is not None and not 0 <= flt(self.progress) <= 100:
			frappe.throw(_("Progress must be between 0 and 100."))
		if self.update_type == "Progress" and not cint(self.progress) and not (self.note or "").strip():
			frappe.throw(_("A progress update needs a note."))

	def after_insert(self):
		if self.update_type == "Progress" and self.progress is not None:
			frappe.db.set_value("Task", self.task, "progress", flt(self.progress), update_modified=False)
