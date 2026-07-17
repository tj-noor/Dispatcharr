from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.output.catalog_cache import (
    bump_catalog_revision,
    cache_catalog,
    catalog_cache_key,
    get_cached_catalog,
)


class XcCatalogCacheTests(SimpleTestCase):
    def _user(self):
        user = MagicMock()
        user.pk = 7
        user.user_level = 3
        user.custom_properties = {"hide_adult_content": True}
        user.channel_profiles.order_by.return_value.values_list.return_value = [2, 5]
        return user

    @patch("apps.output.catalog_cache.get_catalog_revision", return_value=12)
    def test_key_covers_user_profiles_category_revision_and_origin(self, _revision):
        request = RequestFactory().get("/player_api.php", HTTP_HOST="tv.test")

        first = catalog_cache_key(request, self._user(), category_id=9)
        second = catalog_cache_key(request, self._user(), category_id=10)

        self.assertTrue(first.startswith("output:xc-live:12:"))
        self.assertNotEqual(first, second)

    @patch("apps.output.catalog_cache.cache")
    def test_revision_bump_uses_atomic_increment(self, mock_cache):
        mock_cache.incr.return_value = 4

        self.assertEqual(bump_catalog_revision(), 4)
        mock_cache.incr.assert_called_once()

    @override_settings(XC_LIVE_CATALOG_CACHE_TIMEOUT=15)
    @patch("apps.output.catalog_cache.cache")
    def test_cache_stores_and_reads_serialized_payload(self, mock_cache):
        payload = b'[{"stream_id":1}]'
        mock_cache.get.return_value = payload

        cache_catalog("key", payload)

        mock_cache.set.assert_called_once_with("key", payload, timeout=15)
        self.assertEqual(get_cached_catalog("key"), payload)

    @patch("apps.output.catalog_cache.cache")
    def test_cache_failure_falls_back_to_generation(self, mock_cache):
        mock_cache.get.side_effect = OSError("redis unavailable")

        self.assertIsNone(get_cached_catalog("key"))
