# Frontend vs Backend Feature Review (Dec 11, 2025)

## Backend Feature Inventory
- **Authentication & Users** – Djoser JWT endpoints plus `/api/v1/users/` list/update + `me` shortcut (`config/api_router.py`, `hr_payroll/users/api/views.py`).
- **Employee lifecycle** – Registration wizard, nested updates, document CRUD, and document streaming (`hr_payroll/employees/api/views.py`).
- **Attendance tracking** – Full CRUD, manual entries, approvals, clock-out endpoint, personal summaries, and network/IP validation helpers (`hr_payroll/attendance/api/views.py`).
- **Leave management** – Leave types, policies, public holidays, balances, history, and employee-request workflow with scoped queryset logic (`hr_payroll/leaves/api/urls.py`, `views.py`).
- **Payroll domain** – Bank masters/details, salary components & structures, dependents, pay cycles, payroll slips, slip line items, and global payroll settings (`hr_payroll/payroll/api/views.py`).
- **Org structure** – Department CRUD, assign/unassign manager actions, and automatic line-manager group assignment (`hr_payroll/org/api/views.py`).
- **Notifications groundwork** – Channel layers, consumers, and `Notification` model exist (`hr_payroll/notifications/*`), but no REST endpoints are currently routed.

## Frontend Feature Inventory
- **Routing & Auth Guards** – Role-gated layouts for Payroll Officer, HR Manager, and Manager dashboards using `ProtectedRoutes` plus JWT login handling (`src/App.jsx`, `src/routes/Routes.jsx`, `src/Context/AuthContext.jsx`).
- **Employee management UI** – Directory filters, add-employee wizard, employee profile viewer/editor, document uploader, and nested detail tabs (`src/Pages/HR_Manager/Employee Management/*`).
- **Attendance UI suite** – HR attendance list/detail, employee self-attendance dashboard, manual correction form, and clock-in/out console with local IP/summary logic (`src/Pages/HR_Manager/Attendance/*`, `src/Pages/clockIn_out/*`).
- **Leave approval cockpit** – Request inbox, drawer detail view, approval/denial actions, lightweight analytics, and toast notifications (`src/Pages/HR_Manager/LeaveApproval/*`).
- **Payroll officer workspace** – Generate payroll table, salary structure editor, payslip drawers, deduction/allowance placeholders, and payroll reports (`src/Pages/Payroll_Officer/**`).
- **Organisation policy builder** – Multi-step policy editor feeding from `initialPolicies` mock data with deep field editing (`src/Pages/HR_Manager/Policy/*`).
- **Notifications UX** – Notification center, detail reader, send-notification form, and local store with role-based filters (`src/Pages/Notifications/*`).
- **Settings & Misc** – Company info, password, work schedule pages plus announcement boards and profile components (various files under `src/Pages/settings`, `src/Pages/HR_Manager/Announcement`, `src/Pages/profile`).

## Coverage Comparison

### Features implemented on both sides
- **Employee CRUD & documents** – Backend `EmployeeRegistrationViewSet` matches frontend add/edit/document flows; UI already calls `/employees/` (`src/Pages/HR_Manager/Employee Management/AddEmployee.jsx`, `ViewEmployeeDetail.jsx`).
- **Attendance basics** – Backend attendance endpoints exist, and frontend attendance pages are structured to consume `/attendances/` (currently mocked in `EmployeeAttendanceList.jsx`).
- **Payroll master data** – Backend salary components/structures/bank data exist; frontend Payroll Officer pages (`GeneratePayroll.jsx`, `SalaryStructure.jsx`, etc.) scaffold the UI even though most data is mocked.

### Frontend-only (no current backend support)
- **Notification center & sending** – Front uses `useNotificationStore` with mock data; backend exposes only a model, no REST/socket endpoints wired into `config/api_router.py`.
- **Org-wide policy builder** – UI edits `initialPolicies` covering attendance, overtime, disciplinary, etc., but backend only models leave policies; no unified policy API exists.
- **Real-time clock-in console** – `ClockIn.jsx` calls `/api/attendance/check` and `/api/attendance/today`, which are not defined server-side (backend only exposes `AttendanceViewSet` routes).
- **Payroll analytics dashboards** – Pages such as `DepartmentWisePayroll.jsx`, `PayrollReports.jsx`, `TaxReports.jsx` are purely UI placeholders with static data and no matching backend reports.

### Backend-only (not surfaced in UI)
- **Leave policy administration** – CRUD for leave types/policies/public holidays/balances is implemented server-side but no dedicated frontend management pages consume these endpoints (leave UI only handles approvals with mock data).
- **Payroll general settings & bank masters** – REST resources for payroll settings, bank master/detail, salary structure line items, dependents, and pay cycles are unrepresented in the current UI.
- **Attendance adjustments & IP whitelisting** – Endpoints for manual entries, adjustments, IP-bound office networks, and `my/summary` reporting have no frontend hooks.
- **Department manager assignment** – `/departments/:id/assign-manager` and `unassign-manager` endpoints exist without UI controls.
- **Notification websocket plumbing** – Django Channels consumer is defined but no frontend websocket client is wired up.

## Conflicting Implementations & Recommendations

| Feature | Conflict Description | Source Files | Recommended Alignment |
| --- | --- | --- | --- |
| Role/permission naming | Frontend guards expect roles `'Payroll'`, `'Manager'`, or empty string, stored via `localStorage`; backend permissions rely on Django groups `Admin`, `Manager`, `Line Manager`, and `is_staff` flags. | Front: `src/routes/Routes.jsx`, `src/Context/AuthContext.jsx`; Back: `hr_payroll/employees/api/permissions.py`, `hr_payroll/users/api/views.py`. | **Align frontend to backend** by mapping allowedRoles to actual Django group names (e.g., use `Admin`, `Manager`, `Line Manager`, or introduce a dedicated `Payroll` group server-side and reuse it consistently). Backend is authoritative for access control. |
| Attendance list schema | UI tables expect hydrated employee objects (`employee_name`, `employee_email`, nested `attendance_*` keys) and currently use mock data; backend `/attendances/` returns flat serializer with `employee` ID only. | Front: `src/Pages/HR_Manager/Attendance/EmployeeAttendanceList.jsx`, `Components/Table.jsx`; Back: `hr_payroll/attendance/api/serializers.py`. | **Prefer backend enhancement**: extend the serializer (or add select-related nested serializer) to include minimal employee info so the frontend can bind directly without extra fetches. This avoids per-row N+1 calls and keeps business logic server-side. |
| Notification workflow | Frontend offers read/send/delete flows powered by `useNotificationStore`; backend only defines `Notification` model and channels consumer without HTTP endpoints. | Front: `src/Pages/Notifications/*`; Back: `hr_payroll/notifications/*`, `config/api_router.py`. | **Backend should align with frontend** by exposing REST endpoints (list, mark read, send) and/or websocket feed so the existing UI can operate on live data. |
| Policy data model | UI edits a comprehensive multi-policy document (`initialPolicies`) while backend only handles leave policies (`LeavePolicy` etc.). | Front: `src/Pages/HR_Manager/Policy/*`; Back: `hr_payroll/leaves/models.py`. | **Decide scope**: either expand backend to persist the richer policy schema (recommended if policy builder is product requirement) or simplify the UI to just consume leave policies/public holidays. Given the UI investment, extending the backend offers better UX continuity. |
| Clock-in/out endpoints | Front calls `/api/attendance/check` & `/api/attendance/today`; backend lacks these routes and instead exposes `AttendanceViewSet` actions like `manual_entry`, `clock_out`, `my/summary`. | Front: `src/Pages/clockIn_out/ClockIn.jsx`, `useAttendanceToday.js`; Back: `hr_payroll/attendance/api/views.py`. | **Frontend should align with backend** by reusing existing attendance actions (`manual_entry`, `approve`, etc.) or backend should add the lightweight endpoints expected by the UI. Because backend already enforces IP rules and statuses, reusing/expanding current DRF actions is safer than introducing parallel ad-hoc endpoints. |

## Next Steps
1. Confirm which role names/groups the organization will standardize on and update `AuthContext` + protected route guards accordingly.
2. Prioritize API work for notifications and policy storage if those UIs must be functional, or downgrade/remove the UI until server support exists.
3. Decide whether to enrich attendance serializers (preferred) or update the frontend data model; implement the agreed approach before wiring live data into `Table` components.
4. Map backend-only capabilities (leave admin, payroll settings, department manager actions) to upcoming UI tasks so both surfaces stay in sync.
