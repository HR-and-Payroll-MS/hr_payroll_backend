# Backend-only policy items (not in frontend `initialPolicies`)

This list is meant to help the frontend team decide what should become part of the shared organization policy document.

## Payroll (backend-only)
- `PayrollGeneralSetting.proration_policy` ("fixed_day" | "actual_days")
- `PayrollGeneralSetting.working_days_basis` (standard working days per month)

## Attendance (backend-only)
- Attendance edit window (`ATTENDANCE_EDIT_WINDOW_DAYS` in settings; controls how far back adjustments are allowed)
- Office network allowlist (CIDR-based IP restrictions for certain self-service attendance actions)

## Notes
- Frontend currently models policies in `hr_payroll_front/src/Pages/HR_Manager/Policy/policiesSchema.js` (`initialPolicies`).
- Backend now exposes `GET /api/v1/orgs/{org_id}/policies/` and `PUT /api/v1/orgs/{org_id}/policies/{section}/` so the frontend can later fetch/save policy sections.
