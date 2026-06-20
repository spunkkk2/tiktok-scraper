from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tiktok_scraper import api
from tiktok_scraper.cli import build_parser, run
from tiktok_scraper.scraper import TikTokScraper


POST = {
    "id": "123",
    "desc": "hello @friend",
    "createTime": 1602212662,
    "video": {
        "id": "secret",
        "height": 1024,
        "width": 576,
        "duration": 15,
        "ratio": "720p",
        "cover": "cover.jpg",
        "originCover": "origin.jpg",
        "dynamicCover": "dynamic.jpg",
        "playAddr": "https://example.com/play.mp4",
        "downloadAddr": "https://example.com/download.mp4",
    },
    "author": {
        "id": "author-id",
        "uniqueId": "author",
        "nickname": "Author",
        "avatarLarger": "avatar.jpg",
        "signature": "bio",
        "verified": True,
        "secUid": "sec",
        "secret": False,
    },
    "music": {
        "id": "music-id",
        "title": "song",
        "authorName": "artist",
        "original": True,
        "album": "album",
        "playUrl": "https://example.com/song.mp3",
        "coverThumb": "thumb.jpg",
        "coverMedium": "medium.jpg",
        "coverLarge": "large.jpg",
        "duration": 15,
    },
    "stats": {"diggCount": 1, "shareCount": 2, "playCount": 3, "commentCount": 4},
    "authorStats": {"followingCount": 5, "followerCount": 6, "heartCount": 7, "videoCount": 8, "diggCount": 9},
    "challenges": [{"id": "tag-id", "title": "tag", "desc": "tag desc", "coverLarger": "tag.jpg"}],
    "effectStickers": [{"ID": "effect-id", "name": "effect"}],
    "duetEnabled": True,
    "stitchEnabled": False,
    "duetInfo": {"duetFromId": "0"},
}


class FakeScraper(TikTokScraper):
    def request(self, **kwargs):
        uri = kwargs["uri"]
        if uri.startswith("https://www.tiktok.com/@"):
            return (
                '<script id="__NEXT_DATA__" type="application/json">'
                + json.dumps({"props": {"pageProps": {"itemInfo": {"itemStruct": POST}}}})
                + "</script>"
            )
        if "item_list" in uri:
            return {"statusCode": 0, "itemList": [POST], "hasMore": False, "maxCursor": "0"}
        return {}


class ScraperTest(unittest.TestCase):
    def test_missing_input_raises(self) -> None:
        scraper = TikTokScraper(type="user", input="")
        with self.assertRaisesRegex(ValueError, "Missing input"):
            scraper.scrape()

    def test_collect_posts_normalizes_shape(self) -> None:
        scraper = TikTokScraper(type="user", input="author", number=1)
        result = scraper.collect_posts([POST])
        self.assertTrue(result["done"])
        item = scraper.collector[0]
        self.assertEqual(item["id"], "123")
        self.assertEqual(item["authorMeta"]["name"], "author")
        self.assertEqual(item["musicMeta"]["musicId"], "music-id")
        self.assertEqual(item["mentions"], ["@friend"])
        self.assertEqual(item["hashtags"][0]["name"], "tag")

    def test_get_video_meta_from_html(self) -> None:
        scraper = FakeScraper(type="video_meta", input="https://www.tiktok.com/@author/video/123")
        item = scraper.get_video_meta()
        self.assertEqual(item["id"], "123")
        self.assertEqual(item["videoUrl"], "https://example.com/play.mp4")
        self.assertEqual(item["videoMeta"]["ratio"], "720p")

    def test_save_metadata_json_and_csv(self) -> None:
        scraper = TikTokScraper(type="user", input="author", filetype="all")
        scraper.collect_posts([POST])
        with tempfile.TemporaryDirectory() as tmp:
            json_path = str(Path(tmp, "posts.json"))
            csv_path = str(Path(tmp, "posts.csv"))
            scraper.save_metadata(json_path=json_path, csv_path=csv_path)
            self.assertEqual(json.loads(Path(json_path).read_text())[0]["id"], "123")
            self.assertIn("authorMeta.name", Path(csv_path).read_text())

    def test_history_remove_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            item_file = Path(tmp, "author.json")
            item_file.write_text("[]", encoding="utf-8")
            Path(tmp, "tiktok_history.json").write_text(
                json.dumps({"user_author": {"file_location": str(item_file), "type": "user", "input": "author"}}),
                encoding="utf-8",
            )
            result = api.history("", {"history_path": tmp, "remove": "all"})
            self.assertEqual(result["message"], "History was completely removed")
            self.assertFalse(item_file.exists())

    def test_cli_parses_userprofile(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["userprofile", "author"])
        self.assertEqual(args.command, "userprofile")
        self.assertEqual(args.id, "author")

    def test_from_file_batch_parser(self) -> None:
        with tempfile.NamedTemporaryFile("w", delete=False) as file:
            file.write("@author\n#python\nmusic:42\n")
            filename = file.name
        try:
            batch = api._batch_from_file(filename)
            self.assertEqual([item["type"] for item in batch], ["user", "hashtag", "music"])
        finally:
            Path(filename).unlink(missing_ok=True)


class CliValidationTest(unittest.TestCase):
    def test_video_defaults_to_csv_when_no_output_mode_is_set(self) -> None:
        class Stub:
            def __call__(self, input_value, options):
                return {"filetype": options["filetype"], "input": input_value}

        original = api.video
        api.video = Stub()
        try:
            args = build_parser().parse_args(["video", "https://www.tiktok.com/@a/video/1"])
            self.assertEqual(run(args)["filetype"], "csv")
        finally:
            api.video = original


if __name__ == "__main__":
    unittest.main()
