frappe.pages["nds-handover-center"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Handover Center"),
		single_column: true,
	});
	wrapper.nds_center = new NDSHandoverCenter(page, wrapper);
};

frappe.pages["nds-handover-center"].on_page_show = function (wrapper) {
	wrapper.nds_center?.refresh();
};

class NDSHandoverCenter {
	constructor(page, wrapper) {
		this.page = page;
		this.state = { tab: "inbox", status: "", search: "", page: 1, page_size: 20 };
		this.tabs = [
			{ key: "inbox", label: __("Inbox"), badge: "inbox_pending" },
			{ key: "outbox", label: __("Sent"), badge: "outbox_open" },
			{ key: "attention", label: __("Needs My Action"), badge: "needs_my_action" },
			{ key: "drafts", label: __("Drafts"), badge: "drafts" },
		];
		page.set_primary_action(__("New Handover"), () => nds_operations.new_handover_dialog(), "add");
		$(wrapper).find(".layout-main-section").addClass("nds-page nds-center");
		this.body = $(`<div class="nds-center-body"></div>`).appendTo(page.main);
		this.render_shell();
		const debounced = frappe.utils.debounce((value) => {
			this.state.search = value;
			this.state.page = 1;
			this.load();
		}, 300);
		this.search_input.on("input", (e) => debounced(e.target.value));
		this.status_select.on("change", (e) => {
			this.state.status = e.target.value;
			this.state.page = 1;
			this.load();
		});
	}

	render_shell() {
		this.body.html(`
			<div class="nds-tabs"></div>
			<div class="nds-toolbar">
				<input type="search" class="form-control input-sm nds-search" placeholder="${__("Search task, person or reference")}">
				<select class="form-control input-sm nds-status">
					<option value="">${__("All statuses")}</option>
					${["Pending Acceptance", "Under Review", "Clarification Requested", "Accepted", "Rejected", "Withdrawn"]
						.map((s) => `<option value="${s}">${__(s)}</option>`)
						.join("")}
				</select>
			</div>
			<div class="nds-list"></div>
			<div class="nds-pager"></div>`);
		this.search_input = this.body.find(".nds-search");
		this.status_select = this.body.find(".nds-status");
		this.list = this.body.find(".nds-list");
		this.pager = this.body.find(".nds-pager");
		this.tabs_el = this.body.find(".nds-tabs");
	}

	refresh() {
		nds_operations.api("get_counts").then((counts) => {
			this.counts = counts;
			this.render_tabs();
		});
		this.load();
	}

	render_tabs() {
		this.tabs_el.html(
			this.tabs
				.map((t) => {
					const n = this.counts ? this.counts[t.badge] : 0;
					return `<button class="nds-tab ${t.key === this.state.tab ? "active" : ""}" data-tab="${t.key}">
						${t.label}${n ? `<span class="count">${n}</span>` : ""}</button>`;
				})
				.join(""),
		);
		this.tabs_el.find(".nds-tab").on("click", (e) => {
			this.state.tab = $(e.currentTarget).data("tab");
			this.state.page = 1;
			this.render_tabs();
			this.load();
		});
	}

	load() {
		const { tab, status, search } = this.state;
		const method = tab === "inbox" ? "get_inbox" : "get_outbox";
		const view = { outbox: "sent", attention: "attention", drafts: "drafts" }[tab];
		const args = { status, search, page: this.state.page, page_size: this.state.page_size };
		if (view) args.view = view;
		this.list.css("opacity", 0.5);
		nds_operations.api(method, args).then((res) => {
			this.list.css("opacity", 1);
			this.render_rows(res.rows);
			this.render_pager(res);
		});
	}

	row_class(r) {
		const overdue =
			["Pending Acceptance", "Under Review"].includes(r.handover_status) &&
			r.response_due &&
			frappe.datetime.get_diff(frappe.datetime.now_datetime(), r.response_due) > 0;
		if (overdue) return "overdue";
		if (r.handover_status === "Accepted") return "ok";
		if (["Under Review", "Ready for Handover"].includes(r.handover_status)) return "gold";
		return "";
	}

	render_rows(rows) {
		const e = nds_operations.e;
		if (!rows.length) {
			this.list.html(`<div class="nds-empty">${__("Nothing here yet.")}</div>`);
			return;
		}
		this.list.html(
			rows
				.map(
					(r) => `<div class="nds-row ${this.row_class(r)}" data-name="${e(r.name)}">
						<div>
							<div class="title">${e(r.task_title)}</div>
							<div class="meta">${e(r.name)} · ${e(r.task)} · v${r.version_no}</div>
							<div class="meta">${e(r.sender_name)} → ${e(r.receiver_name)}
								${r.sender_department !== r.receiver_department ? ` · ${e(r.sender_department || "")} → ${e(r.receiver_department || "")}` : ""}</div>
						</div>
						<div class="text-end">
							${nds_operations.status_pill(r.handover_status)}
							<div class="meta">${r.response_due && r.docstatus === 1 ? `${__("Reply by")} ${frappe.datetime.str_to_user(r.response_due)}` : frappe.datetime.str_to_user(r.modified)}</div>
						</div>
					</div>`,
				)
				.join(""),
		);
		this.list.find(".nds-row").on("click", (ev) =>
			frappe.set_route("Form", "NDS Task Handover", $(ev.currentTarget).data("name")),
		);
	}

	render_pager(res) {
		const pages = Math.max(Math.ceil(res.total / res.page_size), 1);
		this.pager.html(`
			<span>${res.total} ${__("handovers")}</span>
			<span>
				<button class="btn btn-xs btn-default prev" ${res.page <= 1 ? "disabled" : ""}>${__("Previous")}</button>
				${res.page} / ${pages}
				<button class="btn btn-xs btn-default next" ${res.page >= pages ? "disabled" : ""}>${__("Next")}</button>
			</span>`);
		this.pager.find(".prev").on("click", () => { this.state.page -= 1; this.load(); });
		this.pager.find(".next").on("click", () => { this.state.page += 1; this.load(); });
	}
}
