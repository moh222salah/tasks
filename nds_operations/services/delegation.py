"""Delegation: a receiver explicitly lets another user decide the handovers addressed to him.

A delegation is never implied. It is valid only inside its dates, only until revoked, and never lets the
sender of a handover decide it.
"""

import frappe
from frappe.utils import getdate, nowdate

from nds_operations.constants import DELEGATION


def _active_filters(on=None):
	today = getdate(on or nowdate())
	return {"is_revoked": 0, "valid_from": ("<=", today), "valid_to": (">=", today)}


def get_active_delegation(delegator, delegate, on=None):
	"""Name of the live delegation from `delegator` to `delegate`, or None."""
	if not delegator or not delegate or delegator == delegate:
		return None
	rows = frappe.get_all(
		DELEGATION,
		filters={"delegator": delegator, "delegate": delegate, **_active_filters(on)},
		pluck="name",
		order_by="creation desc",
		limit=1,
	)
	return rows[0] if rows else None


def get_delegators(delegate, on=None):
	"""Users whose handovers `delegate` may currently decide."""
	if not delegate:
		return []
	return frappe.get_all(
		DELEGATION,
		filters={"delegate": delegate, **_active_filters(on)},
		pluck="delegator",
		distinct=True,
	)
