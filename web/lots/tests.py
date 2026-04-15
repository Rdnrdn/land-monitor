from datetime import datetime, timezone

from django.test import SimpleTestCase
from django.utils.dateparse import parse_datetime


class OpendataNoticeIngestTests(SimpleTestCase):
    def test_notice_bidd_type_code_reads_common_info_path(self):
        from lots.management.commands.ingest_notices_opendata import _notice_bidd_type_code

        payload = {
            "exportObject": {
                "structuredObject": {
                    "notice": {
                        "commonInfo": {
                            "biddType": {
                                "code": "ZK",
                                "name": "Аренда и продажа земельных участков",
                            }
                        }
                    }
                }
            }
        }

        self.assertEqual(_notice_bidd_type_code(payload), "ZK")

    def test_notice_bidd_type_code_returns_none_for_missing_path(self):
        from lots.management.commands.ingest_notices_opendata import _notice_bidd_type_code

        self.assertIsNone(_notice_bidd_type_code({}))

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


class OpendataLotSyncScopeTests(SimpleTestCase):
    def test_parse_fias_scope(self):
        from lots.management.commands.sync_lots_from_opendata_notices import _parse_fias_scope

        scope = _parse_fias_scope("69:3:e2d4a16b-79d1-4014-af64-4669fd89d824")

        self.assertEqual(scope["subject_rf_code"], "69")
        self.assertEqual(scope["level"], 3)
        self.assertEqual(scope["guid"], "e2d4a16b-79d1-4014-af64-4669fd89d824")
        self.assertEqual(scope["label"], "69:level_3:e2d4a16b-79d1-4014-af64-4669fd89d824")

    def test_lot_scope_match_uses_subject_and_fias_guid(self):
        from lots.management.commands.sync_lots_from_opendata_notices import _lot_scope_match

        lot_snapshot = {
            "subjectRF": {"code": "61"},
            "estateAddressFIAS": {
                "addressByFIAS": {
                    "hierarchyObjects": [
                        {
                            "guid": "region-guid",
                            "name": "обл Ростовская",
                            "level": {"code": 1},
                        },
                        {
                            "guid": "city-guid",
                            "name": "г Ростов-на-Дону",
                            "level": {"code": 5},
                        },
                    ]
                }
            },
        }
        scopes = [
            {"subject_rf_code": "69", "level": 3, "guid": "wrong-guid", "label": "69:level_3:wrong-guid"},
            {"subject_rf_code": "61", "level": 5, "guid": "city-guid", "label": "61:level_5:city-guid"},
        ]

        matched_scope, fias_levels, subject_code = _lot_scope_match(lot_snapshot, scopes)

        self.assertEqual(subject_code, "61")
        self.assertEqual(fias_levels["fias_level_5_guid"], "city-guid")
        self.assertIsNotNone(matched_scope)
        self.assertEqual(matched_scope["label"], "61:level_5:city-guid")
