import frappe

from nds_operations.api.organization import get_org_chart
from nds_operations.tests.utils import NDSTestCase, act_as


class TestOrgChart(NDSTestCase):
	def test_chart_lists_departments_teams_and_members(self):
		act_as("Administrator")
		team = frappe.get_doc(
			{"doctype": "NDS Team", "team_name": "Chart Squad", "department": self.marketing}
		).insert()
		frappe.get_doc(
			{
				"doctype": "NDS Team Membership",
				"team": team.name,
				"employee": self.sender_employee,
				"is_primary": 1,
			}
		).insert()
		departments = {d["name"]: d for d in get_org_chart()["departments"]}
		self.assertIn(self.marketing, departments)
		self.assertNotIn("All Departments", departments)
		squad = next(t for t in departments[self.marketing]["teams"] if t["name"] == team.name)
		self.assertEqual(squad["member_count"], 1)
		self.assertEqual(squad["members"][0]["role"], "Member")
		self.assertFalse(departments[self.marketing]["parent"])

	def test_requires_an_organization_role(self):
		act_as("Guest")
		with self.assertRaises(frappe.PermissionError):
			get_org_chart()

	def test_plain_employee_still_gets_names_and_parents(self):
		act_as(self.receiver)
		rows = get_org_chart()["departments"]
		self.assertTrue(rows)
		self.assertTrue(all(r["title"] for r in rows))
