from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .permissions import HasAnyRole
from .roles import Role
from .serializers import AuthenticatedUserSerializer, LoginSerializer


@ensure_csrf_cookie
def csrf_token(request):
    return JsonResponse({"detail": "CSRF cookie set."})


class LoginRateThrottle(AnonRateThrottle):
    scope = "login"


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request=request._request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(
                {"detail": "Invalid username or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        login(request._request, user)
        return Response(AuthenticatedUserSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentUserView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        if not request.user.is_authenticated:
            return Response(
                {"detail": "Authentication credentials were not provided."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(AuthenticatedUserSerializer(request.user).data)


class ExampleRoleProtectedView(APIView):
    permission_classes = [IsAuthenticated, HasAnyRole]
    allowed_roles = ()
    area = ""

    def get(self, request):
        return Response({"access": "granted", "area": self.area})


class DashboardAccessView(ExampleRoleProtectedView):
    allowed_roles = (Role.ADMIN, Role.MANAGER)
    area = "dashboard"


class SalesAccessView(ExampleRoleProtectedView):
    allowed_roles = (Role.ADMIN, Role.MANAGER, Role.CASHIER)
    area = "sales"


class InventoryAccessView(ExampleRoleProtectedView):
    allowed_roles = (Role.ADMIN, Role.MANAGER, Role.INVENTORY_STAFF)
    area = "inventory"
