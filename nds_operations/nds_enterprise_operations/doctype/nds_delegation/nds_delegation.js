frappe.ui.form.on("NDS Delegation", {
	refresh(frm) {
		if (frm.is_new()) {
			frm.set_value("delegator", frm.doc.delegator || frappe.session.user);
			return;
		}
		frm.disable_form();
		if (!frm.doc.is_revoked && frm.doc.status !== "Expired") {
			frm.add_custom_button(__("Revoke"), () => {
				frappe.confirm(__("Revoke this delegation? The delegate can no longer decide your handovers."), () => {
					frappe.xcall(
						"nds_operations.nds_enterprise_operations.doctype.nds_delegation.nds_delegation.revoke_delegation",
						{ name: frm.doc.name }
					).then(() => frm.reload_doc());
				});
			}).addClass("btn-danger");
		}
	},
});
