Authentication and RBAC
======================================================================

Authentication
----------------------------------------------------------------------

- Session auth (SSR): django-allauth under ``/accounts/``
- API auth: Djoser + SimpleJWT under ``/api/v1/auth/``
  - JWT create: ``/api/v1/auth/jwt/create/``
  - JWT refresh: ``/api/v1/auth/jwt/refresh/``
  - Current user: ``/api/v1/auth/users/me/``

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

