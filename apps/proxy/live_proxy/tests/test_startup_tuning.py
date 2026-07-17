from unittest.mock import patch

from django.test import SimpleTestCase

from apps.proxy.live_proxy.input.manager import tune_ffmpeg_copy_command


class FfmpegCopyStartupTuningTests(SimpleTestCase):
    def test_copy_profile_gets_bounded_probe_and_low_latency_mux(self):
        original = [
            "ffmpeg",
            "-user_agent",
            "agent",
            "-i",
            "https://provider.test/live/u/p/1.m3u8",
            "-c",
            "copy",
            "-f",
            "mpegts",
            "pipe:1",
        ]

        tuned = tune_ffmpeg_copy_command(original)

        self.assertEqual(original[0:4], ["ffmpeg", "-user_agent", "agent", "-i"])
        self.assertIn("-probesize", tuned)
        self.assertEqual(tuned[tuned.index("-probesize") + 1], "1M")
        self.assertIn("-analyzeduration", tuned)
        self.assertIn("-flush_packets", tuned)
        self.assertIn("-muxdelay", tuned)
        self.assertLess(tuned.index("-probesize"), tuned.index("-i"))
        self.assertLess(tuned.index("-flush_packets"), tuned.index("pipe:1"))

    def test_reencoding_profile_is_unchanged(self):
        original = ["ffmpeg", "-i", "pipe:0", "-c:v", "h264_vaapi", "pipe:1"]

        self.assertIs(tune_ffmpeg_copy_command(original), original)

    def test_existing_probe_values_are_preserved(self):
        original = [
            "ffmpeg",
            "-probesize",
            "2M",
            "-analyzeduration",
            "2000000",
            "-i",
            "input",
            "-c",
            "copy",
            "pipe:1",
        ]

        tuned = tune_ffmpeg_copy_command(original)

        self.assertEqual(tuned.count("-probesize"), 1)
        self.assertEqual(tuned[tuned.index("-probesize") + 1], "2M")
        self.assertEqual(tuned.count("-analyzeduration"), 1)

    @patch.dict(
        "os.environ",
        {
            "DISPATCHARR_FFMPEG_COPY_PROBESIZE": "768K",
            "DISPATCHARR_FFMPEG_COPY_ANALYZEDURATION": "500000",
        },
    )
    def test_probe_bounds_are_operator_tunable(self):
        tuned = tune_ffmpeg_copy_command(
            ["ffmpeg", "-i", "input", "-c", "copy", "pipe:1"]
        )

        self.assertEqual(tuned[tuned.index("-probesize") + 1], "768K")
        self.assertEqual(
            tuned[tuned.index("-analyzeduration") + 1], "500000"
        )
