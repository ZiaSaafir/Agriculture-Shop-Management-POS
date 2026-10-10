from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.accounts.roles import Role

from .models import Branch, BranchMembership, Organization


class OrganizationModelTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Agriculture Shop",
            slug="agriculture-shop",
        )

    def test_branch_codes_and_names_are_unique_per_organization(self):
        Branch.objects.create(
            organization=self.organization,
            name="Main Shop",
            code="MAIN",
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Branch.objects.create(
                organization=self.organization,
                name="Main Shop",
                code="SECOND",
            )

        other_organization = Organization.objects.create(
            name="Another Shop",
            slug="another-shop",
        )
        Branch.objects.create(
            organization=other_organization,
            name="Main Shop",
            code="MAIN",
        )

    def test_membership_requires_a_configured_role(self):
        branch = Branch.objects.create(
            organization=self.organization,
            name="Main Shop",
            code="MAIN",
        )
        user = get_user_model().objects.create_user(
            username="staff",
            password="strong-test-password",
        )
        other_group = Group.objects.create(name="Unconfigured role")
        membership = BranchMembership(
            user=user,
            branch=branch,
            role=other_group,
        )

        with self.assertRaises(ValidationError):
            membership.full_clean()

    def test_membership_prevents_duplicate_user_branch_role(self):
        branch = Branch.objects.create(
            organization=self.organization,
            name="Main Shop",
            code="MAIN",
        )
        user = get_user_model().objects.create_user(
            username="staff",
            password="strong-test-password",
        )
        role = Group.objects.get(name=Role.CASHIER)
        BranchMembership.objects.create(user=user, branch=branch, role=role)

        with self.assertRaises(IntegrityError), transaction.atomic():
            BranchMembership.objects.create(user=user, branch=branch, role=role)
