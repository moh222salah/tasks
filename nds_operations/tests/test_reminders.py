import frappe
from frappe.utils import add_to_date, now_datetime

from nds_operations.constants import HANDOVER, HANDOVER_HISTORY, NOTIFICATION_PREFERENCE
from nds_operations.services import handover as engine
from nds_operations.services.reminders import run_handover_reminders, run_task_reminders
from nds_operations.tests.utils import NDSTestCase, act_as


def logs(user, doc_name):
	return frappe.get_all(
		"Notification Log",
		filters={"for_user": user, "document_type": HANDOVER, "document_name": doc_name},
		pluck="subject",
	)


class TestReminders(NDSTestCase):
	def submitted(self, due_in_hours):
		act_as("Administrator")
		task = self.new_task()
		act_as(self.sender)
		doc = engine.create_handover(
			task.name,
			self.receiver_employee,
			{"handover_reason": "Reassignment", "work_done": "Done so far."},
		)
		engine.submit_handover(doc.name)
		frappe.db.set_value(
			HANDOVER,
			doc.name,
			"response_due",
			add_to_date(now_datetime(), hours=due_in_hours),
			update_modified=False,
		)
		act_as("Administrator")
		return task, doc

	def events(self, name):
		return frappe.get_all(HANDOVER_HISTORY, filters={"handover": name}, pluck="event_type")

	def test_due_soon_is_sent_once_to_the_receiver(self):
		_task, doc = self.submitted(due_in_hours=2)
		first = run_handover_reminders()
		self.assertGreaterEqual(first["due_soon"], 1)
		self.assertTrue(any("must be answered" in s for s in logs(self.receiver, doc.name)))
		self.assertEqual(self.events(doc.name).count("Reminder Sent"), 1)
		run_handover_reminders()
		self.assertEqual(self.events(doc.name).count("Reminder Sent"), 1)  # never twice

	def test_far_from_due_sends_nothing(self):
		_task, doc = self.submitted(due_in_hours=30)
		run_handover_reminders()
		self.assertNotIn("Reminder Sent", self.events(doc.name))
		self.assertNotIn("Overdue Alert", self.events(doc.name))

	def test_overdue_alerts_both_parties_and_escalates_later(self):
		_task, doc = self.submitted(due_in_hours=-1)
		run_handover_reminders()
		self.assertIn("Overdue Alert", self.events(doc.name))
		self.assertNotIn("Escalated", self.events(doc.name))
		self.assertTrue(logs(self.sender, doc.name) and logs(self.receiver, doc.name))

		frappe.db.set_value(
			HANDOVER, doc.name, "response_due", add_to_date(now_datetime(), hours=-30), update_modified=False
		)
		run_handover_reminders()
		run_handover_reminders()
		self.assertEqual(self.events(doc.name).count("Escalated"), 1)
		self.assertEqual(self.events(doc.name).count("Overdue Alert"), 1)

	def test_decided_or_clarified_handovers_are_left_alone(self):
		_task, doc = self.submitted(due_in_hours=-3)
		act_as(self.receiver)
		engine.request_clarification(doc.name, details="Which environment?")
		act_as("Administrator")
		run_handover_reminders()
		self.assertNotIn("Overdue Alert", self.events(doc.name))  # now waiting for the sender

	def test_muting_reminders_never_mutes_required_notices(self):
		act_as("Administrator")
		frappe.get_doc(
			{"doctype": NOTIFICATION_PREFERENCE, "user": self.receiver, "receive_reminders": 0}
		).insert()
		_task, doc = self.submitted(due_in_hours=2)
		run_handover_reminders()
		self.assertFalse(any("must be answered" in s for s in logs(self.receiver, doc.name)))
		# the arrival notice was delivered although the user muted reminders
		self.assertTrue(any("waiting for your acceptance" in s for s in logs(self.receiver, doc.name)))

	def test_reminders_can_be_switched_off(self):
		_task, doc = self.submitted(due_in_hours=2)
		frappe.db.set_single_value("NDS Operations Settings", "enable_reminders", 0)
		frappe.clear_cache()
		self.assertEqual(run_handover_reminders(), {"due_soon": 0, "overdue": 0, "escalated": 0})
		self.assertNotIn("Reminder Sent", self.events(doc.name))

	def test_task_reminder_goes_to_the_current_owner_once(self):
		act_as("Administrator")
		task = self.new_task()
		frappe.db.set_value(
			"Task", task.name, "exp_end_date", frappe.utils.add_days(frappe.utils.nowdate(), -1)
		)
		self.assertGreaterEqual(run_task_reminders(), 1)
		first = frappe.get_all(
			"Notification Log",
			filters={
				"for_user": self.sender,
				"document_name": task.name,
				"subject": ("like", "%is overdue%"),
			},
			pluck="name",
		)
		self.assertEqual(len(first), 1)
		run_task_reminders()
		again = frappe.get_all(
			"Notification Log",
			filters={
				"for_user": self.sender,
				"document_name": task.name,
				"subject": ("like", "%is overdue%"),
			},
			pluck="name",
		)
		self.assertEqual(len(again), 1)
