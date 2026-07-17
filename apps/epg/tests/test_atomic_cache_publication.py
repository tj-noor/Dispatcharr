import gzip
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

from django.test import SimpleTestCase

from apps.epg.tasks import _publish_epg_cache_file


class AtomicEPGCachePublicationTests(SimpleTestCase):
    def test_concurrent_plain_downloads_use_independent_staging_files(self):
        payloads = (
            b"<?xml version='1.0'?><tv><channel id='one'/></tv>",
            b"<?xml version='1.0'?><tv><channel id='two'/></tv>",
        )

        with tempfile.TemporaryDirectory() as cache_dir:
            staging_paths = []
            for index, payload in enumerate(payloads):
                path = os.path.join(cache_dir, f".8.{index}.download.tmp")
                with open(path, "wb") as staging_file:
                    staging_file.write(payload)
                staging_paths.append(path)

            with ThreadPoolExecutor(max_workers=2) as executor:
                published_paths = list(
                    executor.map(
                        lambda path: _publish_epg_cache_file(
                            path, cache_dir, source_id=8, is_compressed=False
                        ),
                        staging_paths,
                    )
                )

            stable_path = os.path.join(cache_dir, "8.xml")
            self.assertEqual(published_paths, [stable_path, stable_path])
            with open(stable_path, "rb") as published_file:
                self.assertIn(published_file.read(), payloads)
            self.assertFalse(any(os.path.exists(path) for path in staging_paths))

    def test_concurrent_compressed_downloads_publish_complete_xml(self):
        payloads = (
            b"<?xml version='1.0'?><tv><channel id='one'/></tv>",
            b"<?xml version='1.0'?><tv><channel id='two'/></tv>",
        )

        with tempfile.TemporaryDirectory() as cache_dir:
            staging_paths = []
            for index, payload in enumerate(payloads):
                path = os.path.join(cache_dir, f".8.{index}.download.tmp")
                with gzip.open(path, "wb") as staging_file:
                    staging_file.write(payload)
                staging_paths.append(path)

            with ThreadPoolExecutor(max_workers=2) as executor:
                published_paths = list(
                    executor.map(
                        lambda path: _publish_epg_cache_file(
                            path, cache_dir, source_id=8, is_compressed=True
                        ),
                        staging_paths,
                    )
                )

            stable_path = os.path.join(cache_dir, "8.xml")
            self.assertEqual(published_paths, [stable_path, stable_path])
            with open(stable_path, "rb") as published_file:
                self.assertIn(published_file.read(), payloads)
            self.assertFalse(any(os.path.exists(path) for path in staging_paths))
            self.assertEqual(
                [name for name in os.listdir(cache_dir) if name != "8.xml"],
                [],
            )
