import frappe

from nds_operations.utils.immutable import ImmutableRecord


class NDSOwnershipHistory(ImmutableRecord):
	pass


def on_doctype_update():
	# One ledger row per (task, sequence): a database-level guard against two transfers racing
	# for the same position, in addition to the row locks taken by the handover engine.
	frappe.db.add_unique("NDS Ownership History", ["task", "sequence"], constraint_name="unique_task_sequence")
