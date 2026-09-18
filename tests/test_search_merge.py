import unittest

import config
from handlers import search


class SearchMergeTests(unittest.TestCase):
    def test_round_robin_merge_keeps_multiple_providers(self):
        old_limit = config.SEARCH_LIMIT
        config.SEARCH_LIMIT = 4
        try:
            prowlarr = [
                {"title": "P1", "hash": "1"},
                {"title": "P2", "hash": "2"},
                {"title": "P3", "hash": "3"},
                {"title": "P4", "hash": "4"},
            ]
            torbox = [
                {"title": "T1", "hash": "a"},
                {"title": "T2", "hash": "b"},
                {"title": "T3", "hash": "c"},
            ]

            merged = search._merge_results([prowlarr, torbox])
            self.assertEqual([item["title"] for item in merged], ["P1", "T1", "P2", "T2"])
        finally:
            config.SEARCH_LIMIT = old_limit

    def test_merge_deduplicates_hashes_across_providers(self):
        old_limit = config.SEARCH_LIMIT
        config.SEARCH_LIMIT = 10
        try:
            merged = search._merge_results([
                [{"title": "P", "hash": "ABC"}],
                [{"title": "T duplicate", "hash": "abc"}, {"title": "T unique", "hash": "def"}],
            ])
            self.assertEqual(len(merged), 2)
            self.assertEqual({item["hash"].lower() for item in merged}, {"abc", "def"})
        finally:
            config.SEARCH_LIMIT = old_limit


if __name__ == "__main__":
    unittest.main()
