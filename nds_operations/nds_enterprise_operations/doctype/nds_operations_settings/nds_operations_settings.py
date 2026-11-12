import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class NDSOperationsSettings(Document):
	def validate(self):
		for fieldname, label in (
			("acceptance_sla_hours", _("Receiver Response SLA (hours)")),
			("repeated_rejection_threshold", _("Repeated Rejection Alert Threshold")),
		):
			if cint(self.get(fieldname)) < 1:
				frappe.throw(_("{0} must be at least 1.").format(label))
