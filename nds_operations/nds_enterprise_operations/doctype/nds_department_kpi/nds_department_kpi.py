import frappe

from nds_operations.utils.immutable import ImmutableRecord


class NDSDepartmentKPI(ImmutableRecord):
	pass


def on_doctype_update():
	# one snapshot per department and period, also under concurrent runs
	frappe.db.add_unique(
		"NDS Department KPI",
		["department", "period_start", "period_end"],
		constraint_name="unique_department_period",
	)
