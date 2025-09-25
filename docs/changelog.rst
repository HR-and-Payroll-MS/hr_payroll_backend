Changelog (Iterations 0 & 1)
======================================================================

Iteration 0
----------------------------------------------------------------------

- API versioning: added ``/api/`` and ``/api/v1/`` namespaces
- Auth routes organized under ``/api/auth`` and ``/api/v1/auth`` (Djoser, SimpleJWT)
- Schema & docs available on both versions
- Seeded RBAC groups (Admin, Manager, Employee)
- Introduced audit app with basic login/update events

Iteration 1
----------------------------------------------------------------------

- Employees app: Department, Employee (1:1 User), EmployeeDocument
- CRUD endpoints with RBAC and object-level permissions
- File upload validation (size/type)
- User defaults: auto-assign Employee group on user creation
- Improved Users API: ``/api/v1/users/me/`` enriched with group info
- Manager-only onboarding endpoints:
  - ``POST /api/v1/employees/onboard/new`` – create User+Employee; email auto-verified (allauth)
  - ``POST /api/v1/employees/onboard/existing`` – promote existing user to Employee (non-employee only)
- Manager-only registration enforcement; users cannot self-register
- Users API URL field now version-aware (links reflect /api vs /api/v1)

Notes
----------------------------------------------------------------------

- Activation emails can be disabled if desired to streamline onboarding
- Generic Employee create kept for compatibility but the onboarding endpoints are preferred
