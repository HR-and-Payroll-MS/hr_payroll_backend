def jwt_tag_override(result, generator, request, public):
    """Normalize tags across the schema for a professional, non-redundant set."""
    patterns = [
        (lambda p: p.startswith("/api/v1/auth/jwt/"), "JWT Authentication"),
        (lambda p: p.startswith("/api/v1/auth/"), "Authentication"),
        (lambda p: p.startswith("/api/v1/users/"), "Users"),
        (
            lambda p: p.startswith("/api/v1/employees/") and "/attendances" in p,
            "Employee Attendance",
        ),
        (lambda p: p.startswith("/api/v1/attendances/"), "Attendance"),
        (lambda p: p.startswith("/api/v1/departments/"), "Departments"),
        (lambda p: p.startswith("/api/v1/payroll/cycles/"), "Payroll Cycles"),
        (lambda p: p.startswith("/api/v1/payroll/records/"), "Payroll Records"),
        (lambda p: p.startswith("/api/v1/payroll/reports/"), "Payroll Reports"),
        (lambda p: p == "/api/v1/schema/", "Meta"),
    ]
    for path, operations in result.get("paths", {}).items():
        tag = None
        for pred, name in patterns:
            if pred(path):
                tag = name
                break
        if tag is None:
            continue
        for op in operations.values():
            op["tags"] = [tag]
    return result
