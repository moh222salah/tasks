frappe.ui.form.on("NDS Task Handover", {
	refresh(frm) {
		frm.dashboard.clear_headline();
		if (frm.is_new()) {
			frm.set_intro(
				__("Fill in the handover. Identity, status and ownership are set by the system."),
				"blue",
			);
			return;
		}
		nds_operations.api("get_handover_details", { name: frm.doc.name }).then((data) => {
			frm.nds = data;
			nds_operations_render(frm, data);
		});
	},
});

function nds_operations_render(frm, data) {
	const o = nds_operations;
	const doc = data.doc;

	const verified =
		data.snapshot_verified === null
			? ""
			: data.snapshot_verified
				? `<span class="nds-verified">✔ ${__("Record integrity verified")}</span>`
				: `<span class="nds-verified bad">✖ ${__("Record does not match its submitted snapshot")}</span>`;

	const html = `<div class="nds-page">
		${o.render_stages(doc.handover_status)}
		<div class="nds-panels">
			<div class="nds-card"><h5>${__("Timeline")}</h5>${o.render_timeline(data.history)} ${verified}</div>
			<div class="nds-card"><h5>${__("Responsibility History")}</h5>${o.render_ledger(data.ownership)}</div>
			${data.reviews.length ? `<div class="nds-card"><h5>${__("Receiver Decisions")}</h5>${o.render_reviews(data.reviews)}</div>` : ""}
			${o.render_versions(data.versions, doc.name)}
		</div>
	</div>`;
	frm.dashboard.add_section(html, __("Handover Workspace"));

	frm.page.clear_custom_actions?.();
	const actions = {
		mark_ready: () => nds_call(frm, "mark_ready", {}),
		reopen_draft: () => nds_call(frm, "reopen_draft", {}),
		submit: () => nds_submit(frm),
		start_review: () => nds_call(frm, "start_review", {}),
		accept: () => nds_accept_dialog(frm),
		reject: () => nds_reject_dialog(frm),
		request_clarification: () => nds_clarify_dialog(frm),
		withdraw: () => nds_withdraw_dialog(frm),
		revise: () => nds_revise(frm),
		handover_again: () => {
			nds_operations.new_handover_dialog(doc.task);
		},
	};
	const labels = {
		mark_ready: [__("Mark Ready"), null],
		reopen_draft: [__("Back to Draft"), null],
		submit: [__("Submit Handover"), "primary"],
		start_review: [__("Start Review"), null],
		accept: [__("Accept Handover"), "primary"],
		reject: [__("Reject Handover"), "danger"],
		request_clarification: [__("Request Clarification"), null],
		withdraw: [__("Withdraw"), "danger"],
		revise: [__("Return for Completion"), "primary"],
		handover_again: [__("Hand Over Again"), null],
	};
	data.allowed_actions.forEach((key) => {
		if (!actions[key] || !labels[key]) return;
		const [label, style] = labels[key];
		const button = frm.add_custom_button(label, actions[key]);
		if (style === "primary") button.removeClass("btn-default").addClass("btn-primary");
		if (style === "danger") button.removeClass("btn-default").addClass("btn-danger");
	});
	// the stock Submit button skips the request id, so the engine's retry-safe one replaces it
	if (frm.doc.docstatus === 0) frm.page.btn_primary?.hide?.();
}

function nds_call(frm, method, args) {
	return nds_operations
		.api(method, Object.assign({ name: frm.doc.name }, args), true)
		.then(() => frm.reload_doc());
}

function nds_submit(frm) {
	const go = () => nds_call(frm, "submit_handover", { request_id: frappe.utils.get_random(16) });
	if (frm.is_dirty()) return frm.save().then(go);
	return go();
}

function nds_revise(frm) {
	nds_operations
		.api("revise_handover", { name: frm.doc.name, request_id: frappe.utils.get_random(16) })
		.then((r) => frappe.set_route("Form", "NDS Task Handover", r.name));
}

function nds_decision_dialog(frm, title, fields, method, primary_label, extra) {
	const request_id = frappe.utils.get_random(16); // one id per dialog: a double click is a retry, not a second decision
	const dialog = new frappe.ui.Dialog({
		title,
		fields,
		primary_action_label: primary_label,
		primary_action(values) {
			dialog.disable_primary_action();
			nds_operations
				.api(method, Object.assign({ name: frm.doc.name, request_id }, values, extra || {}))
				.then(() => {
					dialog.hide();
					frm.reload_doc();
				})
				.catch(() => dialog.enable_primary_action());
		},
	});
	dialog.show();
}

function nds_accept_dialog(frm) {
	nds_decision_dialog(
		frm,
		__("Accept Handover"),
		[
			{ fieldtype: "Check", fieldname: "confirmed_details_reviewed", label: __("I reviewed the task details and technical record"), reqd: 1 },
			{ fieldtype: "Check", fieldname: "confirmed_attachments_received", label: __("I received the files, screenshots and links"), reqd: 1 },
			{ fieldtype: "Check", fieldname: "confirmed_responsibilities_understood", label: __("I understand my responsibilities for this task"), reqd: 1 },
			{ fieldtype: "Small Text", fieldname: "details", label: __("Receiving Notes") },
			{ fieldtype: "Small Text", fieldname: "next_step", label: __("Next Step") },
			{ fieldtype: "Date", fieldname: "expected_start", label: __("Expected Start") },
		],
		"accept_handover",
		__("Accept and Take Responsibility"),
	);
}

function nds_reject_dialog(frm) {
	nds_decision_dialog(
		frm,
		__("Reject Handover"),
		[
			{ fieldtype: "Link", options: "NDS Rejection Reason", fieldname: "rejection_reason", label: __("Reason"), reqd: 1 },
			{ fieldtype: "Small Text", fieldname: "details", label: __("What is wrong?"), reqd: 1 },
		],
		"reject_handover",
		__("Reject"),
	);
}

function nds_clarify_dialog(frm) {
	nds_decision_dialog(
		frm,
		__("Request Clarification"),
		[{ fieldtype: "Small Text", fieldname: "details", label: __("Questions / missing information"), reqd: 1 }],
		"request_clarification",
		__("Send Request"),
	);
}

function nds_withdraw_dialog(frm) {
	nds_decision_dialog(
		frm,
		__("Withdraw Handover"),
		[{ fieldtype: "Small Text", fieldname: "reason", label: __("Reason"), reqd: 1 }],
		"withdraw_handover",
		__("Withdraw"),
	);
}
