import frappe

from nds_operations.constants import HANDOVER
from nds_operations.services import handover as engine
from nds_operations.tests.utils import NDSTestCase, act_as, make_employee, make_user


class TestOrganisationScope(NDSTestCase):
	"""Team leaders and department managers see their own scope, resolved live from Employee links."""

	def submitted(self):
		task = self.new_task()
		doc = self.draft(task)
		act_as(self.sender)
		engine.submit_handover(doc.name)
		return task, doc

	def listed(self, user, task):
		act_as(user)
		return set(frappe.get_list(HANDOVER, filters={"task": task.name}, pluck="name", limit_page_length=0))

	def test_department_manager_sees_the_department_only(self):
		task, doc = self.submitted()
		act_as("Administrator")
		boss = make_user("boss@nds-test.example.com", "Bassem Boss", ("NDS Department Manager",))
		boss_employee = make_employee(boss, "Bassem Boss", self.technology)
		self.assertEqual(self.listed(boss, task), set())  # not a manager yet

		act_as("Administrator")
		frappe.get_doc(
			{
				"doctype": "NDS Department Profile",
				"department": self.marketing,
				"department_manager": boss_employee,
			}
		).insert()
		self.assertEqual(self.listed(boss, task), {doc.name})
		self.assertFalse(frappe.has_permission(HANDOVER, "write", doc=doc.name, user=boss))

		# the scope follows the Employee link: unlink the user and the visibility goes with it
		act_as("Administrator")
		frappe.db.set_value("Employee", boss_employee, "user_id", None)
		self.assertEqual(self.listed(boss, task), set())

	def test_team_lead_sees_the_team_only(self):
		task, _doc = self.submitted()
		act_as("Administrator")
		lead = make_user("lead@nds-test.example.com", "Lina Lead", ("NDS Team Leader",))
		lead_employee = make_employee(lead, "Lina Lead", self.technology)
		team = frappe.get_doc(
			{"doctype": "NDS Team", "team_name": "Marketing Squad", "department": self.marketing}
		).insert()
		self.assertEqual(self.listed(lead, task), set())

		# the sender's team is stamped on the handover, so the lead of that team sees it
		act_as("Administrator")
		frappe.get_doc(
			{
				"doctype": "NDS Team Membership",
				"team": team.name,
				"employee": self.sender_employee,
				"is_primary": 1,
			}
		).insert()
		other = self.new_task(subject="Second task")
		second = self.draft(other)
		act_as(self.sender)
		engine.submit_handover(second.name)
		act_as("Administrator")
		team.team_lead = lead_employee
		team.save()
		self.assertEqual(self.listed(lead, other), {second.name})
		self.assertEqual(self.listed(lead, task), set())  # submitted before the sender joined the team

	def test_memberships_cannot_overlap_and_primary_team_is_unique(self):
		act_as("Administrator")
		first = frappe.get_doc(
			{"doctype": "NDS Team", "team_name": "Squad A", "department": self.marketing}
		).insert()
		second = frappe.get_doc(
			{"doctype": "NDS Team", "team_name": "Squad B", "department": self.marketing}
		).insert()
		membership = {"employee": self.sender_employee, "is_primary": 1}
		frappe.get_doc({"doctype": "NDS Team Membership", "team": first.name, **membership}).insert()
		with self.assertRaises(frappe.ValidationError):  # same team, overlapping dates
			frappe.get_doc(
				{"doctype": "NDS Team Membership", "team": first.name, "employee": self.sender_employee}
			).insert()
		with self.assertRaises(frappe.ValidationError):  # a second primary team
			frappe.get_doc({"doctype": "NDS Team Membership", "team": second.name, **membership}).insert()
		frappe.get_doc(
			{"doctype": "NDS Team Membership", "team": second.name, "employee": self.sender_employee}
		).insert()
