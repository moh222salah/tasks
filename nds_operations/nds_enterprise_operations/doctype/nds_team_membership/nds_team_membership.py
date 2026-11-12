import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate

from nds_operations.constants import TEAM_MEMBERSHIP
from nds_operations.permissions import clear_scope_cache


class NDSTeamMembership(Document):
	def validate(self):
		self.validate_dates()
		self.validate_references()
		self.set_status()
		self.validate_no_overlap()
		self.validate_primary()

	def validate_dates(self):
		if self.to_date and getdate(self.to_date) < getdate(self.from_date):
			frappe.throw(_("To date cannot be before From date."))

	def validate_references(self):
		if not self.is_new():
			return
		if frappe.db.get_value("Employee", self.employee, "status") != "Active":
			frappe.throw(_("Only Active employees can be added to a team."))
		if not frappe.db.get_value("NDS Team", self.team, "is_active"):
			frappe.throw(_("Team {0} is not active.").format(frappe.bold(self.team)))

	def set_status(self):
		ended = self.to_date and getdate(self.to_date) < getdate(nowdate())
		self.status = "Inactive" if ended else "Active"

	def validate_no_overlap(self):
		overlapping = frappe.get_all(
			TEAM_MEMBERSHIP,
			filters={
				"team": self.team,
				"employee": self.employee,
				"name": ("!=", self.name or ""),
				"from_date": ("<=", self.to_date or "9999-12-31"),
			},
			or_filters=[["to_date", "is", "not set"], ["to_date", ">=", self.from_date]],
			pluck="name",
		)
		if overlapping:
			frappe.throw(
				_("{0} already has an overlapping membership in this team ({1}).").format(
					frappe.bold(self.employee), overlapping[0]
				)
			)

	def validate_primary(self):
		if not self.is_primary or self.status != "Active":
			return
		other = frappe.get_all(
			TEAM_MEMBERSHIP,
			filters={
				"employee": self.employee,
				"is_primary": 1,
				"status": "Active",
				"name": ("!=", self.name or ""),
			},
			pluck="team",
		)
		if other:
			frappe.throw(
				_("{0} already has a primary team ({1}). Clear it there first.").format(
					frappe.bold(self.employee), other[0]
				)
			)

	def on_update(self):
		clear_scope_cache()

	def on_trash(self):
		clear_scope_cache()


def refresh_membership_status():
	"""Daily job: memberships whose end date has passed become Inactive."""
	expired = frappe.get_all(
		TEAM_MEMBERSHIP, filters={"status": "Active", "to_date": ("<", nowdate())}, pluck="name"
	)
	for name in expired:
		frappe.db.set_value(TEAM_MEMBERSHIP, name, "status", "Inactive", update_modified=False)
	clear_scope_cache()
