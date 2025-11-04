API Overview
======================================================================

Base URL
----------------------------------------------------------------------

The project exposes a single versioned API namespace:

- ``/api/v1/``

Previous un-versioned aliases (``/api/``) have been removed to enforce explicit
versioning and simplify documentation.

Routers
----------------------------------------------------------------------
Top-level:
- Users: ``/api/v1/users/``
- Departments: ``/api/v1/departments/``
- Employees: ``/api/v1/employees/``
- Attendances: ``/api/v1/attendances/``

Nested under employees:
- Documents: ``/api/v1/employees/{employee_id}/documents/``
- Contracts: ``/api/v1/employees/{employee_id}/contracts/``
- Job Histories: ``/api/v1/employees/{employee_id}/job-histories/``
- Compensations: ``/api/v1/employees/{employee_id}/compensations/``
- Salary Components: ``/api/v1/employees/{employee_id}/compensations/{compensation_id}/salary-components/``

OpenAPI & Docs
----------------------------------------------------------------------

- Schema: ``/api/v1/schema/``
- Swagger UI: ``/api/v1/docs/`` (admin-only by default)

Tag groups (overview):
- Authentication
- Users
- Departments
- Employees, Employees • Documents, Employees • Contracts, Employees • Job Histories
- Payroll • Compensations, Payroll • Salary Components
- Attendance • Records, Attendance • Summaries

Versioning Policy
----------------------------------------------------------------------

- All new endpoints MUST live under ``/api/v1/``.
- Future breaking changes will introduce ``/api/v2/`` while keeping ``/api/v1/``
	available until formally deprecated.
- Hyperlinked fields (e.g., in user serializers) always emit fully-qualified
	``/api/v1/`` URLs.

Deprecation Strategy
^^^^^^^^^^^^^^^^^^^^
- Add a deprecation notice in responses or documentation before removing a prior version.
- Provide migration notes in ``changelog.rst``.
