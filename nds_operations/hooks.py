app_name = "nds_operations"
app_title = "NDS Operations"
app_publisher = "NDS"
app_description = "NDS Enterprise Teams & Operations Management"
app_email = "dev@example.com"
app_license = "mit"

# Apps
# ------------------

required_apps = ["erpnext"]

add_to_apps_screen = [
	{
		"name": "nds_operations",
		"logo": "/assets/nds_operations/images/nds-operations.svg",
		"title": "NDS Operations",
		"route": "/desk/nds-enterprise-operations",
		"has_permission": "nds_operations.permissions.has_app_permission",
		"sequence_id": 30,
	}
]

# Installation
# ------------

before_install = "nds_operations.install.before_install"
after_install = "nds_operations.install.after_install"
before_migrate = "nds_operations.install.before_migrate"

# Permissions
# -----------
# Row-level scoping is enforced on the server. The Administrator bypasses has_permission hooks in
# Frappe, so immutability of approved records is additionally enforced in the controllers.

permission_query_conditions = {
	"NDS Task Handover": "nds_operations.permissions.handover_query_conditions",
	"NDS Handover Review": "nds_operations.permissions.review_query_conditions",
	"NDS Handover History": "nds_operations.permissions.history_query_conditions",
	"NDS Ownership History": "nds_operations.permissions.ownership_query_conditions",
}

has_permission = {
	"NDS Task Handover": "nds_operations.permissions.handover_has_permission",
	"NDS Handover Review": "nds_operations.permissions.record_has_permission",
	"NDS Handover History": "nds_operations.permissions.record_has_permission",
	"NDS Ownership History": "nds_operations.permissions.ownership_has_permission",
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"nds_operations.nds_enterprise_operations.doctype.nds_team_membership.nds_team_membership.refresh_membership_status",
	],
}
