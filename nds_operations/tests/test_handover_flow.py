import frappe

from nds_operations.constants import HANDOVER, HANDOVER_HISTORY, HANDOVER_REVIEW, OWNERSHIP_HISTORY
from nds_operations.services import handover as engine
from nds_operations.services.ownership import get_current_owner
from nds_operations.services.snapshot import verify_snapshot
from nds_operations.tests.utils import NDSTestCase, act_as

CONFIRM = {
	"confirmed_details_reviewed": 1,
	"confirmed_attachments_received": 1,
	"confirmed_responsibilities_understood": 1,
}


def open_todo_users(task):
	return frappe.get_all(
		"ToDo", filters={"reference_type": "Task", "reference_name": task, "status": "Open"}, pluck="allocated_to"
	)


def events(handover):
	return [
		row.event_type
		for row in frappe.get_all(
			HANDOVER_HISTORY,
			filters={"handover": handover},
			fields=["event_type"],
			order_by="event_time asc, creation asc",
		)
	]


def ledger(task):
	return [
		(row.sequence, row.event_type, row.from_user, row.to_user)
		for row in frappe.get_all(
			OWNERSHIP_HISTORY,
			filters={"task": task},
			fields=["sequence", "event_type", "from_user", "to_user"],
			order_by="sequence asc",
		)
	]


class TestHandoverFlow(NDSTestCase):
	def send(self, doc, request_id=None):
		act_as(self.sender)
		return engine.submit_handover(doc.name, request_id)

	def test_scenario_1_accept_moves_responsibility_only_after_acceptance(self):
		task = self.new_task()
		doc = self.draft(task)
		self.assertEqual(doc.handover_status, "Draft")

		result = self.send(doc)
		self.assertEqual(result["handover_status"], "Pending Acceptance")
		self.assertTrue(
			frappe.db.exists(
				"Notification Log", {"for_user": self.receiver, "document_type": HANDOVER, "document_name": doc.name}
			)
		)

		# submitted is not accepted: the task is still the sender's
		self.assertEqual(get_current_owner(task.name), self.sender)
		self.assertEqual(open_todo_users(task.name), [self.sender])
		self.assertEqual(ledger(task.name), [])

		act_as(self.receiver)
		self.assertEqual(engine.start_review(doc.name)["handover_status"], "Under Review")
		self.assertEqual(engine.accept_handover(doc.name, **CONFIRM, request_id="acc-1")["handover_status"], "Accepted")

		self.assertEqual(get_current_owner(task.name), self.receiver)
		self.assertEqual(open_todo_users(task.name), [self.receiver])
		self.assertEqual(
			ledger(task.name),
			[(1, "Initial Assignment", None, self.sender), (2, "Handover Accepted", self.sender, self.receiver)],
		)
		self.assertEqual(
			events(doc.name),
			["Created", "Marked Ready", "Submitted", "Received", "Accepted", "Responsibility Transferred"],
		)
		row = frappe.get_doc(HANDOVER, doc.name)
		self.assertEqual((row.previous_owner, row.new_owner), (self.sender, self.receiver))
		self.assertTrue(row.responsibility_transferred_at)

	def test_accept_needs_the_three_confirmations(self):
		doc = self.draft(self.new_task())
		self.send(doc)
		act_as(self.receiver)
		with self.assertRaises(frappe.ValidationError):
			engine.accept_handover(doc.name, confirmed_details_reviewed=1)
		self.assertEqual(frappe.db.get_value(HANDOVER, doc.name, "handover_status"), "Pending Acceptance")

	def test_scenario_2_reject_keeps_responsibility_and_revision_continues(self):
		task = self.new_task()
		doc = self.draft(task)
		self.send(doc)

		act_as(self.receiver)
		with self.assertRaises(frappe.ValidationError):  # reason and details are mandatory
			engine.reject_handover(doc.name, rejection_reason="", details="x")
		with self.assertRaises(frappe.ValidationError):
			engine.reject_handover(doc.name, rejection_reason="Missing Attachments", details=" ")
		out = engine.reject_handover(
			doc.name, rejection_reason="Missing Attachments", details="No screenshots", request_id="rej-1"
		)
		self.assertEqual(out["handover_status"], "Rejected")
		self.assertEqual(get_current_owner(task.name), self.sender)
		self.assertEqual(ledger(task.name), [])

		# a retry of the same request is replayed, not recorded twice
		self.assertTrue(
			engine.reject_handover(
				doc.name, rejection_reason="Missing Attachments", details="No screenshots", request_id="rej-1"
			)["replayed"]
		)
		self.assertEqual(frappe.db.count(HANDOVER_REVIEW, {"handover": doc.name}), 1)

		act_as(self.sender)
		revision = engine.revise_handover(doc.name, "rv-1")
		self.assertEqual(
			(revision.version_no, revision.handover_type, revision.previous_handover, revision.root_handover),
			(2, "Revision", doc.name, doc.name),
		)
		self.assertEqual(frappe.db.get_value(HANDOVER, doc.name, "superseded_by"), revision.name)
		self.assertEqual(engine.revise_handover(doc.name, "rv-1").name, revision.name)
		with self.assertRaises(frappe.ValidationError):
			engine.revise_handover(doc.name, "rv-other")

		engine.submit_handover(revision.name)
		act_as(self.receiver)
		engine.accept_handover(revision.name, **CONFIRM)
		self.assertEqual(get_current_owner(task.name), self.receiver)
		self.assertEqual(frappe.db.get_value(HANDOVER, doc.name, "handover_status"), "Rejected")  # history stays

	def test_scenario_3_clarification_then_resubmit(self):
		task = self.new_task()
		doc = self.draft(task)
		self.send(doc)

		act_as(self.receiver)
		with self.assertRaises(frappe.ValidationError):
			engine.request_clarification(doc.name, details="")
		engine.request_clarification(doc.name, details="Which server was patched?")
		self.assertEqual(get_current_owner(task.name), self.sender)

		act_as(self.sender)
		revision = engine.revise_handover(doc.name)
		engine.update_draft(revision.name, data={"clarification_response": "The staging server."})
		engine.submit_handover(revision.name)
		act_as(self.receiver)
		engine.accept_handover(revision.name, **CONFIRM)
		self.assertEqual(get_current_owner(task.name), self.receiver)
		self.assertEqual(
			frappe.db.get_value(HANDOVER, revision.name, "clarification_response"), "The staging server."
		)

	def test_scenario_4_cross_department_handover(self):
		task = self.new_task(department=self.marketing)
		doc = self.draft(task, self.tech_employee)
		self.send(doc)
		act_as(self.tech)
		engine.accept_handover(doc.name, **CONFIRM)

		self.assertEqual(frappe.db.get_value("Task", task.name, "department"), self.technology)
		row = frappe.get_doc(OWNERSHIP_HISTORY, {"task": task.name, "sequence": 2})
		self.assertEqual((row.from_department, row.to_department), (self.marketing, self.technology))
		self.assertEqual(open_todo_users(task.name), [self.tech])

	def test_scenario_5_re_handover_keeps_the_whole_chain(self):
		task = self.new_task()
		first = self.draft(task)
		self.send(first)
		act_as(self.receiver)
		engine.accept_handover(first.name, **CONFIRM)

		# the new owner hands it on to a colleague in Technology
		second = engine.create_handover(
			task.name,
			self.tech_employee,
			{"handover_reason": "Department Transfer", "work_done": "Reviewed and extended."},
		)
		self.assertEqual((second.handover_type, second.previous_handover), ("Re-handover", first.name))
		engine.submit_handover(second.name)
		act_as(self.tech)
		engine.accept_handover(second.name, **CONFIRM)

		self.assertEqual(
			ledger(task.name),
			[
				(1, "Initial Assignment", None, self.sender),
				(2, "Handover Accepted", self.sender, self.receiver),
				(3, "Handover Accepted", self.receiver, self.tech),
			],
		)
		self.assertEqual(get_current_owner(task.name), self.tech)

	def test_one_open_handover_per_task(self):
		task = self.new_task()
		doc = self.draft(task)
		self.send(doc)
		act_as(self.sender)
		with self.assertRaises(frappe.ValidationError):
			engine.create_handover(task.name, self.tech_employee, {"handover_reason": "Other"})

	def test_snapshot_is_frozen_and_detects_tampering(self):
		task = self.new_task()
		doc = self.draft(task)
		self.send(doc)
		self.assertTrue(verify_snapshot(doc.name))

		frappe.db.set_value("Task", task.name, "subject", "Renamed after handover")
		self.assertEqual(frappe.db.get_value(HANDOVER, doc.name, "task_title"), "Fix invoice print format")
		self.assertTrue(verify_snapshot(doc.name))

		frappe.db.set_value(HANDOVER, doc.name, "work_done", "tampered directly in the database")
		self.assertFalse(verify_snapshot(doc.name))

	def test_scenario_10_retry_does_not_duplicate(self):
		task = self.new_task()
		act_as(self.sender)
		values = {"handover_reason": "Reassignment", "work_done": "Done."}
		first = engine.create_handover(task.name, self.receiver_employee, values, client_request_id="c-1")
		again = engine.create_handover(task.name, self.receiver_employee, values, client_request_id="c-1")
		self.assertEqual(first.name, again.name)

		one = engine.submit_handover(first.name, "s-1")
		two = engine.submit_handover(first.name, "s-1")
		self.assertFalse(one["replayed"])
		self.assertTrue(two["replayed"])
		with self.assertRaises(frappe.ValidationError):
			engine.submit_handover(first.name, "s-2")
		self.assertEqual(events(first.name).count("Submitted"), 1)

		act_as(self.receiver)
		engine.accept_handover(first.name, **CONFIRM, request_id="a-1")
		again = engine.accept_handover(first.name, **CONFIRM, request_id="a-1")
		self.assertTrue(again["replayed"])
		with self.assertRaises(frappe.ValidationError):  # a different request on a decided handover
			engine.accept_handover(first.name, **CONFIRM, request_id="a-2")
		self.assertEqual(frappe.db.count(HANDOVER_REVIEW, {"handover": first.name}), 1)
		self.assertEqual(len(ledger(task.name)), 2)

	def test_ownership_changed_after_submit_blocks_acceptance(self):
		task = self.new_task()
		doc = self.draft(task)
		self.send(doc)
		act_as("Administrator")
		frappe.get_doc(
			{
				"doctype": OWNERSHIP_HISTORY,
				"task": task.name,
				"sequence": 1,
				"event_type": "Manual Reassignment",
				"to_user": self.stranger,
				"transferred_at": frappe.utils.now_datetime(),
			}
		).insert()

		act_as(self.receiver)
		with self.assertRaises(frappe.ValidationError):
			engine.accept_handover(doc.name, **CONFIRM)
		self.assertEqual(frappe.db.get_value(HANDOVER, doc.name, "handover_status"), "Pending Acceptance")
		self.assertEqual(frappe.db.count(HANDOVER_REVIEW, {"handover": doc.name}), 0)
		self.assertEqual(len(ledger(task.name)), 1)

	def test_withdraw_before_decision(self):
		task = self.new_task()
		doc = self.draft(task)
		self.send(doc)
		act_as(self.sender)
		with self.assertRaises(frappe.ValidationError):
			engine.withdraw_handover(doc.name, " ")
		engine.withdraw_handover(doc.name, "Wrong receiver")
		self.assertEqual(frappe.db.get_value(HANDOVER, doc.name, "handover_status"), "Withdrawn")
		act_as(self.receiver)
		with self.assertRaises(frappe.ValidationError):
			engine.accept_handover(doc.name, **CONFIRM)
		self.assertEqual(get_current_owner(task.name), self.sender)

	def test_incomplete_handover_cannot_be_submitted(self):
		task = self.new_task()
		act_as(self.sender)
		doc = engine.create_handover(task.name, self.receiver_employee, {"handover_reason": "Reassignment"})
		with self.assertRaises(frappe.ValidationError):
			engine.submit_handover(doc.name)
		self.assertEqual(frappe.db.get_value(HANDOVER, doc.name, "docstatus"), 0)
