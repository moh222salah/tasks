frappe.query_reports["Tasks Master Report"] = {
	filters: [
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
		{ fieldname: "owner", label: __("Current Owner"), fieldtype: "Link", options: "User" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Open", "Working", "Pending Review", "Overdue", "Completed", "Cancelled"] },
		{ fieldname: "priority", label: __("Priority"), fieldtype: "Select", options: ["", "Low", "Medium", "High", "Urgent"] },
		{ fieldname: "from_date", label: __("Due From"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("Due To"), fieldtype: "Date" },
	],
};
