from enum import Enum


class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    COMPANY_ADMIN = "company_admin"
    OPERATOR = "operator"


ROLE_HIERARCHY = {
    UserRole.SUPER_ADMIN: 100,
    UserRole.COMPANY_ADMIN: 50,
    UserRole.OPERATOR: 10,
}


def has_role(user_role: str, required_role: UserRole) -> bool:
    return ROLE_HIERARCHY.get(UserRole(user_role), 0) >= ROLE_HIERARCHY[required_role]
