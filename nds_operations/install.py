import frappe

from nds_operations.constants import DEFAULT_REJECTION_REASONS, NDS_ROLES


def before_install():
	ensure_roles()


def before_migrate():
	# DocType permission rows reference these roles, so they must exist before the doctypes are synced
	ensure_roles()


def after_install():
	ensure_roles()
	seed_rejection_reasons()


def ensure_roles():
	"""Create the module roles when missing. Existing roles are never modified."""
	for role in NDS_ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)


def seed_rejection_reasons():
	"""Default rejection categories. Seeded once on install; afterwards they are normal editable records."""
	for reason_name, description in DEFAULT_REJECTION_REASONS:
		if not frappe.db.exists("NDS Rejection Reason", reason_name):
			frappe.get_doc(
				{
					"doctype": "NDS Rejection Reason",
					"reason_name": reason_name,
					"description": description,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)
