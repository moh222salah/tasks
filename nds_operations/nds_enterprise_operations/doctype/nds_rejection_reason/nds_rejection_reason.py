from frappe.model.document import Document


class NDSRejectionReason(Document):
	def validate(self):
		self.reason_name = (self.reason_name or "").strip()
