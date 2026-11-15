frappe.ui.form.on("Task", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.status === "Completed") {
			frm.add_custom_button(
				__("Review Task"),
				() => {
					const dialog = new frappe.ui.Dialog({
						title: __("Review Task"),
						fields: [
							{ fieldname: "verdict", label: __("Verdict"), fieldtype: "Select", options: ["Approved", "Changes Requested"], default: "Approved", reqd: 1 },
							{ fieldname: "quality_score", label: __("Quality Score (1-5)"), fieldtype: "Int", depends_on: "eval:doc.verdict=='Approved'" },
							{ fieldname: "comments", label: __("Comments"), fieldtype: "Text Editor", reqd: 1 },
						],
						primary_action_label: __("Submit Review"),
						primary_action(values) {
							dialog.disable_primary_action();
							frappe
								.xcall("frappe.client.insert", { doc: { doctype: "NDS Task Review", task: frm.doc.name, ...values } })
								.then(() => {
									dialog.hide();
									frappe.show_alert({ message: __("Review recorded"), indicator: "green" });
								})
								.catch(() => dialog.enable_primary_action());
						},
					});
					dialog.show();
				},
				__("NDS")
			);
			frm.add_custom_button(
				__("View Reviews"),
				() => {
					frappe.route_options = { task: frm.doc.name };
					frappe.set_route("List", "NDS Task Review");
				},
				__("NDS")
			);
		}
		if (["Completed", "Cancelled"].includes(frm.doc.status)) return;
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
