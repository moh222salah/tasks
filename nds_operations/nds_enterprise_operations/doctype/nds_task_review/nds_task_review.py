import frappe
from frappe import _
from frappe.utils import now_datetime

from nds_operations.constants import ROLE_DEPT_MANAGER, ROLE_EXECUTIVE, ROLE_OPS_MANAGER, ROLE_REVIEWER
from nds_operations.services.ownership import get_current_owner
from nds_operations.utils.immutable import ImmutableRecord

REVIEWER_ROLES = {ROLE_REVIEWER, ROLE_DEPT_MANAGER, ROLE_OPS_MANAGER, ROLE_EXECUTIVE}


class NDSTaskReview(ImmutableRecord):
	def validate(self):
		super().validate()
		user = frappe.session.user
		if not REVIEWER_ROLES & set(frappe.get_roles(user)):
			frappe.throw(_("You are not a reviewer."), frappe.PermissionError)
		if frappe.db.get_value("Task", self.task, "status") != "Completed":
			frappe.throw(_("Only a completed task can be reviewed."))
		owner = get_current_owner(self.task)
		if user == owner or frappe.db.exists("NDS Ownership History", {"task": self.task, "from_user": user}):
			frappe.throw(_("Nobody can review work he owned himself."), frappe.PermissionError)
		if self.verdict == "Approved" and not 1 <= (self.quality_score or 0) <= 5:
			frappe.throw(_("An approval needs a quality score from 1 to 5."))
		if self.verdict != "Approved":
			self.quality_score = None
		self.reviewer = user
		self.reviewed_at = now_datetime()
		self.reviewed_owner = owner
