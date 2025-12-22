Efficiency
==========

Overview
--------
The efficiency feature mirrors the frontend JSON shapes exactly. Templates are stored as plain JSON and evaluations return the same JSON with server-computed summaries.

Templates
---------
- GET ``/api/v1/efficiency/templates/schema``
  - Returns the active template JSON (fields: ``title``, ``performanceMetrics``, ``feedbackSections``).
- PUT ``/api/v1/efficiency/templates/schema-set``
  - Body: the exact template JSON the frontend builds (same keys as above).
  - Response: the same JSON persisted.
- Permissions: Admin/Manager (staff allowed).

Evaluations
-----------
- POST ``/api/v1/efficiency/evaluations/submit``
  - Required fields: ``template`` (id), ``employee`` (id), ``data``.
  - ``data`` may be either:
    - ``{"answers": {"<fieldId>": <value>}}``; or
    - ``{"performanceMetrics": [{"id": "...", "selected": <value>}], "feedback": [{"id": "...", "value": <value>}]}".
  - Response: same JSON with ``summary`` added plus ``totalEfficiency`` rounded to 2 decimals.
- Permissions and scope:
  - Admin/Manager: all.
  - Line Manager: limited to their department employees.
  - Employee: can view own evaluations.

Scoring rules
-------------
- Number metric: ``possible = weight``; ``achieved = min(answer, weight)``.
- Dropdown metric: ``possible = max(option.point)``; achieved parsed from the selected value (number inside string or matching option label).
- Totals: ``totalEfficiency = (totalAchieved / totalPossible) * 100`` (0 when no possible points).

Notes
-----
- Responses from these endpoints are plain JSON without extra metadata, matching the frontend shapes in ``src/Examples``.
- Department/organization scoping is allowed but defaults to global template selection (first active template).
