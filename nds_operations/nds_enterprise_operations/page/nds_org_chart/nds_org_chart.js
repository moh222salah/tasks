frappe.pages["nds-org-chart"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Organization Chart"), single_column: true });
	wrapper.nds_org = new NDSOrgChart(page);
};
frappe.pages["nds-org-chart"].on_page_show = function (wrapper) {
	wrapper.nds_org && wrapper.nds_org.refresh();
};

class NDSOrgChart {
	constructor(page) {
		this.page = page;
		this.$body = $('<div class="nds-page nds-org"></div>').appendTo(page.main);
		page.add_menu_item(__("Refresh"), () => this.refresh());
	}
	refresh() {
		this.$body.html('<div class="nds-dashboard-loading">' + __("Loading organization…") + "</div>");
		frappe
			.call({ method: "nds_operations.api.organization.get_org_chart", type: "GET" })
			.then((r) => this.render((r.message || {}).departments || []))
			.catch(() =>
				this.$body.html('<div class="nds-dashboard-empty">' + __("The organization chart could not be loaded.") + "</div>")
			);
	}
	render(departments) {
		const e = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
		if (!departments.length) {
			this.$body.html('<div class="nds-dashboard-empty">' + __("No departments to show yet.") + "</div>");
			return;
		}
		const children = {};
		const known = new Set(departments.map((d) => d.name));
		departments.forEach((d) => {
			const parent = d.parent && known.has(d.parent) ? d.parent : "";
			(children[parent] = children[parent] || []).push(d);
		});
		const node = (d) => {
			const teams = d.teams
				.map(
					(t) =>
						'<div class="nds-org-team"><a href="/desk/nds-profile/team/' + encodeURIComponent(t.name) + '"><b>' + e(t.title) + "</b></a>" +
						'<span class="nds-org-meta">' + (t.lead ? e(t.lead) + " · " : "") + t.member_count + " " + __("members") + "</span>" +
						(t.members.length
							? '<div class="nds-org-members">' + t.members.map((m) => '<span><a href="/desk/nds-profile/employee/' + encodeURIComponent(m.employee) + '">' + e(m.name) + "</a></span>").join("") + (t.more ? "<span>+" + t.more + "</span>" : "") + "</div>"
							: "") +
						"</div>"
				)
				.join("");
			const kids = (children[d.name] || []).map(node).join("");
			return (
				'<details class="nds-org-dept" open><summary><b>' + e(d.title) + "</b>" +
				'<span class="nds-org-meta">' + (d.manager ? e(d.manager) + " · " : "") + d.open_tasks + " " + __("open tasks") + "</span></summary>" +
				teams + kids + "</details>"
			);
		};
		this.$body.html((children[""] || []).map(node).join(""));
	}
}
