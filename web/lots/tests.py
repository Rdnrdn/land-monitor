from django.test import SimpleTestCase
from django.utils.dateparse import parse_datetime


class OpendataNoticeIngestTests(SimpleTestCase):
    def test_effective_backlog_excludes_processed_before_limit(self):
        from lots.management.commands.ingest_notices_opendata import (
            _filter_backlog_pairs,
            _version_identity,
        )

        key_values = [
            {
                "reg_num": "n1",
                "document_type": "notice",
                "publish_date": parse_datetime("2026-04-01T00:00:00+00:00"),
                "href": "https://example.test/1.json",
            },
            {
                "reg_num": "n2",
                "document_type": "notice",
                "publish_date": parse_datetime("2026-04-02T00:00:00+00:00"),
                "href": "https://example.test/2.json",
            },
            {
                "reg_num": "n3",
                "document_type": "notice",
                "publish_date": parse_datetime("2026-04-03T00:00:00+00:00"),
                "href": "https://example.test/3.json",
            },
        ]
        candidate_pairs = [
            ({"regNum": key_value["reg_num"], "href": key_value["href"]}, key_value)
            for key_value in key_values
        ]
        processed_identities = {_version_identity(key_values[0])}

        backlog = _filter_backlog_pairs(candidate_pairs, processed_identities)
        planned_for_batch = backlog[:1]

        self.assertEqual([item["regNum"] for item, _ in backlog], ["n2", "n3"])
        self.assertEqual([item["regNum"] for item, _ in planned_for_batch], ["n2"])
