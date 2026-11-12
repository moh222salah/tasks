import frappe
from frappe import _
from frappe.model.document import Document


class NDSTaskHandover(Document):
	def before_update_after_submit(self):
		frappe.throw(
			_("A submitted handover is an approved record and cannot be edited."), frappe.PermissionError
		)

	def on_trash(self):
		if self.docstatus != 0:
			frappe.throw(
				_("Submitted handovers are part of the audit trail and cannot be deleted."),
				frappe.PermissionError,
			)
