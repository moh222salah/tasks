"""Fixtures for the module's tests. They only ever run on a throw-away bench (allow_tests), inside the test
runner, and are rolled back with the test class."""

import frappe
from frappe.desk.form import assign_to
from frappe.tests import IntegrationTestCase

from nds_operations.constants import NDS_ROLES
from nds_operations.permissions import clear_scope_cache

PASSWORD = "Test@12345"


def require_test_run():
	if not frappe.flags.in_test:
		raise RuntimeError("NDS test fixtures can only be created by the test runner.")


def get_company():
	return frappe.db.get_value("Company", {}, "name", order_by="creation asc")


def make_department(name, parent="All Departments"):
	require_test_run()
	company = get_company()
	full_name = f"{name} - {frappe.db.get_value('Company', company, 'abbr')}"
	if frappe.db.exists("Department", full_name):
		return full_name
	return (
		frappe.get_doc(
			{
				"doctype": "Department",
				"department_name": name,
				"parent_department": parent,
				"company": company,
			}
		)
		.insert()
		.name
	)


def make_user(email, first_name, roles=()):
	require_test_run()
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": first_name,
				"send_welcome_email": 0,
				"new_password": PASSWORD,
			}
		).insert(ignore_permissions=True)
	frappe.get_doc("User", email).add_roles("Employee", *roles)
	return email


def make_employee(email, first_name, department, designation=None):
	require_test_run()
	existing = frappe.db.get_value("Employee", {"user_id": email}, "name")
	if existing:
		return existing
	return (
		frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": first_name,
				"gender": frappe.db.get_value("Gender", {}, "name"),
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2020-01-01",
				"company": get_company(),
				"department": department,
				"designation": designation,
				"user_id": email,
				"status": "Active",
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def make_task(subject, owner_email, department=None):
	"""An ERPNext Task assigned to its owner through a ToDo, as the Task module itself does."""
	require_test_run()
	task = frappe.get_doc({"doctype": "Task", "subject": subject, "department": department}).insert(
		ignore_permissions=True
	)
	assign_to._add(
		{"assign_to": [owner_email], "doctype": "Task", "name": task.name}, ignore_permissions=True
	)
	return task


def act_as(user):
	"""Switch the session user the way a request would, with fresh role and scope caches."""
	frappe.set_user(user)
	frappe.clear_cache(user=user)
	clear_scope_cache()


class NDSTestCase(IntegrationTestCase):
	"""Builds a small organisation once per class and isolates every test with a savepoint."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.marketing = make_department("NDS Marketing Test")
		cls.technology = make_department("NDS Technology Test")

		def person(key, first_name, department, *roles):
			email = f"{key}@nds-test.example.com"
			make_user(email, first_name, roles)
			employee = make_employee(email, first_name, department)
			setattr(cls, key, email)
			setattr(cls, f"{key}_employee", employee)

		sender_roles = ("NDS Task Sender", "NDS Task Executor")
		person("sender", "Sara Sender", cls.marketing, *sender_roles)
		person("receiver", "Rami Receiver", cls.marketing, "NDS Task Receiver", "NDS Task Sender")
		person("tech", "Tarek Tech", cls.technology, "NDS Task Receiver", "NDS Task Sender")
		person("stranger", "Sami Stranger", cls.marketing, "NDS Task Sender")
		person("auditor", "Aya Auditor", cls.technology, "NDS Read Only Auditor")
		person("ops", "Omar Ops", cls.technology, "NDS Operations Manager")

	def setUp(self):
		super().setUp()
		frappe.db.savepoint("nds_test")
		act_as("Administrator")

	def tearDown(self):
		act_as("Administrator")
		frappe.db.rollback(save_point="nds_test")
		super().tearDown()

	# -- shortcuts ---------------------------------------------------------------------------

	def new_task(self, owner=None, subject="Fix invoice print format", department=None):
		return make_task(subject, owner or self.sender, department or self.marketing)

	def draft(self, task, receiver_employee=None, **data):
		"""A complete draft handover created by the task owner."""
		from nds_operations.services import handover as engine

		act_as(self.sender)
		values = {
			"handover_reason": "Reassignment",
			"work_done": "Diagnosed the print format issue.",
			"technical_diagnosis": "Jinja block removed by a custom patch.",
			**data,
		}
		return engine.create_handover(task.name, receiver_employee or self.receiver_employee, values)
