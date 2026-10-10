from rest_framework.permissions import BasePermission


class HasAnyRole(BasePermission):
    message = "You do not have a role that can access this resource."

    def has_permission(self, request, view):
        user = request.user
        if user.is_superuser:
            return True

        allowed_roles = getattr(view, "allowed_roles", ())
        if not allowed_roles:
            return False

        return user.branch_memberships.filter(
            branch__is_active=True,
            branch__organization__is_active=True,
            role__name__in=allowed_roles,
        ).exists()
