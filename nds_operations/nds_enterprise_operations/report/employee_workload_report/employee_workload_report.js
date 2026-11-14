frappe.query_reports["Employee Workload Report"] = {
	filters: [
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
	],
};
