import unittest

import config
from services import prowlarr_api


class ProwlarrMappingTests(unittest.TestCase):
    def test_protocol_mapping(self):
        self.assertEqual(prowlarr_api._protocol({"protocol": "usenet"}), "usenet")
        self.assertEqual(prowlarr_api._protocol({"protocol": 1}), "usenet")
        self.assertEqual(prowlarr_api._protocol({"protocol": "torrent"}), "torrent")
        self.assertEqual(prowlarr_api._protocol({"protocol": 2}), "torrent")

    def test_absolute_url_uses_configured_prowlarr_origin(self):
        old_url = config.PROWLARR_URL
        config.PROWLARR_URL = "http://prowlarr:9696"
        try:
            value = prowlarr_api._absolute_url(
                "http://127.0.0.1:9696/download?id=123"
            )
            self.assertEqual(value, "http://prowlarr:9696/download?id=123")
        finally:
            config.PROWLARR_URL = old_url

    def test_absolute_url_rejects_external_host(self):
        old_url = config.PROWLARR_URL
        config.PROWLARR_URL = "http://prowlarr:9696"
        try:
            with self.assertRaises(prowlarr_api.ProwlarrError):
                prowlarr_api._absolute_url("https://example.com/download/123")
        finally:
            config.PROWLARR_URL = old_url

    def test_usenet_release_maps_to_nzb(self):
        mapped = prowlarr_api._map_release({
            "protocol": "usenet",
            "title": "Example.Release",
            "downloadUrl": "/download/nzb/123",
            "size": 987654,
            "indexer": "Example NZB",
        })

        self.assertEqual(mapped["result_type"], "usenet")
        self.assertEqual(mapped["nzb_url"], "/download/nzb/123")
        self.assertEqual(mapped["torrent_url"], "")
        self.assertEqual(mapped["hash"], "")

    def test_torrent_release_maps_to_torrent_url(self):
        mapped = prowlarr_api._map_release({
            "protocol": "torrent",
            "title": "Example.Release",
            "downloadUrl": "/download/torrent/123",
            "infoHash": "abcdef1234567890abcdef1234567890abcdef12",
            "seeders": 42,
        })

        self.assertEqual(mapped["result_type"], "torrent")
        self.assertEqual(mapped["torrent_url"], "/download/torrent/123")
        self.assertEqual(mapped["nzb_url"], "")
        self.assertEqual(mapped["seeders"], 42)


if __name__ == "__main__":
    unittest.main()
