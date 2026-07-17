from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class RuntimeEnvironmentConfigTests(SimpleTestCase):
    def test_stream_startup_tuning_reaches_login_shell_workers(self):
        entrypoint = (
            Path(settings.BASE_DIR) / "docker/entrypoint.sh"
        ).read_text()

        for variable in (
            "DISPATCHARR_INITIAL_BUFFER_CHUNKS",
            "DISPATCHARR_FFMPEG_COPY_PROBESIZE",
            "DISPATCHARR_FFMPEG_COPY_ANALYZEDURATION",
            "XC_LIVE_CATALOG_CACHE_TIMEOUT",
        ):
            with self.subTest(variable=variable):
                self.assertIn(variable, entrypoint)
