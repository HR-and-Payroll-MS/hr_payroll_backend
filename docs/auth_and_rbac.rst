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
``JWT Authentication``
  - ``POST /api/v1/auth/jwt/create/``
  - ``POST /api/v1/auth/jwt/refresh/``
  - ``POST /api/v1/auth/jwt/verify/``
``Session Auth``
  - ``POST /api/v1/auth/login/``
  - ``POST /api/v1/auth/logout/``
  - ``POST /api/v1/auth/password/change/`` (self)
  - ``POST /api/v1/auth/password/reset/`` (Manager/Admin)
  - ``POST /api/v1/auth/password/reset/confirm/`` (Manager/Admin)
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

Registration Policy
----------------------------------------------------------------------

- Public self-registration is disabled.
- Only Admins/Managers may create users.
- Activation emails are disabled; new users created by Admin/Manager are active immediately.
- “Onboarding” is the recommended flow to create a User and their Employee in a single step (see Employees page).

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
