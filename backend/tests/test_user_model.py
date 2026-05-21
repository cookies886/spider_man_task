def test_user_model_columns():
    from app.models.user import User

    cols = {c.name for c in User.__table__.columns}
    assert {
        "username",
        "password_hash",
        "email",
        "full_name",
        "is_active",
        "is_superuser",
        "must_change_password",
        "last_login_at",
    }.issubset(cols)


def test_role_and_permission_models():
    from app.models.user import (
        PageACL,
        Permission,
        Role,
        RolePermission,
        UserRole,
    )

    assert Role.__tablename__ == "roles"
    assert Permission.__tablename__ == "permissions"
    assert UserRole.__tablename__ == "user_roles"
    assert RolePermission.__tablename__ == "role_permissions"
    assert PageACL.__tablename__ == "page_acls"
