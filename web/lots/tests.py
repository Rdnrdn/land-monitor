from datetime import datetime, timezone

from django.test import SimpleTestCase
from django.utils.dateparse import parse_datetime


class OpendataNoticeIngestTests(SimpleTestCase):
    def test_effective_backlog_excludes_processed_before_limit(self):
        from lots.management.commands.ingest_notices_opendata import (
            _filter_backlog_pairs,
            _ledger_version_identity_from_key_values,
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
        processed_identities = {_ledger_version_identity_from_key_values(key_values[0])}

        backlog = _filter_backlog_pairs(candidate_pairs, processed_identities)
        planned_for_batch = backlog[:1]

        self.assertEqual([item["regNum"] for item, _ in backlog], ["n2", "n3"])
        self.assertEqual([item["regNum"] for item, _ in planned_for_batch], ["n2"])

    def test_canonical_identity_matches_candidate_microseconds_to_db_style(self):
        """Planning must treat ledger-processed rows the same way SQL lookup does."""
        from lots.management.commands.ingest_notices_opendata import (
            _filter_backlog_pairs,
            _ledger_version_identity,
            _ledger_version_identity_from_key_values,
        )

        row_like = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
        candidate_publish = datetime(2026, 4, 1, 0, 0, 0, 123456, tzinfo=timezone.utc)
        processed_identities = {
            _ledger_version_identity("n1", "notice", row_like, "https://example.test/1.json")
        }
        kv = {
            "reg_num": "n1",
            "document_type": "notice",
            "publish_date": candidate_publish,
            "href": "https://example.test/1.json",
        }
        pair = ({"regNum": "n1", "href": kv["href"]}, kv)
        self.assertEqual(_ledger_version_identity_from_key_values(kv), next(iter(processed_identities)))
        backlog = _filter_backlog_pairs([pair], processed_identities)
        self.assertEqual(backlog, [])

    def test_planned_batch_prefix_aligns_with_processing_order(self):
        from lots.management.commands.ingest_notices_opendata import _filter_backlog_pairs, _ledger_version_identity

        pairs = []
        for i in range(5):
            kv = {
                "reg_num": f"n{i}",
                "document_type": "notice",
                "publish_date": parse_datetime(f"2026-04-0{i + 1}T00:00:00+00:00"),
                "href": f"https://example.test/{i}.json",
            }
            pairs.append(({"regNum": kv["reg_num"], "href": kv["href"]}, kv))
        processed = {_ledger_version_identity("n0", "notice", pairs[0][1]["publish_date"], pairs[0][1]["href"])}
        backlog = _filter_backlog_pairs(pairs, processed)
        max_hrefs = 2
        planned = backlog[:max_hrefs]
        self.assertEqual([kv["reg_num"] for _, kv in planned], ["n1", "n2"])
        self.assertEqual(len(planned), max_hrefs)
