from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class SecretLoggingConfigTests(SimpleTestCase):
    def test_uwsgi_logs_never_include_request_uri(self):
        root = Path(settings.BASE_DIR)
        for relative in ("docker/uwsgi.ini", "docker/uwsgi.modular.ini"):
            with self.subTest(config=relative):
                content = (root / relative).read_text()
                log_format = next(
                    line for line in content.splitlines()
                    if line.startswith("log-format =")
                )
                self.assertNotIn("%(uri)", log_format)
                self.assertNotIn("QUERY_STRING", log_format)
                self.assertIn("ignore-write-errors = true", content)
                self.assertIn("disable-write-exception = true", content)

    def test_nginx_access_log_is_disabled(self):
        content = (Path(settings.BASE_DIR) / "docker/nginx.conf").read_text()

        self.assertIn("access_log off;", content)
