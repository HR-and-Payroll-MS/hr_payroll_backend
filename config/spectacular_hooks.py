def jwt_tag_override(result, generator, request, public):
    """Post-processing hook to force JWT endpoints under 'JWT Authentication' tag.

    drf-spectacular allows mutation of the generated schema. We rewrite tags for
    paths beginning with the versioned JWT auth prefix.
    """
    paths = result.get("paths", {})
    for path, operations in paths.items():
        if path.startswith("/api/v1/auth/jwt/"):
            for op in operations.values():
                op["tags"] = ["JWT Authentication"]
    return result
