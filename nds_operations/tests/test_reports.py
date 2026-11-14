import frappe
from frappe.utils import add_to_date, now_datetime

from nds_operations.constants import HANDOVER
from nds_operations.nds_enterprise_operations.report.handover_acceptance_report import (
	handover_acceptance_report as acceptance,
)
from nds_operations.nds_enterprise_operations.report.handover_aging_report import (
	handover_aging_report as aging,
)
from nds_operations.nds_enterprise_operations.report.handover_rejection_report import (
	handover_rejection_report as rejection,
)
from nds_operations.nds_enterprise_operations.report.task_handover_register import (
	task_handover_register as register,
)
from nds_operations.services import handover as engine
from nds_operations.tests.utils import NDSTestCase, act_as


class TestHandoverReports(NDSTestCase):
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
		return doc

	def names(self, module, user, filters=None):
		act_as(user)
		return {row.name for row in module.execute(filters or {})[1]}

	def test_register_is_row_scoped_and_filterable(self):
		doc = self.submitted()
		self.assertIn(doc.name, self.names(register, self.sender))
		self.assertIn(doc.name, self.names(register, self.receiver))
		self.assertNotIn(doc.name, self.names(register, self.stranger))
		self.assertIn(
			doc.name, self.names(register, self.receiver, {"handover_status": "Pending Acceptance"})
		)
		self.assertNotIn(doc.name, self.names(register, self.receiver, {"handover_status": "Accepted"}))
		self.assertIn(doc.name, self.names(register, self.receiver, {"employee": self.sender_employee}))
		tomorrow = add_to_date(now_datetime(), days=1).date().isoformat()
		self.assertNotIn(doc.name, self.names(register, self.receiver, {"from_date": tomorrow}))

	def test_acceptance_report_first_pass_and_hours(self):
		doc = self.submitted()
		act_as(self.receiver)
		engine.accept_handover(
			doc.name,
			confirmed_details_reviewed=1,
			confirmed_attachments_received=1,
			confirmed_responsibilities_understood=1,
		)
		_columns, rows, _msg, _chart, summary = acceptance.execute({})
		row = next(r for r in rows if r.name == doc.name)
		self.assertEqual(row.first_pass, 1)
		self.assertIsNotNone(row.hours_to_accept)
		self.assertTrue(any(s["label"].startswith("First-pass") for s in summary))

	def test_clarification_round_is_not_first_pass(self):
		doc = self.submitted()
		act_as(self.receiver)
		engine.request_clarification(doc.name, details="Which environment?")
		act_as(self.sender)
		engine.revise_handover(doc.name)  # new draft version of the same handover chain
		revised = frappe.get_all(HANDOVER, filters={"previous_handover": doc.name}, pluck="name")[0]
		engine.submit_handover(revised)
		act_as(self.receiver)
		engine.accept_handover(
			revised,
			confirmed_details_reviewed=1,
			confirmed_attachments_received=1,
			confirmed_responsibilities_understood=1,
		)
		row = next(r for r in acceptance.execute({})[1] if r.name == revised)
		self.assertEqual(row.first_pass, 0)  # version 2

	def test_rejection_report_lists_reason_and_details(self):
		doc = self.submitted()
		act_as(self.receiver)
		engine.reject_handover(doc.name, rejection_reason="Missing Information", details="No logs attached.")
		_columns, rows, _msg, chart, _summary = rejection.execute({})
		row = next(r for r in rows if r.name == doc.name)
		self.assertEqual(row.rejection_reason, "Missing Information")
		self.assertIn("No logs attached.", row.details)
		self.assertIn("Missing Information", chart["data"]["labels"])

	def test_aging_report_flags_only_receiver_delays(self):
		doc = self.submitted()
		frappe.db.set_value(
			HANDOVER, doc.name, "response_due", add_to_date(now_datetime(), hours=-2), update_modified=False
		)
		act_as(self.receiver)
		row = next(r for r in aging.execute({})[1] if r.name == doc.name)
		self.assertEqual(row.overdue, 1)
		engine.request_clarification(doc.name, details="Need the logs.")
		row = next(r for r in aging.execute({})[1] if r.name == doc.name)
		self.assertEqual(row.overdue, 0)  # now waiting for the sender
		self.assertIn(row.age_bucket, ("0-1 day", "1-3 days"))
