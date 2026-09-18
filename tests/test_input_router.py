import unittest

from services.input_router import classify_text, safe_log_summary


class InputRouterTests(unittest.TestCase):
    def test_plain_text_is_search(self):
        intent = classify_text("Example Movie 2026 1080p")
        self.assertEqual(intent.kind, "search")

    def test_magnet_is_detected(self):
        intent = classify_text("magnet:?xt=urn:btih:abcdef")
        self.assertEqual(intent.kind, "magnet")

    def test_infohash_is_detected(self):
        value = "abcdef1234567890abcdef1234567890abcdef12"
        intent = classify_text(value)
        self.assertEqual(intent.kind, "torrent_hash")
        self.assertEqual(intent.value, value)

    def test_http_url_is_direct_download(self):
        intent = classify_text("https://example.com/file.bin?token=secret")
        self.assertEqual(intent.kind, "url")

    def test_www_url_gets_https(self):
        intent = classify_text("www.example.com/file")
        self.assertEqual(intent.kind, "url")
        self.assertEqual(intent.value, "https://www.example.com/file")

    def test_nzb_url_is_detected(self):
        intent = classify_text("https://example.com/releases/item.nzb")
        self.assertEqual(intent.kind, "nzb_url")

    def test_sentence_containing_url_remains_search(self):
        intent = classify_text("find https://example.com movie")
        self.assertEqual(intent.kind, "search")

    def test_log_summary_does_not_expose_secret_url(self):
        summary = safe_log_summary("https://example.com/file?token=very-secret")
        self.assertIn("host=example.com", summary)
        self.assertNotIn("very-secret", summary)

    def test_log_summary_does_not_expose_magnet(self):
        value = "magnet:?xt=urn:btih:SECRET"
        summary = safe_log_summary(value)
        self.assertNotIn("SECRET", summary)


if __name__ == "__main__":
    unittest.main()
