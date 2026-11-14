frappe.query_reports["Task Handover Register"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
		{ fieldname: "employee", label: __("Employee (sender or receiver)"), fieldtype: "Link", options: "Employee" },
		{ fieldname: "sender_department", label: __("Sender Department"), fieldtype: "Link", options: "Department" },
		{ fieldname: "receiver_department", label: __("Receiver Department"), fieldtype: "Link", options: "Department" },
		{
			fieldname: "handover_status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Pending Acceptance", "Under Review", "Clarification Requested", "Accepted", "Rejected", "Withdrawn"],
		},
	],
};
