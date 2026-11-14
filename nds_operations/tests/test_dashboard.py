import frappe
from frappe.utils import add_to_date, now_datetime

from nds_operations.api.operations import get_dashboard
from nds_operations.constants import HANDOVER
from nds_operations.services import handover as engine
from nds_operations.tests.utils import NDSTestCase, act_as


class TestOperationsDashboard(NDSTestCase):
	"""The site may hold other handovers, so every assertion is a difference against a baseline."""

	def submit_one(self):
		act_as("Administrator")
		task = self.new_task()
		act_as(self.sender)
		doc = engine.create_handover(
			task.name,
			self.receiver_employee,
			{"handover_reason": "Reassignment", "work_done": "Prepared handover."},
		)
		engine.submit_handover(doc.name)
		return doc

	def kpis(self, user):
		act_as(user)
		return get_dashboard()

	def test_dashboard_is_scoped_to_visible_handovers(self):
		before_receiver = self.kpis(self.receiver)["kpis"]["total_submitted"]
		before_stranger = self.kpis(self.stranger)
		doc = self.submit_one()

		data = self.kpis(self.receiver)
		self.assertEqual(data["scope"], "permission_scoped")
		self.assertEqual(data["kpis"]["total_submitted"], before_receiver + 1)
		self.assertIn(doc.name, [row.name for row in data["recent"]])

		after_stranger = self.kpis(self.stranger)
		self.assertEqual(
			after_stranger["kpis"]["total_submitted"], before_stranger["kpis"]["total_submitted"]
		)
		self.assertNotIn(doc.name, [row.name for row in after_stranger["recent"]])

	def test_status_counts_and_rates_follow_the_decisions(self):
		doc = self.submit_one()
		before = self.kpis(self.receiver)["kpis"]
		act_as(self.receiver)
		engine.reject_handover(doc.name, rejection_reason="Missing Information", details="Not enough.")
		after = self.kpis(self.receiver)
		self.assertEqual(after["kpis"]["rejected"], before["rejected"] + 1)
		self.assertEqual(after["kpis"]["pending_acceptance"], before["pending_acceptance"] - 1)
		self.assertEqual(after["status_counts"]["Rejected"], after["kpis"]["rejected"])
		self.assertIsNotNone(after["kpis"]["decision_acceptance_rate"])

	def test_overdue_counts_only_what_the_receiver_still_owes(self):
		doc = self.submit_one()
		before = self.kpis(self.receiver)["kpis"]["overdue"]
		frappe.db.set_value(
			HANDOVER, doc.name, "response_due", add_to_date(now_datetime(), hours=-1), update_modified=False
		)
		self.assertEqual(self.kpis(self.receiver)["kpis"]["overdue"], before + 1)

		# a clarification request moves the wait to the sender, so it is no longer an overdue response
		act_as(self.receiver)
		engine.request_clarification(doc.name, details="Which environment?")
		self.assertEqual(self.kpis(self.receiver)["kpis"]["overdue"], before)

	def test_dashboard_rejects_users_without_nds_roles(self):
		act_as("Guest")
		with self.assertRaises(frappe.PermissionError):
			get_dashboard()

	def test_task_counts_follow_task_permissions(self):
		act_as("Administrator")
		before = get_dashboard()["tasks"]
		task = self.new_task()
		frappe.db.set_value("Task", task.name, "exp_end_date", add_to_date(now_datetime(), days=-3))
		after = get_dashboard()["tasks"]
		self.assertEqual(after["open"], before["open"] + 1)
		self.assertEqual(after["overdue"], before["overdue"] + 1)
		frappe.db.set_value("Task", task.name, "status", "Completed")
		done = get_dashboard()["tasks"]
		self.assertEqual(done["overdue"], before["overdue"])
		self.assertEqual(done["completed"], before["completed"] + 1)
