frappe.ui.form.on("Task", {
	refresh(frm) {
		if (frm.is_new() || ["Completed", "Cancelled"].includes(frm.doc.status)) return;
		frm.add_custom_button(
			__("Post Update"),
			() => {
				const dialog = new frappe.ui.Dialog({
					title: __("Post Update"),
					fields: [
						{
							fieldname: "update_type",
							label: __("Update Type"),
							fieldtype: "Select",
							options: ["Progress", "Issue", "Help Request", "Evidence", "Note"],
							default: "Progress",
							reqd: 1,
						},
						{ fieldname: "progress", label: __("Progress %"), fieldtype: "Percent" },
						{ fieldname: "note", label: __("Note"), fieldtype: "Text Editor", reqd: 1 },
						{ fieldname: "link", label: __("Evidence Link"), fieldtype: "Data", options: "URL" },
					],
					primary_action_label: __("Post"),
					primary_action(values) {
						dialog.disable_primary_action();
						frappe
							.xcall("frappe.client.insert", {
								doc: { doctype: "NDS Task Update", task: frm.doc.name, ...values },
							})
							.then(() => {
								dialog.hide();
								frappe.show_alert({ message: __("Update posted"), indicator: "green" });
								frm.reload_doc();
							})
							.catch(() => dialog.enable_primary_action());
					},
				});
				dialog.show();
			},
			__("NDS")
		);
		frm.add_custom_button(
			__("View Updates"),
			() => {
				frappe.route_options = { task: frm.doc.name };
				frappe.set_route("List", "NDS Task Update");
			},
			__("NDS")
		);
		frm.add_custom_button(
			__("View Checklist"),
			() => {
				frappe.route_options = { task: frm.doc.name };
				frappe.set_route("List", "NDS Task Checklist");
			},
			__("NDS")
		);
	},
});
