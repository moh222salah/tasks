import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate

from nds_operations.constants import TEAM_MEMBERSHIP
from nds_operations.permissions import clear_scope_cache


class NDSTeam(Document):
	def validate(self):
		self.team_name = (self.team_name or "").strip()
		self.validate_leadership()

	def validate_leadership(self):
		if self.team_lead and self.team_lead == self.deputy_lead:
			frappe.throw(_("Team Lead and Deputy Lead must be different employees."))

		company = frappe.db.get_value("Department", self.department, "company")
		for fieldname in ("team_lead", "deputy_lead"):
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
		self.sync_leadership_memberships()
		clear_scope_cache()

	def on_trash(self):
		clear_scope_cache()

	def sync_leadership_memberships(self):
		"""Keep the lead and deputy listed as members with the matching role."""
		wanted = {}
		if self.team_lead:
			wanted[self.team_lead] = "Leader"
		if self.deputy_lead:
			wanted[self.deputy_lead] = "Deputy Leader"

		for employee, role in wanted.items():
			current = frappe.db.get_value(
				TEAM_MEMBERSHIP,
				{"team": self.name, "employee": employee, "status": "Active"},
				["name", "role_in_team"],
				as_dict=True,
			)
			if not current:
				frappe.get_doc(
					{
						"doctype": TEAM_MEMBERSHIP,
						"team": self.name,
						"employee": employee,
						"role_in_team": role,
						"from_date": nowdate(),
					}
				).insert(ignore_permissions=True)
			elif current.role_in_team != role:
				frappe.db.set_value(TEAM_MEMBERSHIP, current.name, "role_in_team", role)

		stale = frappe.get_all(
			TEAM_MEMBERSHIP,
			filters={
				"team": self.name,
				"status": "Active",
				"role_in_team": ("in", ("Leader", "Deputy Leader")),
				"employee": ("not in", list(wanted) or [""]),
			},
			pluck="name",
		)
		for name in stale:
			frappe.db.set_value(TEAM_MEMBERSHIP, name, "role_in_team", "Member")
