Authentication and RBAC
======================================================================

Authentication Backends
----------------------------------------------------------------------

- Session (SSR): django-allauth under ``/accounts/``
- Session API (dj-rest-auth): login/logout & password change/reset endpoints
- JWT (Djoser + SimpleJWT): token create/refresh/verify
- User Management (Djoser): user CRUD, activation, username/password flows

OpenAPI Tag Groups
----------------------------------------------------------------------
``Authentication``
  - ``POST /api/v1/auth/jwt/create/``
  - ``POST /api/v1/auth/jwt/refresh/``
  - ``POST /api/v1/auth/jwt/verify/``
``Session Auth``
  - ``POST /api/v1/auth/login/``
  - ``POST /api/v1/auth/logout/``
  - ``POST /api/v1/auth/password/change/`` (self)
  - ``POST /api/v1/auth/password/reset/``
  - ``POST /api/v1/auth/password/reset/confirm/``
``User Management``
  - ``/api/v1/auth/users/`` CRUD (Manager/Admin except self via ``/users/me``)
  - ``/api/v1/auth/users/me/`` (self read/update/delete if allowed)
  - Activation + resend (Manager/Admin)
  - Set/reset username (Manager/Admin)
  - Set password (self)
  - Reset password (Manager/Admin initiate)

Permission Model Adjustments
----------------------------------------------------------------------
- Regular employees: manage only their own password (set_password / password change) and profile.
- Managers/Admin: can perform onboarding, activation-related tasks, username changes, password resets for users.
- All other sensitive account recovery endpoints are restricted.

API Access Scoping
----------------------------------------------------------------------
- Employees: Non-elevated users only see their own Employee record; Line Managers see direct reports; HR/Admin see all.
- Attendance: Same scoping rules as Employees; per-record actions are restricted to HR/Admin/Line Managers.

Registration Policy
----------------------------------------------------------------------

- Public self-registration is disabled.
- Only Admins/Managers may create users.
- Activation emails are disabled; new users created by Admin/Manager are active immediately.
- “Onboarding” is the recommended flow to create a User and their Employee in a single step (see Employees page).

RBAC Summary (domain-specific)
----------------------------------------------------------------------
- Employees: Non-elevated users only see their own; elevated roles have broader access.
- Employee Documents/Contracts/Job Histories: same scoping as Employees.
- Payroll: reads for authenticated users; writes restricted to Admin by default.
- Attendance: non-elevated users manage only their own records; approvals/adjustments restricted to Line Managers and HR/Admin.

Groups & Permissions
----------------------------------------------------------------------

Seeded via ``python manage.py setup_rbac``

- Admin: full permissions
- Manager: elevated permissions for HR operations
- Employee: standard limited access

Default Group Assignment
----------------------------------------------------------------------

New users are automatically added to the "Employee" group via a user-created signal.

Field-Level Restrictions
----------------------------------------------------------------------

- Regular employees can update their first/last name and password.
- Only Admin/Manager can change username/email via the API.
