import frappe
from frappe.utils import add_days, nowdate

from nds_operations.api.handover import get_inbox
from nds_operations.constants import DELEGATION, HANDOVER, HANDOVER_REVIEW
from nds_operations.services import handover as engine
from nds_operations.services.ownership import get_current_owner
from nds_operations.tests.utils import NDSTestCase, act_as

CONFIRM = {
	"confirmed_details_reviewed": 1,
	"confirmed_attachments_received": 1,
	"confirmed_responsibilities_understood": 1,
}


class TestDelegation(NDSTestCase):
	def submitted(self):
		act_as("Administrator")
		task = self.new_task()
		act_as(self.sender)
		doc = engine.create_handover(
			task.name,
			self.receiver_employee,
			{"handover_reason": "Reassignment", "work_done": "Done so far."},
		)
		engine.submit_handover(doc.name)
		return task, doc

	def delegate(self, delegate, start=0, end=5, by=None, delegator=None):
		act_as(by or self.receiver)
		return frappe.get_doc(
			{
				"doctype": DELEGATION,
				"delegator": delegator or self.receiver,
				"delegate": delegate,
				"valid_from": add_days(nowdate(), start),
				"valid_to": add_days(nowdate(), end),
				"reason": "On leave",
			}
		).insert()

	def test_without_a_delegation_nobody_else_can_decide(self):
		_task, doc = self.submitted()
		act_as(self.tech)
		with self.assertRaises(frappe.PermissionError):
			engine.accept_handover(doc.name, **CONFIRM)
		with self.assertRaises(frappe.PermissionError):
			engine.reject_handover(doc.name, rejection_reason="Missing Information", details="x")

	def test_delegate_accepts_and_it_is_recorded_as_on_behalf(self):
		task, doc = self.submitted()
		self.delegate(self.tech)
		act_as(self.tech)
		self.assertIn(doc.name, [row.name for row in get_inbox()["rows"]])
		self.assertIn("accept", engine.get_allowed_actions(frappe.get_doc(HANDOVER, doc.name)))
		engine.accept_handover(doc.name, **CONFIRM)

		review = frappe.get_doc(HANDOVER_REVIEW, {"handover": doc.name, "decision": "Accepted"})
		self.assertEqual(review.reviewer_user, self.tech)
		self.assertEqual(review.acted_on_behalf_of, self.receiver)
		self.assertTrue(review.delegation)
		# responsibility goes to the receiver the handover was addressed to, not to the proxy
		self.assertEqual(get_current_owner(task.name), self.receiver)
		self.assertEqual(frappe.db.get_value(HANDOVER, doc.name, "decided_by"), self.tech)

	def test_expired_future_and_revoked_delegations_do_not_count(self):
		_task, doc = self.submitted()
		act_as("Administrator")
		future = self.delegate(self.tech, start=2, end=6)
		act_as(self.tech)
		with self.assertRaises(frappe.PermissionError):
			engine.accept_handover(doc.name, **CONFIRM)

		act_as(self.receiver)
		future.reload()
		future.is_revoked = 1
		future.save()
		self.assertEqual(future.status, "Revoked")
		live = self.delegate(self.tech)
		live.is_revoked = 1
		live.save()
		act_as(self.tech)
		with self.assertRaises(frappe.PermissionError):
			engine.accept_handover(doc.name, **CONFIRM)

		# ended yesterday, whatever the record says
		active = self.delegate(self.tech)
		frappe.db.set_value(DELEGATION, active.name, "valid_to", add_days(nowdate(), -1))
		frappe.local.nds_scope_cache = {}
		act_as(self.tech)
		with self.assertRaises(frappe.PermissionError):
			engine.accept_handover(doc.name, **CONFIRM)

	def test_the_sender_can_never_decide_his_own_handover(self):
		_task, doc = self.submitted()
		self.delegate(self.sender)  # allowed to exist, useless for this handover
		act_as(self.sender)
		with self.assertRaises(frappe.PermissionError):
			engine.accept_handover(doc.name, **CONFIRM)

	def test_a_delegation_only_covers_the_delegators_handovers(self):
		_task, doc = self.submitted()
		self.delegate(self.stranger)
		act_as(self.stranger)
		engine.start_review(doc.name)  # allowed: it is addressed to the delegator
		act_as(self.tech)  # a different user with no delegation
		with self.assertRaises(frappe.PermissionError):
			engine.start_review(doc.name)

	def test_rules_for_creating_and_changing_delegations(self):
		act_as(self.receiver)
		with self.assertRaises(frappe.ValidationError):
			self.delegate(self.receiver)  # to himself
		with self.assertRaises(frappe.ValidationError):
			self.delegate(self.tech, start=-9, end=-2)  # already over
		with self.assertRaises(frappe.PermissionError):
			self.delegate(self.tech, by=self.stranger)  # nobody delegates someone else's handovers

		record = self.delegate(self.tech)
		record.valid_to = add_days(nowdate(), 60)
		with self.assertRaises(frappe.PermissionError):
			record.save()
		record.reload()
		with self.assertRaises(frappe.PermissionError):
			record.delete()
		record.is_revoked = 1
		record.save()
		record.reload()
		record.is_revoked = 0
		with self.assertRaises(frappe.PermissionError):
			record.save()

	def test_only_the_parties_see_the_delegation(self):
		record = self.delegate(self.tech)

		def visible(user):
			act_as(user)
			try:
				return record.name in frappe.get_list(DELEGATION, pluck="name", limit_page_length=0)
			except frappe.PermissionError:
				return False  # no role on the DocType at all

		self.assertTrue(visible(self.receiver))
		self.assertTrue(visible(self.tech))
		self.assertFalse(visible(self.stranger))
