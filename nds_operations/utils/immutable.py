import frappe
from frappe import _
from frappe.model.document import Document


class ImmutableRecord(Document):
	"""Append-only record: inserted once by the module, never edited and never deleted.

	Frappe lets the Administrator bypass has_permission hooks, so the rule is enforced here,
	in the controller, where it applies to every user.
	"""

	def validate(self):
		if not self.is_new():
			frappe.throw(
				_("{0} records are append-only and cannot be modified.").format(_(self.doctype)),
				frappe.PermissionError,
			)

	def on_trash(self):
		frappe.throw(
			_("{0} records are part of the audit trail and cannot be deleted.").format(_(self.doctype)),
			frappe.PermissionError,
		)
