from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.organizations.models import Branch, BranchMembership, Organization

from .roles import Role


class UserModelTests(TestCase):
    def test_configured_user_model_is_project_user(self):
        self.assertEqual(get_user_model().__module__, "apps.accounts.models")

    def test_user_manager_hashes_password(self):
        user = get_user_model().objects.create_user(
            username="shop-owner",
            password="a-strong-test-password",
        )

        self.assertNotEqual(user.password, "a-strong-test-password")
        self.assertTrue(user.check_password("a-strong-test-password"))


class AuthenticationApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="shop-cashier",
            password="a-strong-test-password",
            first_name="Shop",
            last_name="Cashier",
        )
        organization = Organization.objects.create(
            name="Test Shop",
            slug="test-shop",
        )
        branch = Branch.objects.create(
            organization=organization,
            name="Main Shop",
            code="MAIN",
        )
        BranchMembership.objects.create(
            user=self.user,
            branch=branch,
            role=Group.objects.get(name=Role.CASHIER),
        )
        self.client = APIClient(enforce_csrf_checks=True)

    def _csrf_token(self):
        response = self.client.get("/api/auth/csrf/")
        self.assertEqual(response.status_code, 200)
        return self.client.cookies["csrftoken"].value

    def _login(self):
        token = self._csrf_token()
        return self.client.post(
            "/api/auth/login/",
            {"username": "shop-cashier", "password": "a-strong-test-password"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )

    def test_login_requires_csrf_token(self):
        response = self.client.post(
            "/api/auth/login/",
            {"username": "shop-cashier", "password": "a-strong-test-password"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_login_current_user_and_logout(self):
        login_response = self._login()

        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(login_response.data["username"], "shop-cashier")
        self.assertEqual(login_response.data["roles"], [Role.CASHIER])
        self.assertNotIn("password", login_response.data)

        me_response = self.client.get("/api/auth/me/")
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.data["username"], "shop-cashier")

        blocked_logout = self.client.post("/api/auth/logout/", {}, format="json")
        self.assertEqual(blocked_logout.status_code, 403)

        token = self.client.cookies["csrftoken"].value
        logout_response = self.client.post(
            "/api/auth/logout/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(logout_response.status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_invalid_credentials_return_generic_error(self):
        token = self._csrf_token()
        response = self.client.post(
            "/api/auth/login/",
            {"username": "shop-cashier", "password": "incorrect-password"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data, {"detail": "Invalid username or password."})


class RolePermissionApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.manager = User.objects.create_user(
            username="shop-manager",
            password="a-strong-test-password",
        )
        organization = Organization.objects.create(
            name="Test Shop",
            slug="test-shop",
        )
        branch = Branch.objects.create(
            organization=organization,
            name="Main Shop",
            code="MAIN",
        )
        BranchMembership.objects.create(
            user=self.manager,
            branch=branch,
            role=Group.objects.get(name=Role.MANAGER),
        )
        self.cashier = User.objects.create_user(
            username="shop-cashier-role",
            password="a-strong-test-password",
        )
        BranchMembership.objects.create(
            user=self.cashier,
            branch=branch,
            role=Group.objects.get(name=Role.CASHIER),
        )
        self.client = APIClient(enforce_csrf_checks=True)

    def _login(self, username):
        self.client.get("/api/auth/csrf/")
        token = self.client.cookies["csrftoken"].value
        return self.client.post(
            "/api/auth/login/",
            {"username": username, "password": "a-strong-test-password"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )

    def test_role_permissions_allow_and_deny_by_branch_membership(self):
        self.assertEqual(self._login("shop-manager").status_code, 200)
        self.assertEqual(
            self.client.get("/api/auth/protected/dashboard/").status_code,
            200,
        )

        self.client.logout()
        self.assertEqual(self._login("shop-cashier-role").status_code, 200)
        self.assertEqual(
            self.client.get("/api/auth/protected/sales/").status_code,
            200,
        )
        self.assertEqual(
            self.client.get("/api/auth/protected/dashboard/").status_code,
            403,
        )
