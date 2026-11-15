"""Scaling checks: the number of database queries must not grow with the number of rows (no N+1), and the
main screens must stay fast on a seeded data set. Thresholds are generous; they catch regressions, not tune."""

import os
import time

import frappe

from nds_operations.api import handover as api
from nds_operations.api.operations import get_dashboard
from nds_operations.api.organization import get_org_chart
from nds_operations.services import handover as engine
from nds_operations.tests.utils import NDSTestCase, act_as


class QueryCounter:
	def __enter__(self):
		self.count = 0
		self.original = frappe.db.sql
		counter = self

		def counting(*args, **kwargs):
			counter.count += 1
			return counter.original(*args, **kwargs)

		frappe.db.sql = counting
		return self

	def __exit__(self, *exc):
		frappe.db.sql = self.original


class TestPerformance(NDSTestCase):
	def seed(self, rows):
		for i in range(rows):
			act_as("Administrator")
			task = self.new_task(subject=f"Perf task {i}")
			act_as(self.sender)
			doc = engine.create_handover(
				task.name,
				self.receiver_employee,
				{"handover_reason": "Reassignment", "work_done": "Prepared."},
			)
			engine.submit_handover(doc.name)

	def measure(self, fn):
		with QueryCounter() as counter:
			started = time.perf_counter()
			fn()
			elapsed = time.perf_counter() - started
		return counter.count, elapsed

	def screens(self):
		from nds_operations.nds_enterprise_operations.report.employee_workload_report import (
			employee_workload_report as workload,
		)
		from nds_operations.nds_enterprise_operations.report.management_executive_report import (
			management_executive_report as executive,
		)
		from nds_operations.nds_enterprise_operations.report.task_handover_register import (
			task_handover_register as register,
		)

		return {
			"dashboard": lambda: get_dashboard(),
			"inbox": lambda: api.get_inbox(),
			"counts": lambda: api.get_counts(),
			"org chart": lambda: get_org_chart(),
			"register": lambda: register.execute({}),
			"workload": lambda: workload.execute({}),
			"executive": lambda: executive.execute({}),
		}

	def test_queries_do_not_grow_with_rows(self):
		self.seed(5)
		act_as("Administrator")
		small = {name: self.measure(fn)[0] for name, fn in self.screens().items()}
		rows = int(os.environ.get("NDS_PERF_ROWS", 25))
		self.seed(rows)
		act_as("Administrator")
		large, seconds = {}, {}
		for name, fn in self.screens().items():
			queries, elapsed = self.measure(fn)
			large[name], seconds[name] = queries, round(elapsed, 3)
			self.assertLess(elapsed, 3.0, f"{name} took {elapsed:.2f}s")
		for name in small:
			self.assertLessEqual(
				large[name],
				small[name] + 5,
				f"{name}: {small[name]} queries at 5 rows, {large[name]} at {rows + 5}",
			)
		print(
			f"\nqueries (5 -> {rows + 5} handovers):",
			{n: (small[n], large[n]) for n in small},
			"\nseconds:",
			seconds,
		)
