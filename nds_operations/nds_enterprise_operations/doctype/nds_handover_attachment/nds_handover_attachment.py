import frappe
from frappe import _
from frappe.model.document import Document


class NDSHandoverAttachment(Document):
	pass


def validate_attachment_rows(rows):
	"""Child controllers are not validated by Frappe, so parents call this."""
	for row in rows or []:
		if not (row.file or row.url):
			frappe.throw(_("Attachment row #{0}: add a file or a link.").format(row.idx))
