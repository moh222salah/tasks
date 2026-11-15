import frappe

from nds_operations.tests.utils import NDSTestCase, act_as


class TestTaskChecklist(NDSTestCase):
	def fresh_task(self, **kw):
		act_as("Administrator")
		return self.new_task(**kw)

	def item(self, task, user, **values):
		act_as(user)
		return frappe.get_doc(
			{"doctype": "NDS Task Checklist", "task": task.name, "title": "Tested on staging", **values}
		).insert()

	def complete(self, task):
		task = frappe.get_doc("Task", task.name)
		task.status = "Completed"
		task.save(ignore_permissions=True)

	def test_required_item_blocks_completion_until_done(self):
		task = self.fresh_task()
		item = self.item(task, self.sender)
		with self.assertRaises(frappe.ValidationError):
			self.complete(task)
		item.is_done = 1
		item.save()
		self.assertEqual(item.done_by, self.sender)
		self.assertTrue(item.done_at)
		self.complete(task)

	def test_optional_item_and_tasks_without_checklist_are_unaffected(self):
		task = self.fresh_task()
		self.item(task, self.sender, is_required=0)
		self.complete(task)
		other = self.fresh_task(subject="No checklist")
		self.complete(other)

	def test_only_the_current_owner_changes_the_checklist(self):
		task = self.fresh_task()
		with self.assertRaises(frappe.PermissionError):
			self.item(task, self.receiver)
		with self.assertRaises(frappe.PermissionError):
			self.item(task, "Administrator")

	def test_done_item_cannot_be_deleted_and_untick_clears_the_stamp(self):
		task = self.fresh_task()
		item = self.item(task, self.sender, is_done=1)
		with self.assertRaises(frappe.PermissionError):
			frappe.delete_doc("NDS Task Checklist", item.name)
		item.is_done = 0
		item.save()
		self.assertFalse(item.done_by)
		frappe.delete_doc("NDS Task Checklist", item.name)

	def test_done_by_cannot_be_forged(self):
		task = self.fresh_task()
		item = self.item(task, self.sender, is_done=1, done_by=self.receiver)
		self.assertEqual(item.done_by, self.sender)
