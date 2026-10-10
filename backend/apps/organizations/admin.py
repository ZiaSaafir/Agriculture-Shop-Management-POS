from django import forms
from django.contrib import admin
from django.contrib.auth.models import Group

from apps.accounts.roles import Role

from .models import Branch, BranchMembership, Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "organization", "is_active")
    list_filter = ("organization", "is_active")
    search_fields = ("name", "code", "organization__name")


class BranchMembershipForm(forms.ModelForm):
    class Meta:
        model = BranchMembership
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].queryset = Group.objects.filter(name__in=Role.CHOICES)


@admin.register(BranchMembership)
class BranchMembershipAdmin(admin.ModelAdmin):
    form = BranchMembershipForm
    list_display = ("user", "branch", "role", "created_at")
    list_filter = ("branch__organization", "branch", "role")
    search_fields = ("user__username", "branch__name", "role__name")
