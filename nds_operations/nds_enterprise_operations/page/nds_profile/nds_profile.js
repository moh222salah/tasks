frappe.pages["nds-profile"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Profile"), single_column: true });
	wrapper.nds_profile = new NDSProfile(page);
};
frappe.pages["nds-profile"].on_page_show = function (wrapper) {
	wrapper.nds_profile && wrapper.nds_profile.refresh();
};

class NDSProfile {
	constructor(page) {
		this.page = page;
		this.$body = $('<div class="nds-page nds-profile"></div>').appendTo(page.main);
		page.add_menu_item(__("Refresh"), () => this.refresh());
	}
	refresh() {
		// routes: /desk/nds-profile (me), /desk/nds-profile/employee/<id>, /desk/nds-profile/team/<id>
		const route = frappe.get_route();
		const kind = route[1] === "team" ? "team" : "employee";
		const id = route[2] ? decodeURIComponent(route.slice(2).join("/")) : null;
		this.$body.html('<div class="nds-dashboard-loading">' + __("Loading profile…") + "</div>");
		frappe
			.call({
				method: "nds_operations.api.profile.get_" + kind + "_profile",
				type: "GET",
				args: kind === "team" ? { team: id } : { employee: id },
			})
			.then((r) => (kind === "team" ? this.render_team(r.message) : this.render_employee(r.message)))
			.catch(() => this.$body.html('<div class="nds-dashboard-empty">' + __("This profile could not be opened.") + "</div>"));
	}
	e(v) {
		return frappe.utils.escape_html(v == null ? "" : String(v));
	}
	rate(v) {
		return v == null ? "—" : this.e(v) + "%";
	}
	val(v, unit) {
		return v == null ? "—" : this.e(v) + (unit || "");
	}
	tile(label, value, tone) {
		return '<div class="nds-prof-tile ' + (tone || "") + '"><strong>' + value + "</strong><span>" + this.e(label) + "</span></div>";
	}
	render_employee(d) {
		const e = (v) => this.e(v);
		const emp = d.employee;
		this.page.set_title(emp.employee_name);
		const s = d.stats;
		const teams = (d.teams || [])
			.map((t) => '<a class="nds-chip" href="/desk/nds-profile/team/' + encodeURIComponent(t.team) + '">' + e(t.title) + " · " + e(t.role) + "</a>")
			.join("");
		const head =
			'<div class="nds-prof-head"><div><h3>' + e(emp.employee_name) + "</h3><div class=\"nds-org-meta\">" +
			[emp.designation, emp.department, d.manager ? __("Reports to") + " " + d.manager : ""].filter(Boolean).map(e).join(" · ") +
			"</div><div class=\"nds-prof-chips\">" + (teams || '<span class="nds-org-meta">' + __("Not in any team") + "</span>") + "</div></div></div>";
		if (!s) {
			this.$body.html(head + '<div class="nds-dashboard-empty">' + __("This employee has no linked user, so there are no task figures yet.") + "</div>");
			return;
		}
		const tiles =
			this.tile(__("Open tasks"), s.open_tasks) +
			this.tile(__("Overdue"), s.overdue_tasks, s.overdue_tasks ? "bad" : "") +
			this.tile(__("Waiting on handover"), s.waiting_on_handover) +
			this.tile(__("Completed"), s.completed_tasks, "ok") +
			this.tile(__("On-time rate"), this.rate(s.on_time_rate)) +
			this.tile(__("Avg cycle (days)"), this.val(s.avg_cycle_days)) +
			this.tile(__("Handovers sent"), s.handovers_sent) +
			this.tile(__("Awaiting my decision"), s.handovers_pending_decision, s.handovers_pending_decision ? "warn" : "") +
			this.tile(__("First-pass rate"), this.rate(s.first_pass_rate)) +
			this.tile(__("Rejection rate"), this.rate(s.rejection_rate)) +
			this.tile(__("Handover quality"), this.val(s.quality_score)) +
			this.tile(__("Quality review (1-5)"), this.val(s.review_score));
		const tasks = d.tasks.length
			? '<table class="nds-prof-table"><tbody>' +
			  d.tasks
					.map(
						(t) =>
							'<tr><td><a href="/desk/task/' + encodeURIComponent(t.name) + '">' + e(t.name) + "</a></td><td>" + e(t.subject) + "</td><td>" +
							(t.due ? frappe.datetime.str_to_user(t.due) : "—") + "</td><td>" +
							(t.overdue ? '<span class="indicator-pill red">' + __("Overdue") + "</span>" : t.waiting ? '<span class="indicator-pill orange">' + __("Handover pending") + "</span>" : e(t.status)) + "</td></tr>"
					)
					.join("") + "</tbody></table>"
			: '<div class="nds-dashboard-empty">' + __("No open tasks.") + "</div>";
		const hos = d.handovers.length
			? '<table class="nds-prof-table"><tbody>' +
			  d.handovers
					.map(
						(h) =>
							'<tr><td><a href="/desk/nds-task-handover/' + encodeURIComponent(h.name) + '">' + e(h.name) + "</a></td><td>" + e(h.sender_user) + " → " + e(h.receiver_user) + "</td><td>" + e(h.handover_status) + "</td></tr>"
					)
					.join("") + "</tbody></table>"
			: '<div class="nds-dashboard-empty">' + __("No handovers yet.") + "</div>";
		this.$body.html(
			head + '<div class="nds-prof-tiles">' + tiles + "</div>" +
				'<div class="nds-panels"><div class="nds-card"><h5>' + __("Open tasks") + "</h5>" + tasks + '</div><div class="nds-card"><h5>' + __("Recent handovers") + "</h5>" + hos + "</div></div>" +
				'<p class="nds-org-meta">' + __("Overdue does not count tasks waiting on a receiver. Rates with nothing to divide by stay empty. Figures cover only records you may read.") + "</p>"
		);
	}
	render_team(d) {
		const e = (v) => this.e(v);
		this.page.set_title(d.team.team_name);
		const h = d.handovers,
			t = d.totals;
		const tiles =
			this.tile(__("Members"), d.members.length) +
			this.tile(__("Open tasks"), t.open_tasks) +
			this.tile(__("Overdue"), t.overdue_tasks, t.overdue_tasks ? "bad" : "") +
			this.tile(__("Completed"), t.completed_tasks, "ok") +
			this.tile(__("Avg open per member"), this.val(t.average_open_per_member)) +
			this.tile(__("Handovers sent"), h.sent) +
			this.tile(__("Waiting to decide"), h.pending_decision, h.pending_decision ? "warn" : "") +
			this.tile(__("First-pass rate"), this.rate(h.first_pass_rate)) +
			this.tile(__("Rejection rate"), this.rate(h.rejection_rate)) +
			this.tile(__("Handover quality"), this.val(h.quality_score)) +
			this.tile(__("Avg response (h)"), this.val(h.avg_response_hours));
		const mx = Math.max(1, ...d.members.map((m) => m.open_tasks || 0));
		const rows = d.members.length
			? d.members
					.map(
						(m) =>
							'<div class="nds-prof-bar"><a href="/desk/nds-profile/employee/' + encodeURIComponent(m.employee) + '">' + e(m.name) + "</a><span>" + e(m.role || "") +
							'</span><span class="nds-prof-track"><i class="' + (m.heavy ? "heavy" : "") + '" style="width:' + Math.round((100 * (m.open_tasks || 0)) / mx) + '%"></i></span><b>' +
							(m.open_tasks == null ? "—" : m.open_tasks) + (m.heavy ? ' <span class="indicator-pill red">' + __("Heavy load") + "</span>" : "") + "</b></div>"
					)
					.join("")
			: '<div class="nds-dashboard-empty">' + __("This team has no active members.") + "</div>";
		this.$body.html(
			'<div class="nds-prof-head"><div><h3>' + e(d.team.team_name) + '</h3><div class="nds-org-meta">' + e(d.team.department || "") + (d.team.team_lead_name ? " · " + __("Lead") + " " + e(d.team.team_lead_name) : "") +
				' · <a href="/desk/nds-team/' + encodeURIComponent(d.team.name) + '">' + __("Open team record") + "</a></div></div></div>" +
				'<div class="nds-prof-tiles">' + tiles + "</div>" +
				'<div class="nds-card"><h5>' + __("Workload by member") + "</h5>" + rows + "</div>" +
				'<p class="nds-org-meta">' + __("Heavy load means at least 3 open tasks and clearly above the team average. Delays caused by a receiver are not counted against the owner.") + "</p>"
		);
	}
}
