from tiktok_scraper import get_video_meta, hashtag, user


def main() -> None:
    user_feed = user("tiktok", {"number": 5, "filetype": "json"})
    print(f"Collected {len(user_feed['collector'])} user posts")

    hashtag_feed = hashtag("python", {"number": 5})
    print(f"Collected {len(hashtag_feed['collector'])} hashtag posts")

    video_meta = get_video_meta("https://www.tiktok.com/@tiktok/video/6807491984882765062")
    print(video_meta["collector"][0]["id"])


if __name__ == "__main__":
    main()
