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

- Users: ``/api/v1/users/``
- Departments: ``/api/v1/departments/``
- Employees: ``/api/v1/employees/``
- Employee Documents: ``/api/v1/employee-documents/``

OpenAPI & Docs
----------------------------------------------------------------------

- Schema: ``/api/v1/schema/``
- Swagger UI: ``/api/v1/docs/`` (admin-only by default)

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
