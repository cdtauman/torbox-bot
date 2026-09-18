import unittest

from services import parser


class ParserTests(unittest.TestCase):
    def test_usenet_result_stays_usenet(self):
        result = parser.normalize({
            "title": "Example.Movie.2026.1080p",
            "protocol": "usenet",
            "result_type": "usenet",
            "download_url": "http://prowlarr:9696/download/123",
            "size": 1234,
            "indexer": "Example NZB",
        })

        self.assertEqual(result["result_type"], "usenet")
        self.assertTrue(result["is_usenet"])
        self.assertFalse(result["is_webdl"])
        self.assertEqual(result["nzb_url"], "http://prowlarr:9696/download/123")
        self.assertEqual(result["magnet"], "")
        self.assertEqual(result["quality"], "1080p")

    def test_torrent_hash_generates_magnet(self):
        result = parser.normalize({
            "title": "Example 2160p",
            "hash": "abcdef1234567890abcdef1234567890abcdef12",
            "result_type": "torrent",
        })

        self.assertEqual(result["result_type"], "torrent")
        self.assertTrue(result["magnet"].startswith("magnet:?xt=urn:btih:"))
        self.assertTrue(result["generated_magnet"])

    def test_source_filter(self):
        results = [
            parser.normalize({"title": "A", "result_type": "torrent"}),
            parser.normalize({"title": "B", "result_type": "usenet", "nzb_url": "https://example/nzb"}),
            parser.normalize({"title": "C", "is_webdl": True, "magnet": "https://example/file"}),
        ]
        settings = {
            "quality": "all",
            "max_size_gb": 0,
            "cached_only": 0,
            "category": "all",
            "language": "all",
        }

        filtered = parser.apply_filters(results, settings, {"source_type": "usenet"})
        self.assertEqual([r["name"] for r in filtered], ["B"])


if __name__ == "__main__":
    unittest.main()
