import json

from django.test import SimpleTestCase
from django.urls import reverse


class HealthEndpointTests(SimpleTestCase):
    def test_health_endpoint_returns_ok(self):
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {"status": "ok"})

    def test_health_endpoint_rejects_non_get_methods(self):
        response = self.client.post(reverse("health"))

        self.assertEqual(response.status_code, 405)
