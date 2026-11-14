import frappe
from frappe.utils import add_days, nowdate

from nds_operations.nds_enterprise_operations.report.department_performance_report import (
	department_performance_report as department_report,
)
from nds_operations.nds_enterprise_operations.report.employee_productivity_report import (
	employee_productivity_report as productivity,
)
from nds_operations.nds_enterprise_operations.report.rework_and_revision_report import (
	rework_and_revision_report as rework,
)
from nds_operations.nds_enterprise_operations.report.task_cycle_time_report import (
	task_cycle_time_report as cycle_time,
)
from nds_operations.nds_enterprise_operations.report.team_performance_report import (
	team_performance_report as team_report,
)
from nds_operations.services import handover as engine
from nds_operations.services.kpi import completed_tasks, get_handovers, handover_group_stats, on_time_rate
from nds_operations.tests.utils import NDSTestCase, act_as

CONFIRM = {
	"confirmed_details_reviewed": 1,
	"confirmed_attachments_received": 1,
	"confirmed_responsibilities_understood": 1,
}


class TestKPI(NDSTestCase):
	def send(self, task=None):
		act_as("Administrator")
		task = task or self.new_task()
		act_as(self.sender)
		doc = engine.create_handover(
			task.name,
			self.receiver_employee,
			{"handover_reason": "Reassignment", "work_done": "Done so far."},
		)
		engine.submit_handover(doc.name)
		return task, doc

	def accept(self, name):
		act_as(self.receiver)
		engine.accept_handover(name, **CONFIRM)

	def reject(self, name):
		act_as(self.receiver)
		engine.reject_handover(name, rejection_reason="Missing Information", details="Not enough.")

	def stats(self, names):
		act_as("Administrator")
		rows = get_handovers({"name": ("in", names)})
		return handover_group_stats(rows, "sender_user", "receiver_user")

	def test_first_pass_rejection_and_quality_score(self):
		_t1, ok = self.send()
		self.accept(ok.name)
		_t2, bad = self.send()
		self.reject(bad.name)
		stats = self.stats([ok.name, bad.name])
		sender, receiver = stats[self.sender], stats[self.receiver]
		self.assertEqual((sender.sent, sender.decided, sender.first_pass), (2, 2, 1))
		self.assertEqual(sender.first_pass_rate, 50.0)
		self.assertEqual(sender.rejection_rate, 50.0)
		self.assertEqual(sender.rework_rate, 0.0)
		self.assertEqual(sender.quality_score, 65.0)  # 0.5*50 + 0.3*100 + 0.2*50
		self.assertEqual(receiver.received_decided, 2)
		self.assertIsNotNone(receiver.avg_response_hours)

	def test_a_revision_is_rework_and_never_first_pass(self):
		_task, first = self.send()
		self.reject(first.name)
		act_as(self.sender)
		revised = engine.revise_handover(first.name)
		engine.submit_handover(revised.name)
		self.accept(revised.name)
		sender = self.stats([first.name, revised.name])[self.sender]
		self.assertEqual(sender.revisions, 1)
		self.assertEqual(sender.rework_rate, 50.0)
		self.assertEqual(sender.first_pass_rate, 0.0)  # accepted, but on version 2

	def test_rates_without_a_denominator_are_empty_not_zero(self):
		_task, pending = self.send()
		sender = self.stats([pending.name])[self.sender]
		self.assertIsNone(sender.first_pass_rate)
		self.assertIsNone(sender.quality_score)
		self.assertEqual(sender.sent, 1)

	def finish(self, task, due_offset, done_offset):
		act_as("Administrator")
		frappe.db.set_value(
			"Task",
			task.name,
			{
				"status": "Completed",
				"exp_end_date": add_days(nowdate(), due_offset),
				"completed_on": add_days(nowdate(), done_offset),
			},
		)
		return task

	def test_on_time_late_and_excused(self):
		act_as("Administrator")
		on_time = self.finish(self.new_task(), due_offset=-1, done_offset=-2)
		late = self.finish(self.new_task(), due_offset=-5, done_offset=-1)
		waiting, doc = self.send()  # the handover is still pending on the due date
		frappe.db.set_value(
			"NDS Task Handover", doc.name, "submitted_at", add_days(nowdate(), -4), update_modified=False
		)
		self.finish(waiting, due_offset=-1, done_offset=0)
		act_as("Administrator")
		tasks = {
			t.name: t for t in completed_tasks({"name": ("in", [on_time.name, late.name, waiting.name])})
		}
		self.assertTrue(tasks[on_time.name].on_time)
		self.assertTrue(tasks[late.name].late and not tasks[late.name].excused)
		self.assertTrue(tasks[waiting.name].late and tasks[waiting.name].excused)
		# the excused task is left out of the denominator: 1 on time out of 2 scored
		self.assertEqual(on_time_rate(list(tasks.values())), 50.0)
		self.assertIsNone(on_time_rate([tasks[waiting.name]]))

	def test_cancelled_tasks_never_count(self):
		act_as("Administrator")
		task = self.new_task()
		frappe.db.set_value("Task", task.name, {"status": "Cancelled", "completed_on": nowdate()})
		self.assertNotIn(task.name, {t.name for t in completed_tasks()})

	def test_reports_run_and_describe_their_method(self):
		_task, first = self.send()
		self.reject(first.name)
		act_as(self.sender)
		revised = engine.revise_handover(first.name)
		engine.submit_handover(revised.name)
		act_as("Administrator")
		done = self.finish(self.new_task(), due_offset=1, done_offset=0)

		for module in (productivity, department_report, team_report, cycle_time, rework):
			result = module.execute({})
			self.assertGreaterEqual(len(result[0]), 5, module.__name__)
			self.assertIn("How the numbers are calculated", result[2])

		rows = rework.execute({})[1]
		row = next(r for r in rows if r.root == first.name)
		self.assertEqual((row.versions, row.rejections), (2, 1))
		self.assertIn(done.name, {r.name for r in cycle_time.execute({})[1]})
		users = {r.user for r in productivity.execute({})[1]}
		self.assertIn(self.sender, users)
