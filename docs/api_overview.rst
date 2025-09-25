API Overview
======================================================================

Base URLs
----------------------------------------------------------------------

- v1: ``/api/v1/`` (recommended)
- Legacy alias: ``/api/`` (mirrors v1 routes)

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

Versioning Notes
----------------------------------------------------------------------

Both ``/api/`` and ``/api/v1/`` are available. The serializer for Users returns
fully-qualified links respecting the current namespace (v1-aware URLs).

