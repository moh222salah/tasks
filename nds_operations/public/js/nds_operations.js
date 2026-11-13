frappe.provide("nds_operations");

(function () {
	const e = (value) => frappe.utils.escape_html(value == null ? "" : String(value));

	const STATUS_CLASS = {
		Draft: "muted",
		"Ready for Handover": "gold",
		"Pending Acceptance": "warn",
		"Under Review": "gold",
		"Clarification Requested": "warn",
		Accepted: "ok",
		Rejected: "bad",
		Withdrawn: "muted",
	};
	const EVENT_CLASS = {
		Accepted: "ok",
		"Responsibility Transferred": "ok",
		Rejected: "bad",
		Withdrawn: "bad",
		"Clarification Requested": "warn",
		Superseded: "warn",
	};
	const STAGES = [
		__("Draft"),
		__("Ready"),
		__("Submitted"),
		__("Under Review"),
		__("Decision"),
		__("Responsibility Transferred"),
	];

	Object.assign(nds_operations, {
		e,
		// read endpoints are GET-only on the server, every action is POST-only
		api: (method, args) =>
			frappe.xcall(
				`nds_operations.api.handover.${method}`,
				args || {},
				method.startsWith("get_") ? "GET" : "POST",
			),

		status_pill(status) {
			return `<span class="nds-pill ${STATUS_CLASS[status] || ""}">${e(__(status))}</span>`;
		},

		// index of the stage a status sits on, and how the decision stage should look
		stage_state(status) {
			const map = {
				Draft: [0, ""],
				"Ready for Handover": [1, ""],
				"Pending Acceptance": [2, ""],
				"Under Review": [3, ""],
				"Clarification Requested": [4, "bad"],
				Rejected: [4, "bad"],
				Withdrawn: [2, "bad"],
				Accepted: [5, ""],
			};
			return map[status] || [0, ""];
		},

		render_stages(status) {
			const [current, tone] = this.stage_state(status);
			const cells = STAGES.map((label, i) => {
				let cls = "";
				if (i < current) cls = "is-done";
				else if (i === current) cls = tone === "bad" ? "is-bad" : "is-current";
				if (status === "Accepted" && i === current) cls = "is-done";
				return `<div class="nds-stage ${cls}">${e(label)}</div>`;
			});
			return `<div class="nds-stages nds-page">${cells.join("")}</div>`;
		},

		render_timeline(history) {
			if (!history.length) return `<div class="text-muted">${__("No activity yet.")}</div>`;
			const items = history.map(
				(h) => `<li class="${EVENT_CLASS[h.event_type] || ""}">
					<b>${e(__(h.event_type))}</b>
					${h.to_status ? `<span class="text-muted"> → ${e(__(h.to_status))}</span>` : ""}
					<div class="when">${e(h.actor_name || h.actor)} · ${frappe.datetime.str_to_user(h.event_time)}</div>
					${h.remarks && h.event_type !== "Submitted" ? `<div>${e(h.remarks)}</div>` : ""}
				</li>`,
			);
			return `<ul class="nds-timeline">${items.join("")}</ul>`;
		},

		render_ledger(rows) {
			if (!rows.length)
				return `<div class="text-muted">${__("Responsibility has not moved yet.")}</div>`;
			const body = rows.map(
				(r) => `<tr>
					<td>${r.sequence}</td>
					<td>${e(r.from_user || "—")}</td>
					<td><b>${e(r.to_user)}</b></td>
					<td>${e(r.to_department || "")}</td>
					<td>${r.transferred_at ? frappe.datetime.str_to_user(r.transferred_at) : ""}</td>
				</tr>`,
			);
			return `<table class="nds-ledger"><thead><tr>
				<th>#</th><th>${__("From")}</th><th>${__("To")}</th><th>${__("Department")}</th><th>${__("When")}</th>
				</tr></thead><tbody>${body.join("")}</tbody></table>`;
		},

		render_reviews(reviews) {
			if (!reviews.length) return "";
			return reviews
				.map(
					(r) => `<div class="mb-2">
						<span class="nds-pill ${r.decision === "Accepted" ? "ok" : r.decision === "Rejected" ? "bad" : "warn"}">${e(__(r.decision))}</span>
						<span class="text-muted"> ${e(r.reviewer_name)} · ${frappe.datetime.str_to_user(r.reviewed_at)}</span>
						${r.rejection_reason ? `<div><b>${e(__(r.rejection_reason))}</b></div>` : ""}
						<div>${e(r.details || "")}</div>
						${r.next_step ? `<div class="text-muted">${__("Next step")}: ${e(r.next_step)}</div>` : ""}
					</div>`,
				)
				.join("");
		},

		render_versions(versions, current) {
			if (versions.length < 2) return "";
			const chips = versions.map(
				(v) => `<a class="nds-pill ${v.name === current ? "gold" : "muted"}" href="/desk/nds-task-handover/${encodeURIComponent(v.name)}">
					v${v.version_no} · ${e(__(v.handover_status))}</a>`,
			);
			return `<div class="nds-card"><h5>${__("Versions")}</h5><div class="d-flex flex-wrap" style="gap:6px">${chips.join("")}</div></div>`;
		},
	});
})();

// New Handover dialog: pick the task and the receiver; the engine does the rest.
nds_operations.new_handover_dialog = function (task) {
	const dialog = new frappe.ui.Dialog({
		title: __("New Task Handover"),
		fields: [
			{ fieldtype: "Link", options: "Task", fieldname: "task", label: __("Task"), reqd: 1, default: task },
			{ fieldtype: "Link", options: "Employee", fieldname: "receiver_employee", label: __("Receiver"), reqd: 1,
				get_query: () => ({ filters: { status: "Active", user_id: ["is", "set"] } }) },
			{
				fieldtype: "Select",
				fieldname: "handover_reason",
				label: __("Reason"),
				reqd: 1,
				options: "Reassignment\nWorkload Balancing\nLeave or Absence\nDepartment Transfer\nSkill Match\nWork Completed\nEscalation\nOther",
			},
		],
		primary_action_label: __("Create Draft"),
		primary_action(values) {
			dialog.disable_primary_action();
			nds_operations
				.api("create_handover", {
					task: values.task,
					receiver_employee: values.receiver_employee,
					data: { handover_reason: values.handover_reason },
					client_request_id: dialog.request_id,
				})
				.then((r) => {
					dialog.hide();
					frappe.set_route("Form", "NDS Task Handover", r.name);
				})
				.catch(() => dialog.enable_primary_action());
		},
	});
	dialog.request_id = frappe.utils.get_random(16);
	dialog.show();
};
