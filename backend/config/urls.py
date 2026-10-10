from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/products/", include("apps.products.urls")),
    path("api/inventory/", include("apps.inventory.urls")),
    path("api/customers/", include("apps.customers.urls")),
    path("api/suppliers/", include("apps.suppliers.urls")),
    path("api/purchases/", include("apps.purchases.urls")),
    path("api/sales/", include("apps.sales.urls")),
    path("api/reports/", include("apps.reports.urls")),
    path("api/backups/", include("apps.backups.urls")),
]
