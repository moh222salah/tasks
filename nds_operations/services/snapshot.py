"""Frozen copy of what the sender submitted, plus its SHA-256, so the approved record can be verified later."""

import datetime
import hashlib
import json
from decimal import Decimal

import frappe
from frappe.model import no_value_fields

from nds_operations.constants import HANDOVER

# Fields the engine changes after submission (decision, transfer, links); everything else is frozen.
MUTABLE_AFTER_SUBMIT = {
	"handover_status",
	"superseded_by",
	"received_at",
	"received_by",
	"decided_at",
	"decided_by",
	"latest_review",
	"rejection_reason",
	"withdrawn_at",
	"withdraw_reason",
	"new_owner",
	"responsibility_transferred_at",
	"new_department",
	"new_team",
	"snapshot_hash",
	"submission_snapshot",
}
ATTACHMENT_KEYS = ("attachment_type", "title", "file", "url", "description")


def _norm(value):
	if value in (None, ""):
		return None
	if isinstance(value, datetime.datetime):
		return value.strftime("%Y-%m-%d %H:%M:%S.%f")
	if isinstance(value, datetime.date):
		return value.isoformat()
	if isinstance(value, Decimal):
		return str(value)
	if isinstance(value, datetime.timedelta | datetime.time):
		return str(value)
	return value


def build_snapshot(doc):
	"""Return (json_text, sha256_hex) for the handover as it stands."""
	fields = {}
	for df in frappe.get_meta(HANDOVER).fields:
		if df.fieldtype in no_value_fields or df.fieldname in MUTABLE_AFTER_SUBMIT:
			continue
		fields[df.fieldname] = _norm(doc.get(df.fieldname))

	attachments = []
	for row in doc.get("attachments") or []:
		item = {key: _norm(row.get(key)) for key in ATTACHMENT_KEYS}
		item["file_hash"] = (
			frappe.db.get_value(
				"File",
				{"file_url": row.file, "attached_to_doctype": HANDOVER, "attached_to_name": doc.name},
				"content_hash",
			)
			if row.file
			else None
		)
		attachments.append(item)

	text = json.dumps(
		{"handover": doc.name, "fields": fields, "attachments": attachments},
		sort_keys=True,
		ensure_ascii=False,
		separators=(",", ":"),
	)
	return text, hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_snapshot(name):
	"""True when the stored record still matches the hash taken at submission."""
	doc = frappe.get_doc(HANDOVER, name)
	if doc.docstatus != 1 or not doc.snapshot_hash:
		return None
	return build_snapshot(doc)[1] == doc.snapshot_hash
