"""Real-time event constants.

This module acts as a single source of truth for event names shared between
backend signals and frontend listeners.
"""

# Generic Systems
EVENT_CONNECT = "connect"
EVENT_DISCONNECT = "disconnect"
EVENT_NOTIFICATION = "notification"  # Generic toast/bell notification
EVENT_ERROR = "error"

# Chat
EVENT_CHAT_MESSAGE = "chat_message"
EVENT_CHAT_TYPING = "chat_typing"
EVENT_CHAT_READ_RECEIPT = "chat_read_receipt"

# Attendance
EVENT_ATTENDANCE_UPDATE = "attendance_update"  # Dashboard table refresh

# --- Requests (Leaves, Loans, Expenses) ---
EVENT_REQUEST_CREATED = "request_created"  # To approvers
EVENT_REQUEST_UPDATE = "request_update"  # To requester (status change)

# Payroll
EVENT_PAYROLL_PROGRESS = "payroll_progress"

# Announcements
EVENT_ANNOUNCEMENT_PUBLISHED = "announcement_published"

# Entity Updates (Generic data refresh triggers)
EVENT_ENTITY_UPDATE = "entity_update"
