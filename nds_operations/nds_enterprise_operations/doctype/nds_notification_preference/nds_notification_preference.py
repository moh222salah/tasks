import frappe
from frappe import _
from frappe.model.document import Document


class NDSNotificationPreference(Document):
	def validate(self):
		if self.is_new() and frappe.session.user not in (self.user, "Administrator"):
			if "System Manager" not in frappe.get_roles():
				frappe.throw(_("You can only change your own notification preferences."), frappe.PermissionError)
