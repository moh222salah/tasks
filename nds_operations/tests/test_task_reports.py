import frappe
from frappe.utils import add_days, nowdate

from nds_operations.nds_enterprise_operations.report.employee_workload_report import (
	employee_workload_report as workload,
)
from nds_operations.nds_enterprise_operations.report.overdue_tasks_report import (
	overdue_tasks_report as overdue,
)
from nds_operations.nds_enterprise_operations.report.tasks_master_report import (
	tasks_master_report as master,
)
from nds_operations.services import handover as engine
from nds_operations.tests.utils import NDSTestCase, act_as


class TestTaskReports(NDSTestCase):
	def late_task(self, days=3):
		act_as("Administrator")
		task = self.new_task()
		frappe.db.set_value("Task", task.name, "exp_end_date", add_days(nowdate(), -days))
		return task

	def hand_over(self, task):
		act_as(self.sender)
		doc = engine.create_handover(
			task.name,
			self.receiver_employee,
			{"handover_reason": "Reassignment", "work_done": "Done so far."},
		)
		engine.submit_handover(doc.name)
		return doc

	def row(self, module, task, **filters):
		act_as("Administrator")
		rows = module.execute(filters)[1]
		return next((r for r in rows if r.name == task.name), None)

	def test_master_shows_owner_overdue_and_open_handover(self):
		task = self.late_task(4)
		row = self.row(master, task)
		self.assertEqual(row.current_owner, self.sender)
		self.assertEqual(row.days_overdue, 4)
		self.assertFalse(row.open_handover)

		doc = self.hand_over(task)
		row = self.row(master, task)
		self.assertEqual(row.open_handover, doc.name)
		self.assertEqual(row.handover_status, "Pending Acceptance")
		self.assertEqual(row.current_owner, self.sender)  # nothing moves before acceptance

	def test_owner_follows_the_ledger_after_acceptance(self):
		task = self.late_task()
		doc = self.hand_over(task)
		act_as(self.receiver)
		engine.accept_handover(
			doc.name,
			confirmed_details_reviewed=1,
			confirmed_attachments_received=1,
			confirmed_responsibilities_understood=1,
		)
		row = self.row(master, task)
		self.assertEqual(row.current_owner, self.receiver)
		self.assertFalse(row.open_handover)
		self.assertEqual(self.row(master, task, owner=self.receiver).name, task.name)
		self.assertIsNone(self.row(master, task, owner=self.sender))

	def test_overdue_report_gives_a_visible_reason_only(self):
		task = self.late_task(5)
		self.assertEqual(self.row(overdue, task).reason, "")  # nothing in the data explains it
		doc = self.hand_over(task)
		row = self.row(overdue, task)
		self.assertIn(doc.name, row.reason)
		self.assertIn("Pending Acceptance", row.reason)

		act_as("Administrator")
		frappe.db.set_value("Task", task.name, "status", "Completed")
		self.assertIsNone(self.row(overdue, task))  # closed tasks are never overdue

	def test_workload_counts_tasks_and_awaiting_decisions(self):
		def mine(user):
			act_as("Administrator")
			return next((r for r in workload.execute({})[1] if r.user == user), frappe._dict())

		before_sender = mine(self.sender).get("open_tasks", 0)
		before_receiver = mine(self.receiver).get("awaiting_my_decision", 0)
		task = self.late_task()
		self.hand_over(task)
		self.assertEqual(mine(self.sender).open_tasks, before_sender + 1)
		self.assertEqual(mine(self.receiver).awaiting_my_decision, before_receiver + 1)
		self.assertGreaterEqual(mine(self.sender).overdue, 1)
