import frappe

from nds_operations.api.profile import get_employee_profile, get_team_profile
from nds_operations.services import handover as engine
from nds_operations.tests.utils import NDSTestCase, act_as, make_employee, make_user

CONFIRM = {
	"confirmed_details_reviewed": 1,
	"confirmed_attachments_received": 1,
	"confirmed_responsibilities_understood": 1,
}


class TestProfiles(NDSTestCase):
	def hand_over(self, accept):
		act_as("Administrator")
		task = self.new_task()
		doc = self.draft(task)
		act_as(self.sender)
		engine.submit_handover(doc.name)
		act_as(self.receiver)
		if accept:
			engine.accept_handover(doc.name, **CONFIRM)
		else:
			engine.reject_handover(doc.name, rejection_reason="Missing Information", details="Not enough.")
		return task

	def figures(self, employee):
		act_as("Administrator")
		return get_employee_profile(employee)["stats"]

	def test_employee_profile_figures(self):
		sender_before = self.figures(self.sender_employee)
		receiver_before = self.figures(self.receiver_employee)
		self.hand_over(accept=True)
		self.hand_over(accept=False)
		act_as("Administrator")
		sender = get_employee_profile(self.sender_employee)
		receiver = get_employee_profile(self.receiver_employee)
		self.assertEqual(sender["employee"]["employee_name"], "Sara Sender")
		self.assertEqual(sender["stats"]["handovers_sent"] - sender_before["handovers_sent"], 2)
		# ownership follows the ledger: of the two new tasks the accepted one moved, the rejected one stayed
		self.assertEqual(sender["stats"]["open_tasks"] - sender_before["open_tasks"], 1)
		self.assertEqual(receiver["stats"]["open_tasks"] - receiver_before["open_tasks"], 1)
		self.assertTrue(sender["handovers"])
		self.assertTrue(all(h["sender_user"] == self.sender or h["receiver_user"] == self.sender for h in sender["handovers"]))
		for key in ("first_pass_rate", "rejection_rate", "on_time_rate"):
			value = sender["stats"][key]
			self.assertTrue(value is None or 0 <= value <= 100)

	def test_own_profile_needs_no_argument(self):
		act_as(self.sender)
		self.assertEqual(get_employee_profile()["employee"]["name"], self.sender_employee)

	def test_overdue_is_excused_while_a_handover_waits(self):
		act_as("Administrator")
		before = self.profile_stats()
		task = self.new_task()
		frappe.db.set_value("Task", task.name, "exp_end_date", frappe.utils.add_days(frappe.utils.nowdate(), -3))
		late = self.profile_stats()
		self.assertEqual(late["overdue_tasks"] - before["overdue_tasks"], 1)
		doc = self.draft(task)
		act_as(self.sender)
		engine.submit_handover(doc.name)
		stats = self.profile_stats()
		self.assertEqual(stats["overdue_tasks"] - before["overdue_tasks"], 0)
		self.assertEqual(stats["waiting_on_handover"] - before["waiting_on_handover"], 1)

	def profile_stats(self):
		act_as("Administrator")
		return get_employee_profile(self.sender_employee)["stats"]

	def test_employee_without_user_has_no_figures(self):
		act_as("Administrator")
		email = "nouser@nds-test.example.com"
		employee = make_employee(make_user(email, "Nadia NoUser"), "Nadia NoUser", self.marketing)
		frappe.db.set_value("Employee", employee, "user_id", None)
		self.assertIsNone(get_employee_profile(employee)["stats"])

	def test_guest_and_unknown_are_refused(self):
		act_as("Guest")
		with self.assertRaises(frappe.PermissionError):
			get_employee_profile(self.sender_employee)
		with self.assertRaises(frappe.PermissionError):
			get_team_profile("anything")
		act_as("Administrator")
		with self.assertRaises(frappe.DoesNotExistError):
			get_employee_profile("EMP-DOES-NOT-EXIST")
		with self.assertRaises(frappe.DoesNotExistError):
			get_team_profile("TEAM-DOES-NOT-EXIST")

	def test_team_profile_flags_a_heavy_load(self):
		act_as("Administrator")
		team = frappe.get_doc(
			{"doctype": "NDS Team", "team_name": "Profile Squad", "department": self.marketing}
		).insert()
		for employee in (self.sender_employee, self.receiver_employee):
			frappe.get_doc({"doctype": "NDS Team Membership", "team": team.name, "employee": employee}).insert()
		base = {m["name"]: m["open_tasks"] for m in get_team_profile(team.name)["members"]}
		for i in range(8):
			self.new_task(subject=f"Heavy {i}")
		profile = get_team_profile(team.name)
		by_name = {m["name"]: m for m in profile["members"]}
		self.assertEqual(by_name["Sara Sender"]["open_tasks"] - base["Sara Sender"], 8)
		self.assertEqual(by_name["Rami Receiver"]["open_tasks"], base["Rami Receiver"])
		self.assertTrue(by_name["Sara Sender"]["heavy"])
		self.assertFalse(by_name["Rami Receiver"]["heavy"])
		self.assertEqual(profile["totals"]["open_tasks"], sum(m["open_tasks"] for m in profile["members"]))
		self.assertIsNone(profile["handovers"]["first_pass_rate"])

	def test_a_balanced_team_has_no_heavy_member(self):
		act_as("Administrator")
		team = frappe.get_doc(
			{"doctype": "NDS Team", "team_name": "Balanced Squad", "department": self.marketing}
		).insert()
		frappe.get_doc(
			{"doctype": "NDS Team Membership", "team": team.name, "employee": self.sender_employee}
		).insert()
		self.assertFalse(any(m["heavy"] for m in get_team_profile(team.name)["members"]))

	def test_a_colleague_cannot_open_anothers_profile_without_employee_access(self):
		act_as(self.stranger)
		readable = frappe.has_permission("Employee", "read", self.sender_employee)
		if readable:
			self.assertEqual(get_employee_profile(self.sender_employee)["employee"]["name"], self.sender_employee)
		else:
			with self.assertRaises(frappe.PermissionError):
				get_employee_profile(self.sender_employee)
