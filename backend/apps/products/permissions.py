from django.shortcuts import get_object_or_404
from rest_framework.permissions import BasePermission

from apps.accounts.roles import Role
from apps.organizations.models import Branch


class ProductCatalogBranchPermission(BasePermission):
    message = "You do not have product catalog access to this branch."
    allowed_roles = (Role.ADMIN, Role.MANAGER, Role.INVENTORY_STAFF)

    def has_permission(self, request, view):
        branch = get_object_or_404(
            Branch.objects.select_related("organization"),
            pk=view.kwargs["branch_id"],
            is_active=True,
            organization__is_active=True,
        )
        view.product_branch = branch
        if request.user.is_superuser:
            return True
        return request.user.branch_memberships.filter(
            branch=branch,
            role__name__in=self.allowed_roles,
        ).exists()
