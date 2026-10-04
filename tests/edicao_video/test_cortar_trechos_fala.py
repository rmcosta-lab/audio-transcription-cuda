import unittest

from edicao_video.cortar_trechos_fala import parse_progress_time


class ParseProgressTimeTests(unittest.TestCase):
    def test_parses_ffmpeg_microsecond_fields(self) -> None:
        self.assertEqual(parse_progress_time("out_time_us", "1500000"), 1.5)
        self.assertEqual(parse_progress_time("out_time_ms", "2250000"), 2.25)

    def test_parses_formatted_timestamp(self) -> None:
        self.assertEqual(parse_progress_time("out_time", "01:02:03.500000"), 3723.5)

    def test_ignores_unavailable_or_invalid_timestamps(self) -> None:
        for value in ("N/A", "", "invalid", "-1000000"):
            with self.subTest(value=value):
                self.assertIsNone(parse_progress_time("out_time_us", value))


if __name__ == "__main__":
    unittest.main()
