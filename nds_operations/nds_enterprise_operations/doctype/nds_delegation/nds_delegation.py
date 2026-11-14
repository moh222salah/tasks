import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime, nowdate

from nds_operations.constants import ROLE_OPS_MANAGER
from nds_operations.permissions import clear_scope_cache
from nds_operations.utils.people import get_employee_for_user

IMMUTABLE_AFTER_INSERT = ("delegator", "delegate", "valid_from", "valid_to", "reason")


class NDSDelegation(Document):
	def validate(self):
		if self.is_new():
			self.validate_parties()
			self.validate_dates()
			self.validate_actor()
		else:
			self.validate_only_revocation_changes()
		self.set_status()

	def after_insert(self):
		clear_scope_cache()

	def on_update(self):
		clear_scope_cache()

	def on_trash(self):
		frappe.throw(
			_("Delegations are part of the audit trail and cannot be deleted. Revoke it instead."),
			frappe.PermissionError,
		)

	def validate_parties(self):
		if self.delegator == self.delegate:
			frappe.throw(_("You cannot delegate to yourself."))
		for user in (self.delegator, self.delegate):
			if not frappe.db.get_value("User", user, "enabled"):
				frappe.throw(_("{0} is not an enabled user.").format(frappe.bold(user)))
			if not get_employee_for_user(user):
				frappe.throw(_("{0} is not linked to an active Employee.").format(frappe.bold(user)))

	def validate_dates(self):
		if getdate(self.valid_to) < getdate(self.valid_from):
			frappe.throw(_("To date cannot be before From date."))
		if getdate(self.valid_to) < getdate(nowdate()):
			frappe.throw(_("A delegation cannot end in the past."))

	def validate_actor(self):
		"""Only the delegator himself (or an operations manager) can grant authority over his handovers."""
		user = frappe.session.user
		roles = set(frappe.get_roles(user))
		if user in (self.delegator, "Administrator") or roles & {"System Manager", ROLE_OPS_MANAGER}:
			return
		frappe.throw(
			_("Only {0} or an operations manager can delegate his handovers.").format(
				frappe.bold(self.delegator)
			),
			frappe.PermissionError,
		)

	def validate_only_revocation_changes(self):
		before = self.get_doc_before_save()
		for fieldname in IMMUTABLE_AFTER_INSERT:
			if str(self.get(fieldname) or "") != str(before.get(fieldname) or ""):
				frappe.throw(
					_("A delegation cannot be edited. Revoke it and create a new one."),
					frappe.PermissionError,
				)
		if before.is_revoked and not self.is_revoked:
			frappe.throw(_("A revoked delegation cannot be re-activated."), frappe.PermissionError)
		if self.is_revoked and not before.is_revoked:
			user = frappe.session.user
			roles = set(frappe.get_roles(user))
			if not (
				user in (self.delegator, "Administrator") or roles & {"System Manager", ROLE_OPS_MANAGER}
			):
				frappe.throw(_("Only the delegator can revoke this delegation."), frappe.PermissionError)
			self.revoked_at = now_datetime()
			self.revoked_by = user

	def set_status(self):
		today = getdate(nowdate())
		if self.is_revoked:
			self.status = "Revoked"
		elif getdate(self.valid_to) < today:
			self.status = "Expired"
		elif getdate(self.valid_from) > today:
			self.status = "Scheduled"
		else:
			self.status = "Active"


@frappe.whitelist(methods=["POST"])
def revoke_delegation(name):
	doc = frappe.get_doc("NDS Delegation", name)
	doc.is_revoked = 1
	doc.save()
	return {"name": doc.name, "status": doc.status}
