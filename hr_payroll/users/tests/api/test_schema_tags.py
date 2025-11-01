from drf_spectacular.generators import SchemaGenerator


def test_schema_tag_grouping(db):
    generator = SchemaGenerator()
    schema = generator.get_schema(request=None, public=True)
    # Collect all tags from operations for representative paths
    paths = schema["paths"]
    tags_map = {}
    for candidate in [
        "/api/v1/employees/",
        "/api/v1/departments/",
        "/api/v1/employee-documents/",
        "/api/v1/auth/jwt/create/",
        "/api/v1/users/",
    ]:
        if candidate in paths:
            # pick first available method
            first_op = next(iter(paths[candidate].values()))
            tags_map[candidate] = first_op.get("tags")
    # Assertions: every candidate should have exactly one expected tag
    # Employees/Departments/Employee Documents endpoints may be disabled
    if "/api/v1/employees/" in tags_map:
        assert tags_map["/api/v1/employees/"] == ["Employees"]
    if "/api/v1/departments/" in tags_map:
        assert tags_map["/api/v1/departments/"] == ["Departments"]
    if "/api/v1/employee-documents/" in tags_map:
        assert tags_map["/api/v1/employee-documents/"] == ["Employee Documents"]
    # Auth endpoints grouped
    # JWT endpoints are grouped under a dedicated 'JWT Authentication' tag
    assert tags_map["/api/v1/auth/jwt/create/"] == ["JWT Authentication"]
    assert tags_map["/api/v1/users/"] == ["Users"]
