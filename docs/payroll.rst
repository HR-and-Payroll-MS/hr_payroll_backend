Payroll
======================================================================

Overview
----------------------------------------------------------------------
Payroll data is modeled as Compensations (containers) with nested Salary
Components (earnings/deductions). Endpoints are nested under an employee.

Compensations
----------------------------------------------------------------------
- List/Create: ``/api/v1/employees/{employee_id}/compensations/``
- Retrieve/Update/Delete: ``/api/v1/employees/{employee_id}/compensations/{id}/``
- Action: ``POST /api/v1/employees/{employee_id}/compensations/{id}/apply-to-employee/``
  Body: {"employee": "<target_employee_id>"}
  Clones all components into a new compensation for the target employee.

Salary Components
----------------------------------------------------------------------
- List/Create: ``/api/v1/employees/{employee_id}/compensations/{compensation_id}/salary-components/``
- Retrieve/Update/Delete: ``/api/v1/employees/{employee_id}/compensations/{compensation_id}/salary-components/{id}/``

Behavior & recalculation
----------------------------------------------------------------------
- Components are grouped under their parent Compensation.
- On create/update/delete of a component, the parent total is recalculated.

Permissions
----------------------------------------------------------------------
- Authenticated read.
- Admin-only writes by default. (Managers may be granted via future settings)

OpenAPI tags
----------------------------------------------------------------------
- "Payroll • Compensations"
- "Payroll • Salary Components"
