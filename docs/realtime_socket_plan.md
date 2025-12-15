# Realtime Socket Plan

_Updated: Dec 12, 2025_

## Current Capabilities
- `Notification` model + post-save signal already emits websocket payloads to `user_<id>` groups via `ws/notifications/` (see `hr_payroll/notifications/consumers.py`).
- Any backend component can trigger realtime traffic by creating a `Notification` row—no additional socket plumbing is required.

## Required Usage Patterns
1. **Leave Request Escalation**
   - When an employee submits a leave request, persist a notification targeting their Line Manager group (or specific manager user) with type `leave_request` and a deep-link to the approval drawer.
   - When a manager approves/denies, create a new notification targeting the HR Manager (group `Manager`) so the second-level workflow receives the payload in realtime.
   - Once HR acts, send a final notification to the originating employee with the updated status so their UI updates immediately.

2. **Attendance Clock-In Updates**
   - After a successful clock-in/out, emit notifications for:
     - The employee (confirmation message)
     - HR dashboard listeners (tagged type `attendance`) so charts refresh without polling.
   - Include metadata (employee id, timestamp, action) in the notification payload; the frontend socket handler can decide which widgets to refresh.

3. **Generic Realtime Events**
   - Reuse the same pattern for any workflow that requires immediate visibility (e.g., approvals, payroll adjustments, announcements). Emit a notification with a descriptive `notification_type` and contextual `related_link`.

## Implementation Notes
- Wrap notification creation in helper utilities (e.g., `hr_payroll.notifications.services.dispatch_event`) so domain code (leave, attendance, payroll) only declares recipients + payloads.
- Continue using websocket groups keyed by user id. For broadcast scenarios ("all HR Managers"), iterate over users in the relevant Django Group and create per-user notifications to leverage existing delivery.
- Because the frontend socket layer already listens on `/ws/notifications/`, no frontend code changes are required; only the backend needs to create the relevant notifications when events occur.

## Frontend Note
- The clock-in UI should call `GET /api/v1/employees/<id>/attendances/network-status/` on load and disable the action button unless `is_office_network` is `true`.
