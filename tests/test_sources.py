from __future__ import annotations

import json
from pathlib import Path
import unittest

from astrbot_plugin_anime.sources import (
    parse_acgsecrets_html,
    parse_bangumi_payload,
    parse_bgmlist_payload,
    parse_youranimes_html,
    parse_yuc_html,
)


FIXTURES = Path(__file__).parent / "fixtures"


class SourceParserTests(unittest.TestCase):
    def test_empty_translation_list_does_not_crash(self):
        records = parse_bgmlist_payload({"items": [{"title": "Test", "titleTranslate": {"zh-Hans": []},
            "sites": [{"site": "bangumi", "id": "1"}]}]})
        self.assertEqual(records[0].title_cn, "")

    def test_bangumi_maps_region_type_and_ids(self) -> None:
        payload = json.loads((FIXTURES / "bangumi.json").read_text(encoding="utf-8"))
        records = parse_bangumi_payload(payload)
        self.assertEqual(records[0].bangumi_id, 101)
        self.assertEqual(records[0].region, "jp")
        self.assertEqual(records[0].item_type, "tv")

    def test_bangumi_proxy_is_normalized_from_one_url_setting(self) -> None:
        from astrbot_plugin_anime.sources.bangumi import BangumiAdapter

        self.assertEqual(
            BangumiAdapter(None, proxy_url="http://192.168.0.2:7890").proxy_url,
            "http://192.168.0.2:7890",
        )
        self.assertIsNone(BangumiAdapter(None, proxy_url="").proxy_url)

    def test_bangumi_can_exclude_r18_records(self) -> None:
        payload = {"data": [
            {"id": 1, "type": 2, "platform": "TV", "name": "Safe", "date": "2026-10-01", "meta_tags": ["日本"]},
            {"id": 2, "type": 2, "platform": "TV", "name": "Adult", "date": "2026-10-02", "meta_tags": ["日本", "R18"]},
        ]}
        self.assertEqual([item.title for item in parse_bangumi_payload(payload, exclude_r18=True)], ["Safe"])

    def test_bgmlist_maps_structured_broadcast(self) -> None:
        payload = json.loads((FIXTURES / "bgmlist.json").read_text(encoding="utf-8"))
        records = parse_bgmlist_payload(payload)
        self.assertEqual(records[0].bangumi_id, 101)
        self.assertEqual(records[0].schedules[0].interval_days, 7)

    def test_yuc_parses_extended_japanese_clock(self) -> None:
        html = (FIXTURES / "yuc.html").read_text(encoding="utf-8")
        records = parse_yuc_html(html, "2026-10")
        self.assertEqual(records[0].title, "测试动画")
        self.assertEqual(records[0].schedules[0].hour, 25)
        self.assertEqual(records[0].schedules[0].start_date, "2026-10-05")

    def test_acgsecrets_parses_seasonal_schedule(self) -> None:
        html = (FIXTURES / "acgsecrets.html").read_text(encoding="utf-8")
        records = parse_acgsecrets_html(html, "2026-10")
        self.assertEqual(records[0].title, "測試動畫")
        self.assertEqual(records[0].schedules[0].hour, 25)

    def test_youranimes_parses_schedule(self) -> None:
        html = (FIXTURES / "youranimes.html").read_text(encoding="utf-8")
        records = parse_youranimes_html(html, "2026-10")
        self.assertEqual(records[0].title, "测试动画")
        self.assertEqual(records[0].schedules[0].hour, 24)

    def test_youranimes_jsonld_provides_bangumi_id_and_exact_japan_time(self) -> None:
        html = (FIXTURES / "youranimes-jsonld.html").read_text(encoding="utf-8")
        records = parse_youranimes_html(html, "2026-10")
        self.assertEqual(records[0].bangumi_id, 624085)
        self.assertEqual((records[0].schedules[0].weekday, records[0].schedules[0].hour, records[0].schedules[0].minute), (2, 21, 25))

    def test_acgsecrets_jsonld_converts_utc_start_to_japan_schedule(self) -> None:
        html = (FIXTURES / "acgsecrets-jsonld.html").read_text(encoding="utf-8")
        records = parse_acgsecrets_html(html, "2026-10")
        self.assertEqual(records[0].bangumi_id, 624085)
        self.assertEqual((records[0].schedules[0].weekday, records[0].schedules[0].hour, records[0].schedules[0].minute), (2, 21, 25))

    def test_unrecognized_page_does_not_become_fake_empty_success(self) -> None:
        self.assertEqual(parse_yuc_html("<html><body>blocked</body></html>"), [])
        self.assertEqual(parse_acgsecrets_html("<html><body>blocked</body></html>"), [])
        self.assertEqual(parse_youranimes_html("<html><body>blocked</body></html>"), [])


if __name__ == "__main__":
    unittest.main()
