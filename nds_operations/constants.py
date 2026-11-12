"""Shared names used across the module (roles, doctypes, statuses)."""

ROLE_EXECUTIVE = "NDS Executive Management"
ROLE_OPS_MANAGER = "NDS Operations Manager"
ROLE_DEPT_MANAGER = "NDS Department Manager"
ROLE_TEAM_LEADER = "NDS Team Leader"
ROLE_PROJECT_MANAGER = "NDS Project Manager"
ROLE_SENDER = "NDS Task Sender"
ROLE_EXECUTOR = "NDS Task Executor"
ROLE_RECEIVER = "NDS Task Receiver"
ROLE_REVIEWER = "NDS Task Reviewer"
ROLE_AUDITOR = "NDS Read Only Auditor"

NDS_ROLES = (
	ROLE_EXECUTIVE,
	ROLE_OPS_MANAGER,
	ROLE_DEPT_MANAGER,
	ROLE_TEAM_LEADER,
	ROLE_PROJECT_MANAGER,
	ROLE_SENDER,
	ROLE_EXECUTOR,
	ROLE_RECEIVER,
	ROLE_REVIEWER,
	ROLE_AUDITOR,
)

HANDOVER = "NDS Task Handover"
HANDOVER_REVIEW = "NDS Handover Review"
HANDOVER_HISTORY = "NDS Handover History"
OWNERSHIP_HISTORY = "NDS Ownership History"
TEAM = "NDS Team"
TEAM_MEMBERSHIP = "NDS Team Membership"
DEPARTMENT_PROFILE = "NDS Department Profile"
SETTINGS = "NDS Operations Settings"

# Handover statuses (execution status stays on the ERPNext Task; this is the handover dimension only)
DRAFT = "Draft"
READY = "Ready for Handover"
PENDING = "Pending Acceptance"
UNDER_REVIEW = "Under Review"
CLARIFICATION = "Clarification Requested"
ACCEPTED = "Accepted"
REJECTED = "Rejected"
WITHDRAWN = "Withdrawn"

# States where a handover is still open (blocks another handover on the same task)
OPEN_STATUSES = (PENDING, UNDER_REVIEW, CLARIFICATION)
# States where the receiver may still decide
DECIDABLE_STATUSES = (PENDING, UNDER_REVIEW)
TERMINAL_STATUSES = (ACCEPTED, REJECTED, WITHDRAWN)

DEFAULT_REJECTION_REASONS = (
	("Missing Information", "Information needed to continue the work is missing."),
	("Incomplete Work", "The work described as done is not complete."),
	("Missing Attachments", "Required files, screenshots or links are missing."),
	("Technical Issues", "Technical problems prevent accepting the work."),
	("Incorrect Diagnosis", "The technical diagnosis does not match what was found."),
	("Unclear Instructions", "The instructions or next steps are not clear."),
	("Unverified Results", "The reported results are not backed by evidence or testing."),
	("Wrong Assignment", "The task was handed to the wrong person, team or department."),
	("Other", "Any other reason; details are mandatory."),
)
