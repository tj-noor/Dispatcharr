from unittest.mock import MagicMock, call, patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from dispatcharr.health import _database_ready, _redis_ready, live, ready


class HealthEndpointTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/health/ready")

    def test_liveness_has_no_dependency_checks(self):
        response = live(RequestFactory().get("/health/live"))

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"status": "ok"})

    @patch("dispatcharr.health._redis_ready", return_value=True)
    @patch("dispatcharr.health._database_ready", return_value=True)
    def test_readiness_reports_both_dependencies(self, _database, _redis):
        response = ready(self.request)

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content,
            {"status": "ok", "checks": {"database": True, "redis": True}},
        )

    @patch("dispatcharr.health._redis_ready", return_value=True)
    @patch("dispatcharr.health._database_ready", return_value=False)
    def test_readiness_fails_when_database_is_unavailable(self, _database, _redis):
        response = ready(self.request)

        self.assertEqual(response.status_code, 503)

    @patch("dispatcharr.health.close_old_connections")
    @patch("dispatcharr.health.connection")
    def test_database_probe_restores_timeout_and_closes_checkout(
        self, mock_connection, mock_close
    ):
        cursor = MagicMock()
        cursor.fetchone.return_value = (1,)
        mock_connection.vendor = "postgresql"
        mock_connection.cursor.return_value.__enter__.return_value = cursor

        self.assertTrue(_database_ready(750))

        self.assertEqual(
            cursor.execute.call_args_list,
            [
                call("SET statement_timeout = '750ms'"),
                call("SELECT 1"),
                call("SET statement_timeout = DEFAULT"),
            ],
        )
        mock_close.assert_called_once()

    @override_settings(
        REDIS_HOST="redis.test",
        REDIS_PORT=6380,
        REDIS_DB=4,
        REDIS_USER="",
        REDIS_PASSWORD="",
        REDIS_SSL_PARAMS={},
    )
    @patch("dispatcharr.health.redis.Redis")
    def test_redis_probe_uses_bounded_socket_timeouts(self, redis_cls):
        redis_cls.return_value.ping.return_value = True

        self.assertTrue(_redis_ready(1.25))

        redis_cls.assert_called_once_with(
            host="redis.test",
            port=6380,
            db=4,
            username=None,
            password=None,
            socket_connect_timeout=1.25,
            socket_timeout=1.25,
            retry_on_timeout=False,
        )
        redis_cls.return_value.close.assert_called_once()
