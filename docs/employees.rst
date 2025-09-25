Employees Module
======================================================================

Models
----------------------------------------------------------------------

- Department: simple org grouping (unique name)
- Employee: one-to-one with User; fields include department, title, hire_date
- EmployeeDocument: file uploads linked to Employee (path includes employee PK)

API Endpoints
----------------------------------------------------------------------

- Departments: ``/api/v1/departments/`` (Admin/Manager write; authenticated read)
- Employees: ``/api/v1/employees/``
  - Regular employees see only their own record; Admin/Manager see all
  - Create via one of two manager-only onboarding endpoints (see below)
- Employee Documents: ``/api/v1/employee-documents/``
  - Regular employees can upload only for themselves; elevated users may upload for anyone

Onboarding (Manager/Admin only)
----------------------------------------------------------------------

Single-step creation of a User and their Employee, or promotion of an existing user to Employee.

- Create new User + Employee:
  - POST ``/api/v1/employees/onboard/new``
  - Body:
    ::

        {
          "username": "alice",
          "email": "alice@example.com",
          "password": "AlicePass!123",
          "first_name": "Alice",
          "last_name": "Smith",
          "department": 3,
          "title": "Engineer",
          "hire_date": "2025-09-25"
        }

  - Behavior:
    - Creates the User (active)
    - Marks the email verified and primary (django-allauth)
    - Activation emails are disabled globally; onboarding users are active immediately
    - Creates the Employee

- Promote existing User to Employee:
  - POST ``/api/v1/employees/onboard/existing``
  - Body:
    ::

        { "user": "bob", "department": 3, "title": "Analyst" }

  - Constraints:
    - Only users who are not already employees are listed/accepted

Uploads & Validation
----------------------------------------------------------------------

- Allowed extensions: .pdf .png .jpg .jpeg .txt
- Max size: 5MB
- Server-side validation on both model and serializer

Security & Object Permissions
----------------------------------------------------------------------

- Admin/Manager can write across Departments/Employees/EmployeeDocuments
- Regular employees can read and modify their own resources only

