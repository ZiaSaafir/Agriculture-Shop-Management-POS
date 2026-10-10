from django.urls import path

from .views import (
    BranchPurchaseDetailView,
    BranchPurchaseListView,
    BranchPurchaseReceiveView,
    BranchPurchaseReturnDetailView,
    BranchPurchaseReturnListView,
    BranchPurchaseReturnPostView,
    BranchSupplierInvoiceBalancesView,
    BranchSupplierPaymentDetailView,
    BranchSupplierPaymentListView,
)

app_name = "purchases"

urlpatterns = [
    path(
        "branches/<int:branch_id>/",
        BranchPurchaseListView.as_view(),
        name="branch-purchase-list",
    ),
    path(
        "branches/<int:branch_id>/<int:purchase_id>/",
        BranchPurchaseDetailView.as_view(),
        name="branch-purchase-detail",
    ),
    path(
        "branches/<int:branch_id>/<int:purchase_id>/receive/",
        BranchPurchaseReceiveView.as_view(),
        name="branch-purchase-receive",
    ),
    path(
        "branches/<int:branch_id>/outstanding/",
        BranchSupplierInvoiceBalancesView.as_view(),
        name="branch-purchase-outstanding",
    ),
    path(
        "branches/<int:branch_id>/payments/",
        BranchSupplierPaymentListView.as_view(),
        name="branch-supplier-payment-list",
    ),
    path(
        "branches/<int:branch_id>/payments/<int:payment_id>/",
        BranchSupplierPaymentDetailView.as_view(),
        name="branch-supplier-payment-detail",
    ),
    path(
        "branches/<int:branch_id>/returns/",
        BranchPurchaseReturnListView.as_view(),
        name="branch-purchase-return-list",
    ),
    path(
        "branches/<int:branch_id>/returns/<int:return_id>/",
        BranchPurchaseReturnDetailView.as_view(),
        name="branch-purchase-return-detail",
    ),
    path(
        "branches/<int:branch_id>/returns/<int:return_id>/post/",
        BranchPurchaseReturnPostView.as_view(),
        name="branch-purchase-return-post",
    ),
]
