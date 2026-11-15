import frappe
from frappe.utils import add_days, today

from nds_operations.services import kpi_snapshot
from nds_operations.tests.utils import NDSTestCase, act_as


class TestKPISnapshot(NDSTestCase):
	def finished_task(self):
		act_as("Administrator")
		start, end = kpi_snapshot.previous_month()
		task = self.new_task()
		frappe.db.set_value(
			"Task",
			task.name,
			{"status": "Completed", "completed_on": add_days(start, 3), "exp_end_date": add_days(start, 5)},
		)
		return task, start, end

	def test_snapshot_is_created_once_and_frozen(self):
		task, start, end = self.finished_task()
		created = kpi_snapshot.generate(start, end)
		self.assertTrue(created)
		row = frappe.get_doc("NDS Department KPI", {"department": self.marketing, "period_start": start})
		self.assertEqual(row.completed_tasks, 1)
		self.assertEqual(row.on_time_rate, 100.0)
		self.assertFalse(kpi_snapshot.generate(start, end))  # second run creates nothing
		frappe.db.set_value("Task", task.name, "status", "Open")
		row.reload()
		self.assertEqual(row.completed_tasks, 1)  # later changes do not rewrite history
		row.completed_tasks = 9
		with self.assertRaises(frappe.PermissionError):
			row.save()
		with self.assertRaises(frappe.PermissionError):
			frappe.delete_doc("NDS Department KPI", row.name, force=True)

	def test_open_period_cannot_be_frozen(self):
		act_as("Administrator")
		with self.assertRaises(frappe.ValidationError):
			kpi_snapshot.generate(add_days(today(), -3), today())

	def test_only_management_can_freeze(self):
		_task, start, end = self.finished_task()
		act_as(self.sender)
		with self.assertRaises(frappe.PermissionError):
			kpi_snapshot.freeze_period(start, end)
