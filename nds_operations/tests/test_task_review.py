import frappe

from nds_operations.tests.utils import NDSTestCase, act_as, make_user


class TestTaskReview(NDSTestCase):
	def completed_task(self):
		act_as("Administrator")
		task = self.new_task()
		frappe.db.set_value("Task", task.name, "status", "Completed")
		return task

	def review(self, task, user, **values):
		act_as(user)
		return frappe.get_doc(
			{
				"doctype": "NDS Task Review",
				"task": task.name,
				"verdict": "Approved",
				"quality_score": 4,
				"comments": "Looks right.",
				**values,
			}
		).insert()

	def reviewer(self):
		act_as("Administrator")
		return make_user("reviewer@nds-test.example.com", "Rana Reviewer", ("NDS Task Reviewer",))

	def test_reviewer_records_a_review_with_owner_and_stamp(self):
		task = self.completed_task()
		doc = self.review(task, self.reviewer(), reviewer=self.receiver)
		self.assertEqual(doc.reviewer, "reviewer@nds-test.example.com")
		self.assertEqual(doc.reviewed_owner, self.sender)
		self.assertTrue(doc.reviewed_at)

	def test_owner_and_non_reviewers_cannot_review(self):
		task = self.completed_task()
		self.reviewer()
		with self.assertRaises(frappe.PermissionError):
			self.review(task, self.sender)  # not a reviewer
		act_as("Administrator")
		frappe.get_doc(
			{
				"doctype": "Has Role",
				"parent": self.sender,
				"parenttype": "User",
				"parentfield": "roles",
				"role": "NDS Task Reviewer",
			}
		).insert(ignore_permissions=True)
		with self.assertRaises(frappe.PermissionError):
			self.review(task, self.sender)  # reviewer role, but he owns the task

	def test_only_completed_tasks_and_a_score_for_approval(self):
		open_task = self.new_task(subject="Still open")
		reviewer = self.reviewer()
		with self.assertRaises(frappe.ValidationError):
			self.review(open_task, reviewer)
		task = self.completed_task()
		with self.assertRaises(frappe.ValidationError):
			self.review(task, reviewer, quality_score=0)
		doc = self.review(task, reviewer, verdict="Changes Requested", quality_score=5)
		self.assertIsNone(doc.quality_score)

	def test_review_is_append_only(self):
		task = self.completed_task()
		doc = self.review(task, self.reviewer())
		doc.comments = "changed"
		with self.assertRaises(frappe.PermissionError):
			doc.save()
		act_as("Administrator")
		with self.assertRaises(frappe.PermissionError):
			frappe.delete_doc("NDS Task Review", doc.name, force=True)
