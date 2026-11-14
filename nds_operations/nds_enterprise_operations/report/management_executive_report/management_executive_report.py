import frappe
from frappe import _

from nds_operations.reports import average, col, get_rows, get_tasks, hours_between, link

METHOD = _(
	"One row per department: open and overdue tasks (cancelled excluded, tasks waiting on a receiver not "
	"counted as late), and handovers received in the period with their first-pass acceptance rate "
	"(accepted without any earlier rejection or version) and average hours to decision. Blank means no data."
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	tasks = get_tasks({}, open_only=True)
	handovers = get_rows(filters)
	departments = {}

	def dept(name):
		return departments.setdefault(
			name or _("Unassigned"),
			frappe._dict(department=name, open=0, overdue=0, received=0, accepted=0, first_pass=0, hours=[]),
		)

	for task in tasks:
		row = dept(task.department)
		row.open += 1
		row.overdue += bool(task.days_overdue and not task.open_handover)
	for h in handovers:
		row = dept(h.receiver_department)
		row.received += 1
		if h.handover_status == "Accepted":
			row.accepted += 1
			row.first_pass += (h.version_no or 1) == 1
		row.hours.append(hours_between(h.submitted_at, h.decided_at))
	rows = []
	for row in sorted(departments.values(), key=lambda r: r.department or ""):
		row.first_pass_rate = round(100 * row.first_pass / row.accepted, 1) if row.accepted else None
		row.avg_hours = average(row.hours)
		rows.append(row)
	columns = [
		link("department", "Department", "Department", 200),
		col("open", "Open Tasks", "Int", 100),
		col("overdue", "Overdue", "Int", 90),
		col("received", "Handovers Received", "Int", 140),
		col("accepted", "Accepted", "Int", 90),
		col("first_pass_rate", "First-Pass %", "Percent", 110),
		col("avg_hours", "Avg Hours to Decision", "Float", 150),
	]
	summary = [
		{"label": "Open tasks", "value": sum(r.open for r in rows), "datatype": "Int", "indicator": "Blue"},
		{"label": "Overdue", "value": sum(r.overdue for r in rows), "datatype": "Int", "indicator": "Red"},
	]
	return columns, rows, METHOD, None, summary
