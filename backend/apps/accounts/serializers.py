from rest_framework import serializers

from .models import User
from .roles import Role


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(trim_whitespace=True)
    password = serializers.CharField(trim_whitespace=False, write_only=True)


class AuthenticatedUserSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "first_name", "last_name", "roles")

    def get_roles(self, user):
        roles = list(
            user.branch_memberships.filter(
                branch__is_active=True,
                branch__organization__is_active=True,
            )
            .values_list("role__name", flat=True)
            .distinct()
        )
        if user.is_superuser and Role.ADMIN not in roles:
            roles.append(Role.ADMIN)
        return roles
