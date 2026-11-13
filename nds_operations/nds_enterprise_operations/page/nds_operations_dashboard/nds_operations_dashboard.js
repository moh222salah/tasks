frappe.pages["nds-operations-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Operations Overview"), single_column: true });
	wrapper.nds_dashboard = new NDSOperationsDashboard(page);
};
frappe.pages["nds-operations-dashboard"].on_page_show = function (wrapper) {
	wrapper.nds_dashboard && wrapper.nds_dashboard.refresh();
};

class NDSOperationsDashboard {
	constructor(page) {
		this.page = page;
		this.$body = $('<div class="nds-page nds-dashboard"><div class="nds-dashboard-loading">' + __("Loading operational overview…") + '</div></div>').appendTo(page.main);
		page.set_primary_action(__("Open Handover Center"), () => frappe.set_route("nds-handover-center"), "arrow-right");
		page.add_menu_item(__("Refresh"), () => this.refresh());
	}
	refresh() {
		this.$body.html('<div class="nds-dashboard-loading">' + __("Refreshing operational data…") + '</div>');
		frappe.call({ method: "nds_operations.api.operations.get_dashboard", type: "GET" })
			.then((response) => this.render(response.message || {}))
			.catch(() => this.$body.html('<div class="nds-dashboard-empty">' + __("The dashboard could not be loaded. Check your NDS Operations permissions and try again.") + '</div>'));
	}
	render(data) {
		const e = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
		const k = data.kpis || {};
		const cards = [
			["total_submitted", __("Submitted handovers"), "layers", "navy"],
			["pending_acceptance", __("Pending acceptance"), "inbox", "amber"],
			["under_review", __("Under review"), "eye", "blue"],
			["overdue", __("Overdue responses"), "clock-o", "red"],
			["accepted", __("Accepted"), "check-circle", "green"],
			["rejected", __("Rejected"), "times-circle", "slate"],
		];
		const counts = data.status_counts || {};
		const maxStatus = Math.max(1, ...Object.values(counts).map(Number));
		const labels = {
			"Pending Acceptance": __("Pending Acceptance"), "Under Review": __("Under Review"),
			"Clarification Requested": __("Clarification Requested"), Accepted: __("Accepted"),
			Rejected: __("Rejected"), Withdrawn: __("Withdrawn"),
		};
		const statusRows = Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([name, count]) => {
			const width = Math.max(2, Number(count) / maxStatus * 100);
			return '<div class="nds-dash-bar-row"><div class="nds-dash-bar-label">' + e(labels[name] || name) +
				'</div><div class="nds-dash-bar-track"><span style="width:' + width + '%"></span></div><b>' + Number(count) + '</b></div>';
		}).join("") || '<div class="nds-dashboard-empty">' + __("No submitted handovers are visible in your scope yet.") + '</div>';
		const departmentRows = (data.departments || []).map((row) =>
			'<div class="nds-dash-dept"><span>' + e(row.receiver_department || __("Unassigned")) +
			'</span><b>' + Number(row.total || 0) + '</b></div>').join("") ||
			'<div class="nds-dashboard-empty">' + __("Department activity will appear here when handovers are recorded.") + '</div>';
		const recentRows = (data.recent || []).map((row) =>
			'<button class="nds-dash-recent" data-name="' + e(row.name) + '"><span class="nds-dash-recent-main"><b>' +
			e(row.task_title || row.task || row.name) + '</b><small>' + e(row.name) + ' · ' + e(row.sender_name) +
			' → ' + e(row.receiver_name) + '</small></span><span class="nds-pill">' +
			e(__(row.handover_status)) + '</span></button>').join("") ||
			'<div class="nds-dashboard-empty">' + __("No recent handovers.") + '</div>';
		const kpiHtml = cards.map(([key, label, icon, tone]) =>
			'<div class="nds-dash-kpi ' + tone + '"><div class="nds-dash-kpi-top"><span>' + e(label) +
			'</span><i class="fa fa-' + icon + '"></i></div><strong>' +
			(k[key] == null ? "—" : Number(k[key]).toLocaleString()) + '</strong></div>').join("");
		const rate = k.decision_acceptance_rate == null ? "—" : Number(k.decision_acceptance_rate).toFixed(1) + "%";
		this.$body.html(
			'<header class="nds-dash-header"><div><div class="nds-dash-eyebrow">NDS ENTERPRISE OPERATIONS</div><h2>' +
			__("Operations Overview") + '</h2><p>' + __("A live view of handovers and responsibility flow visible to your account.") +
			'</p></div><div class="nds-dash-header-actions"><span class="nds-dash-scope">' +
			__("Permission-scoped data") + '</span><button class="btn btn-default btn-sm nds-dash-refresh">' +
			__("Refresh") + '</button></div></header><section class="nds-dash-kpis">' + kpiHtml +
			'</section><section class="nds-dash-insight-grid"><div class="nds-dash-panel"><div class="nds-dash-panel-head"><h4>' +
			__("Handover Status") + '</h4><span>' + __("Submitted records") + '</span></div>' + statusRows +
			'</div><div class="nds-dash-panel"><div class="nds-dash-panel-head"><h4>' + __("Department Activity") +
			'</h4><span>' + __("By receiving department") + '</span></div>' + departmentRows +
			'<div class="nds-dash-acceptance"><span>' + __("Decision acceptance rate") + '</span><b>' + rate +
			'</b><small>' + __("Accepted ÷ (accepted + rejected)") + '</small></div></div></section>' +
			'<section class="nds-dash-panel nds-dash-recent-panel"><div class="nds-dash-panel-head"><h4>' +
			__("Recent Handover Activity") + '</h4><a href="/app/nds-handover-center">' + __("View all") +
			'</a></div>' + recentRows + '</section><footer class="nds-dash-footer">' + __("Updated") + ': ' +
			e(data.generated_at || "") + ' · ' + __("Figures reflect records your account is allowed to read.") + '</footer>'
		);
		this.$body.find(".nds-dash-refresh").on("click", () => this.refresh());
		this.$body.find(".nds-dash-recent").on("click", (event) =>
			frappe.set_route("Form", "NDS Task Handover", $(event.currentTarget).attr("data-name")));
	}
}
