import frappe

from nds_operations.constants import (
	HANDOVER,
	HANDOVER_HISTORY,
	HANDOVER_REVIEW,
	OWNERSHIP_HISTORY,
)
from nds_operations.services import handover as engine
from nds_operations.tests.utils import NDSTestCase, act_as

CONFIRM = {
	"confirmed_details_reviewed": 1,
	"confirmed_attachments_received": 1,
	"confirmed_responsibilities_understood": 1,
}


def visible_to(user, task):
	"""Handovers of this test's task the user can list (other data on the site is irrelevant)."""
	act_as(user)
	return set(frappe.get_list(HANDOVER, filters={"task": task}, pluck="name", limit_page_length=0))


class TestHandoverSecurity(NDSTestCase):
	def submitted(self):
		task = self.new_task()
		doc = self.draft(task)
		act_as(self.sender)
		engine.submit_handover(doc.name)
		return task, doc

	def test_scenario_8_only_the_receiver_decides(self):
		_, doc = self.submitted()
		for user in (self.sender, self.stranger, self.tech):
			act_as(user)
			with self.assertRaises(frappe.PermissionError):
				engine.accept_handover(doc.name, **CONFIRM)
			with self.assertRaises(frappe.PermissionError):
				engine.reject_handover(doc.name, rejection_reason="Other", details="x")
			with self.assertRaises(frappe.PermissionError):
				engine.start_review(doc.name)
		self.assertEqual(frappe.db.get_value(HANDOVER, doc.name, "handover_status"), "Pending Acceptance")
		self.assertEqual(frappe.db.count(HANDOVER_REVIEW, {"handover": doc.name}), 0)

	def test_only_the_sender_submits_withdraws_or_revises(self):
		task = self.new_task()
		doc = self.draft(task)
		act_as(self.receiver)
		with self.assertRaises(frappe.PermissionError):
			engine.submit_handover(doc.name)
		act_as(self.sender)
		engine.submit_handover(doc.name)
		act_as(self.receiver)
		with self.assertRaises(frappe.PermissionError):
			engine.withdraw_handover(doc.name, "no")
		engine.reject_handover(doc.name, rejection_reason="Other", details="not mine")
		act_as(self.stranger)
		with self.assertRaises(frappe.PermissionError):
			engine.revise_handover(doc.name)

	def test_scenario_8_submitted_records_are_immutable_even_for_administrator(self):
		_, doc = self.submitted()
		act_as("Administrator")
		row = frappe.get_doc(HANDOVER, doc.name)
		row.work_done = "rewritten history"
		with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
			row.save(ignore_permissions=True)
		with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
			frappe.delete_doc(HANDOVER, doc.name, force=True, ignore_permissions=True)
		with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
			frappe.get_doc(HANDOVER, doc.name).cancel()
		self.assertEqual(frappe.db.get_value(HANDOVER, doc.name, "work_done"), "Diagnosed the print format issue.")

	def test_history_reviews_and_ledger_are_append_only(self):
		task, doc = self.submitted()
		act_as(self.receiver)
		engine.accept_handover(doc.name, **CONFIRM)
		act_as("Administrator")
		for doctype, filters in (
			(HANDOVER_HISTORY, {"handover": doc.name}),
			(HANDOVER_REVIEW, {"handover": doc.name}),
			(OWNERSHIP_HISTORY, {"task": task.name}),
		):
			name = frappe.get_all(doctype, filters=filters, pluck="name", limit=1)[0]
			row = frappe.get_doc(doctype, name)
			row.reload()
			with self.assertRaises(frappe.PermissionError):
				row.save(ignore_permissions=True)
			with self.assertRaises(frappe.PermissionError):
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)

	def test_row_scoping_in_lists_and_single_documents(self):
		task = self.new_task()
		draft = self.draft(task)
		self.assertEqual(visible_to(self.sender, task.name), {draft.name})
		self.assertEqual(visible_to(self.receiver, task.name), set())  # drafts are private to the sender
		self.assertEqual(visible_to(self.auditor, task.name), set())

		act_as(self.sender)
		engine.submit_handover(draft.name)
		self.assertEqual(visible_to(self.sender, task.name), {draft.name})
		self.assertEqual(visible_to(self.receiver, task.name), {draft.name})
		self.assertEqual(visible_to(self.auditor, task.name), {draft.name})  # read-only auditor: every submitted one
		self.assertEqual(visible_to(self.ops, task.name), {draft.name})
		self.assertEqual(visible_to(self.stranger, task.name), set())
		self.assertEqual(visible_to(self.tech, task.name), set())

		act_as(self.stranger)
		self.assertFalse(frappe.has_permission(HANDOVER, "read", doc=draft.name))
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc(HANDOVER, draft.name).check_permission("read")
		act_as(self.receiver)
		self.assertTrue(frappe.has_permission(HANDOVER, "read", doc=draft.name))
		self.assertFalse(frappe.has_permission(HANDOVER, "write", doc=draft.name))

	def test_identity_and_engine_fields_cannot_be_forged(self):
		task = self.new_task()
		act_as(self.sender)
		doc = frappe.get_doc(
			{
				"doctype": HANDOVER,
				"task": task.name,
				"receiver_employee": self.receiver_employee,
				"handover_reason": "Reassignment",
				"work_done": "x",
				"sender_user": self.stranger,
				"sender_name": "Somebody Else",
				"handover_status": "Accepted",
				"snapshot_hash": "forged",
				"new_owner": self.stranger,
				"version_no": 9,
			}
		).insert()
		self.assertEqual(doc.sender_user, self.sender)
		self.assertEqual(doc.sender_employee, self.sender_employee)
		self.assertEqual(doc.sender_name, "Sara Sender")
		self.assertEqual((doc.handover_status, doc.version_no), ("Draft", 1))
		self.assertFalse(doc.snapshot_hash or doc.new_owner)

		doc.handover_status = "Accepted"
		doc.save()
		self.assertEqual(frappe.db.get_value(HANDOVER, doc.name, "handover_status"), "Draft")

	def test_standard_form_submit_works_for_the_sender(self):
		task = self.new_task()
		doc = self.draft(task)
		act_as(self.sender)
		row = frappe.get_doc(HANDOVER, doc.name)
		row.submit()
		self.assertEqual(frappe.db.get_value(HANDOVER, doc.name, "handover_status"), "Pending Acceptance")

	def test_handover_rules(self):
		task = self.new_task()
		# not the owner
		act_as(self.stranger)
		with self.assertRaises(frappe.PermissionError):
			engine.create_handover(task.name, self.receiver_employee, {"handover_reason": "Other"})
		# no sender role
		act_as(self.auditor)
		with self.assertRaises(frappe.PermissionError):
			engine.create_handover(task.name, self.receiver_employee, {"handover_reason": "Other"})
		# to yourself
		act_as(self.sender)
		with self.assertRaises(frappe.ValidationError):
			engine.create_handover(task.name, self.sender_employee, {"handover_reason": "Other"})
		# ops managers may hand over any task
		act_as("Administrator")
		frappe.get_doc("User", self.ops).add_roles("NDS Task Sender")
		act_as(self.ops)
		doc = engine.create_handover(
			task.name, self.receiver_employee, {"handover_reason": "Escalation", "work_done": "x"}
		)
		self.assertEqual(doc.sender_user, self.ops)

	def test_scenario_6_private_attachments_follow_the_handover(self):
		task = self.new_task()
		act_as(self.sender)
		doc = engine.create_handover(
			task.name,
			self.receiver_employee,
			{"handover_reason": "Reassignment", "work_done": "Done."},
			attachments=[{"attachment_type": "Document", "title": "Staging", "url": "https://example.com/s"}],
		)
		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "evidence.txt",
				"content": "before and after",
				"is_private": 1,
				"attached_to_doctype": HANDOVER,
				"attached_to_name": doc.name,
			}
		).insert()
		engine.submit_handover(doc.name)

		def can_read_file(user):
			act_as(user)
			return frappe.has_permission("File", "read", doc=file.name)

		self.assertTrue(can_read_file(self.sender))
		self.assertTrue(can_read_file(self.receiver))
		self.assertFalse(can_read_file(self.stranger))
