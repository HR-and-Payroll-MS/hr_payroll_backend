Attendance
======================================================================

Overview
----------------------------------------------------------------------
The Attendance module provides daily time records per employee with approval
status, administrative adjustments, and personal/team summaries.

Key concepts:
- Status: PRESENT (default), ABSENT, or PERMITTED
- Logged time: clock_out - clock_in (if clocked out)
- Paid time: effective payable duration (may be adjusted)
- Scheduled hours: expected daily hours used to compute overtime/deficit
- Overtime cache: denormalized seconds for reporting

Endpoints
----------------------------------------------------------------------
Base collection:
- GET/POST: ``/api/v1/attendances/``
- GET/PATCH/PUT/DELETE: ``/api/v1/attendances/{id}/``

Actions on a record:
- POST ``/api/v1/attendances/{id}/clock-out/``
  Body: {"clock_out": ISO-8601 datetime, "clock_out_location": "optional"}
- POST ``/api/v1/attendances/{id}/adjust-paid-time/`` (HR/Admin/Line Manager)
  Body: {"paid_time": "HH:MM:SS" | ISO 8601 duration, "notes": "optional"}
  Notes: Resets status to PERMITTED and records an adjustment audit row.
- POST ``/api/v1/attendances/{id}/approve/`` (HR/Admin/Line Manager)
  Body (optional): {"status": "PRESENT" | "ABSENT" | "PERMITTED" | ...}
- POST ``/api/v1/attendances/{id}/revoke-approval/`` (HR/Admin/Line Manager)
  Notes: Returns the record to PERMITTED.

Self-service punches (alternate flow exposed through the employee nested routes):
- GET ``/api/v1/employees/{employee_id}/attendances/today/`` — returns ``{"date": "YYYY-MM-DD", "attendance_id": nullable, "punches": [{"type": "check_in"|"check_out", "time": ISO8601, "location": str}]}``
  *Query parameter ``date`` (optional) defaults to the server's local date. The employee id comes from the nested path; non-elevated users are restricted to their own id.*
- POST ``/api/v1/employees/{employee_id}/attendances/check/`` — body ``{"action": "check_in"|"check_out", "location": "HQ kiosk", "date": "YYYY-MM-DD" (optional), "time": "HH:MM" (optional), "timestamp": ISO8601 (optional), "notes": "..."}``
  *Clock-ins reuse the existing office network restriction; managers/admins can bypass via their elevated role. Clock-outs finalize the open record for the requested date. Responses mirror the ``today`` payload so the frontend can refresh state without an extra call.*

Summaries:
- GET ``/api/v1/attendances/my/summary`` — aggregate my records in a date range
  Query: start_date, end_date, status
- GET ``/api/v1/attendances/team/summary`` — aggregate team/all (scoped)
  Query: start_date, end_date, status, office (icontains)

Filters on collection
----------------------------------------------------------------------
Query parameters on ``/api/v1/attendances/``:
- ``employee``: employee UUID
- ``date``: YYYY-MM-DD
- ``start_date`` / ``end_date``: inclusive range
- ``status``: PRESENT | ABSENT | PERMITTED
- ``location``: icontains on clock-in/out location
- ``office``: icontains on employee office

Computed fields
----------------------------------------------------------------------
Read-most fields on the serializer:
- ``logged_time``: formatted duration if clocked out (e.g., "+08:30:00")
- ``deficit``: formatted difference (scheduled - paid), signed
- ``overtime``: formatted difference (paid - scheduled), signed
- ``overtime_seconds``: denormalized int seconds (for reporting)

RBAC & scoping
----------------------------------------------------------------------
- Regular employees: can only view and modify their own records; may clock-out
  only their own record
- Line Managers: scoped access to direct reports; may approve/revoke/adjust
- HR/Admin: full access across the organization

Celery task (overtime cache)
----------------------------------------------------------------------
A daily task computes ``overtime_seconds`` for records of a given date (default:
yesterday). Schedule with django-celery-beat if desired.

OpenAPI tags
----------------------------------------------------------------------
Endpoints appear under two groups in Swagger UI:
- "Attendance • Records": CRUD and per-record actions
- "Attendance • Summaries": my/summary and team/summary
