"""Real concurrency: every worker has its own database connection and transaction, so row locks really
contend. This needs committed fixtures, so the test builds them itself and deletes them in `finally`.
Only ever run on a throw-away bench (allow_tests)."""

import threading

import frappe
from frappe.tests import IntegrationTestCase

from nds_operations.constants import (
	HANDOVER,
	HANDOVER_HISTORY,
	HANDOVER_REVIEW,
	OWNERSHIP_HISTORY,
)
from nds_operations.services import handover as engine
from nds_operations.tests.utils import (
	act_as,
	make_department,
	make_employee,
	make_task,
	make_user,
)

CONFIRM = {
	"confirmed_details_reviewed": 1,
	"confirmed_attachments_received": 1,
	"confirmed_responsibilities_understood": 1,
}


def run_parallel(site, sites_path, jobs):
	"""Run each job in its own thread and connection, released together by a barrier."""
	barrier = threading.Barrier(len(jobs))
	results = [None] * len(jobs)

	def worker(index, user, job):
		frappe.init(site=site, sites_path=sites_path)
		frappe.connect()
		frappe.flags.in_test = True
		frappe.set_user(user)
		try:
			barrier.wait(timeout=30)
			outcome = ("ok", job())
			frappe.db.commit()
		except Exception as error:
			frappe.db.rollback()
			outcome = ("error", type(error).__name__)
		finally:
			frappe.destroy()
		results[index] = outcome

	threads = [threading.Thread(target=worker, args=(i, user, job)) for i, (user, job) in enumerate(jobs)]
	for thread in threads:
		thread.start()
	for thread in threads:
		thread.join(timeout=60)
	return results


class TestConcurrency(IntegrationTestCase):
	def build_world(self):
		frappe.set_user("Administrator")
		suffix = frappe.generate_hash(length=6)
		department = make_department("NDS Marketing Test")
		world = frappe._dict(users=[], tasks=[])
		for key in ("sender", "receiver"):
			email = f"conc-{key}-{suffix}@nds-test.example.com"
			make_user(email, f"Conc {key}", ("NDS Task Sender",))
			world[key] = email
			world[f"{key}_employee"] = make_employee(email, f"Conc {key}", department)
			world.users.append(email)
		world.department = department
		return world

	def new_submitted_handover(self, world, subject):
		task = make_task(subject, world.sender, world.department)
		world.tasks.append(task.name)
		act_as(world.sender)
		doc = engine.create_handover(
			task.name, world.receiver_employee, {"handover_reason": "Reassignment", "work_done": "Done."}
		)
		engine.submit_handover(doc.name)
		act_as("Administrator")
		return task.name, doc.name

	def cleanup(self, world):
		frappe.db.rollback()
		frappe.set_user("Administrator")
		for task in world.tasks:
			handovers = frappe.get_all(HANDOVER, filters={"task": task}, pluck="name")
			for name in handovers:
				frappe.db.delete("NDS Handover Attachment", {"parent": name})
			for doctype, field in (
				(HANDOVER_HISTORY, "task"),
				(HANDOVER_REVIEW, "task"),
				(OWNERSHIP_HISTORY, "task"),
				(HANDOVER, "task"),
			):
				frappe.db.delete(doctype, {field: task})
			frappe.db.delete("ToDo", {"reference_type": "Task", "reference_name": task})
			frappe.db.delete("DocShare", {"share_doctype": "Task", "share_name": task})
			frappe.db.delete("Comment", {"reference_doctype": "Task", "reference_name": task})
			frappe.db.delete("Task", {"name": task})
		for email in world.users:
			frappe.db.delete("Notification Log", {"for_user": email})
			frappe.db.delete("Employee", {"user_id": email})
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		frappe.db.commit()

	def test_scenario_7_two_simultaneous_accepts_transfer_once(self):
		world = self.build_world()
		task, handover = self.new_submitted_handover(world, "Race: double accept")
		frappe.db.commit()
		try:
			results = run_parallel(
				frappe.local.site,
				frappe.local.sites_path,
				[
					(world.receiver, lambda: engine.accept_handover(handover, **CONFIRM, request_id="race-a")),
					(world.receiver, lambda: engine.accept_handover(handover, **CONFIRM, request_id="race-b")),
				],
			)
			self.assertEqual(sorted(r[0] for r in results), ["error", "ok"], results)
			frappe.db.rollback()  # drop this connection's stale snapshot before reading the outcome
			self.assertEqual(frappe.db.count(HANDOVER_REVIEW, {"handover": handover}), 1)
			self.assertEqual(frappe.db.count(OWNERSHIP_HISTORY, {"task": task}), 2)
			self.assertEqual(frappe.db.get_value(HANDOVER, handover, "handover_status"), "Accepted")
			todos = frappe.get_all(
				"ToDo",
				filters={"reference_type": "Task", "reference_name": task, "status": "Open"},
				pluck="allocated_to",
			)
			self.assertEqual(todos, [world.receiver])
		finally:
			self.cleanup(world)

	def test_accept_racing_withdraw_has_one_winner(self):
		world = self.build_world()
		task, handover = self.new_submitted_handover(world, "Race: accept vs withdraw")
		frappe.db.commit()
		try:
			results = run_parallel(
				frappe.local.site,
				frappe.local.sites_path,
				[
					(world.receiver, lambda: engine.accept_handover(handover, **CONFIRM, request_id="x-1")),
					(world.sender, lambda: engine.withdraw_handover(handover, "changed my mind", "x-2")),
				],
			)
			self.assertEqual(sorted(r[0] for r in results), ["error", "ok"], results)
			frappe.db.rollback()
			status = frappe.db.get_value(HANDOVER, handover, "handover_status")
			ledger = frappe.db.count(OWNERSHIP_HISTORY, {"task": task})
			if status == "Accepted":
				self.assertEqual(ledger, 2)
			else:
				self.assertEqual((status, ledger), ("Withdrawn", 0))
		finally:
			self.cleanup(world)

	def test_two_drafts_submitted_at_once_only_one_goes_through(self):
		world = self.build_world()
		task = make_task("Race: two drafts", world.sender, world.department)
		world.tasks.append(task.name)
		act_as(world.sender)
		values = {"handover_reason": "Reassignment", "work_done": "Done."}
		first = engine.create_handover(task.name, world.receiver_employee, values)
		second = engine.create_handover(task.name, world.receiver_employee, values)
		act_as("Administrator")
		frappe.db.commit()
		try:
			results = run_parallel(
				frappe.local.site,
				frappe.local.sites_path,
				[
					(world.sender, lambda: engine.submit_handover(first.name, "d-1")),
					(world.sender, lambda: engine.submit_handover(second.name, "d-2")),
				],
			)
			self.assertEqual(sorted(r[0] for r in results), ["error", "ok"], results)
			frappe.db.rollback()
			self.assertEqual(
				frappe.db.count(HANDOVER, {"task": task.name, "docstatus": 1, "handover_status": "Pending Acceptance"}),
				1,
			)
		finally:
			self.cleanup(world)
