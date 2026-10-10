from django.urls import path

from .views import BranchOperationalReportView

app_name = "reports"

urlpatterns = [
    path(
        "branches/<int:branch_id>/",
        BranchOperationalReportView.as_view(),
        name="branch-operational-report",
    ),
]
