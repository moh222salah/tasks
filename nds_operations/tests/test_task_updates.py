import frappe

from nds_operations.services import handover as engine
from nds_operations.tests.utils import NDSTestCase, act_as


class TestTaskUpdates(NDSTestCase):
	def post(self, task, user, **values):
		act_as(user)
		doc = frappe.get_doc(
			{
				"doctype": "NDS Task Update",
				"task": task.name,
				"update_type": "Progress",
				"note": "Working on it.",
				**values,
			}
		)
		return doc.insert()

	def test_owner_posts_and_task_progress_follows(self):
		task = self.new_task()
		doc = self.post(task, self.sender, progress=40)
		self.assertEqual(doc.author, self.sender)
		self.assertEqual(frappe.db.get_value("Task", task.name, "progress"), 40)

	def test_author_cannot_be_forged(self):
		task = self.new_task()
		doc = self.post(task, self.sender, author=self.receiver)
		self.assertEqual(doc.author, self.sender)

	def test_non_owner_is_refused_even_as_administrator(self):
		task = self.new_task()
		with self.assertRaises(frappe.PermissionError):
			self.post(task, self.receiver)
		with self.assertRaises(frappe.PermissionError):
			self.post(task, "Administrator")

	def test_ownership_moves_the_right_to_post_only_on_acceptance(self):
		task = self.new_task()
		act_as(self.sender)
		doc = engine.create_handover(
			task.name, self.receiver_employee, {"handover_reason": "Reassignment", "work_done": "Done."}
		)
		engine.submit_handover(doc.name)
		with self.assertRaises(frappe.PermissionError):
			self.post(task, self.receiver)  # pending: still the sender's task
		act_as(self.receiver)
		engine.accept_handover(
			doc.name,
			confirmed_details_reviewed=1,
			confirmed_attachments_received=1,
			confirmed_responsibilities_understood=1,
		)
		self.post(task, self.receiver, progress=10)
		with self.assertRaises(frappe.PermissionError):
			self.post(task, self.sender)

	def test_append_only_and_range(self):
		task = self.new_task()
		doc = self.post(task, self.sender)
		doc.note = "edited"
		with self.assertRaises(frappe.PermissionError):
			doc.save()
		act_as("Administrator")
		with self.assertRaises(frappe.PermissionError):
			frappe.delete_doc("NDS Task Update", doc.name, force=True)
		with self.assertRaises(frappe.ValidationError):
			self.post(task, self.sender, progress=140)

	def test_stranger_does_not_see_updates(self):
		task = self.new_task()
		doc = self.post(task, self.sender)
		act_as(self.receiver)
		self.assertFalse(frappe.has_permission("NDS Task Update", "read", doc=doc))
