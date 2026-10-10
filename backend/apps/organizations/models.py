from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import models

from apps.accounts.roles import Role


class Organization(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")

    def __str__(self):
        return self.name


class Branch(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="branches",
    )
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=32)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("organization__name", "name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "name"),
                name="unique_branch_name_per_organization",
            ),
            models.UniqueConstraint(
                fields=("organization", "code"),
                name="unique_branch_code_per_organization",
            ),
        ]
        indexes = [
            models.Index(
                fields=("organization", "is_active"),
                name="branch_org_active_idx",
            ),
        ]

    def __str__(self):
        return f"{self.organization}: {self.name}"


class BranchMembership(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="branch_memberships",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="memberships",
    )
    role = models.ForeignKey(
        Group,
        on_delete=models.PROTECT,
        related_name="branch_memberships",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("user__username", "branch__name", "role__name")
        constraints = [
            models.UniqueConstraint(
                fields=("user", "branch", "role"),
                name="unique_user_branch_role_membership",
            ),
        ]
        indexes = [
            models.Index(
                fields=("branch", "role"),
                name="membership_branch_role_idx",
            ),
        ]

    def clean(self):
        super().clean()
        if self.role_id and self.role.name not in Role.CHOICES:
            raise ValidationError(
                {"role": "Select one of the configured shop roles."}
            )

    def __str__(self):
        return f"{self.user} — {self.branch} ({self.role})"
