from django.test import SimpleTestCase

from dispatcharr.redaction import redact_sensitive_text, redact_url_credentials
from apps.proxy.live_proxy.url_utils import transform_url


class CredentialRedactionTests(SimpleTestCase):
    username = "known-xc-user"
    password = "known-xc-password"

    def assertCredentialsRedacted(self, value):
        self.assertNotIn(self.username, value)
        self.assertNotIn(self.password, value)
        self.assertIn("REDACTED", value)

    def test_redacts_live_path_credentials(self):
        value = redact_url_credentials(
            f"https://provider.test/live/{self.username}/{self.password}/123.ts"
        )
        self.assertCredentialsRedacted(value)
        self.assertTrue(value.endswith("/123.ts"))

    def test_redacts_movie_and_legacy_path_credentials(self):
        for url in (
            f"https://provider.test/movie/{self.username}/{self.password}/456.mkv",
            f"https://provider.test/{self.username}/{self.password}/789.ts",
        ):
            with self.subTest(url=url):
                self.assertCredentialsRedacted(redact_url_credentials(url))

    def test_redacts_query_and_userinfo_credentials(self):
        value = redact_url_credentials(
            f"https://{self.username}:{self.password}@provider.test/player_api.php"
            f"?username={self.username}&password={self.password}&action=x"
        )
        self.assertCredentialsRedacted(value)
        self.assertIn("action=x", value)

    def test_redacts_url_inside_exception_text(self):
        value = redact_sensitive_text(
            f"request failed for https://provider.test/live/{self.username}/"
            f"{self.password}/123.ts after timeout"
        )
        self.assertCredentialsRedacted(value)

    def test_transformed_url_logs_never_capture_known_credentials(self):
        url = (
            f"https://provider.test/live/{self.username}/{self.password}/123.ts"
        )

        with self.assertLogs("live_proxy.url_utils", level="DEBUG") as captured:
            self.assertEqual(transform_url(url, r"$^", "unused"), url)

        output = "\n".join(captured.output)
        self.assertCredentialsRedacted(output)
