import frappe

from nds_operations.api.operations import get_dashboard
from nds_operations.services import handover as engine
from nds_operations.tests.utils import NDSTestCase, act_as


class TestOperationsDashboard(NDSTestCase):
	def test_dashboard_is_scoped_to_visible_handovers(self):
		task = self.new_task()
		act_as(self.sender)
		doc = engine.create_handover(
			task.name, self.receiver_employee,
			{"handover_reason": "Reassignment", "work_done": "Prepared handover."},
		)
		engine.submit_handover(doc.name)

		act_as(self.receiver)
		data = get_dashboard()
		self.assertEqual(data["scope"], "permission_scoped")
		self.assertEqual(data["kpis"]["total_submitted"], 1)
		self.assertEqual(len(data["recent"]), 1)

		act_as(self.stranger)
		data = get_dashboard()
		self.assertEqual(data["kpis"]["total_submitted"], 0)
		self.assertEqual(data["recent"], [])

	def test_dashboard_rejects_users_without_nds_roles(self):
		act_as("Guest")
		with self.assertRaises(frappe.PermissionError):
			get_dashboard()
