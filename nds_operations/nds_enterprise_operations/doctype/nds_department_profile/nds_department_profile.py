import frappe
from frappe import _
from frappe.model.document import Document

from nds_operations.permissions import clear_scope_cache


class NDSDepartmentProfile(Document):
	def validate(self):
		if self.department_manager and self.department_manager == self.deputy_manager:
			frappe.throw(_("Department Manager and Deputy Manager must be different employees."))

		company = frappe.db.get_value("Department", self.department, "company")
		for fieldname in ("department_manager", "deputy_manager"):
			employee = self.get(fieldname)
			if not employee:
				continue
			row = frappe.db.get_value("Employee", employee, ["status", "company"], as_dict=True)
			if not row:
				continue
			if row.status != "Active":
				frappe.throw(_("{0} must be an Active employee.").format(frappe.bold(employee)))
			if company and row.company != company:
				frappe.throw(
					_("{0} does not belong to the company of department {1}.").format(
						frappe.bold(employee), frappe.bold(self.department)
					)
				)

	def on_update(self):
		clear_scope_cache()

	def on_trash(self):
		clear_scope_cache()
