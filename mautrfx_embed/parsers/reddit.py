import html
import mimetypes
from typing import Any

from ..resources.datastructures import ForumPost, Media
from ..resources.utils import Utilities


class Reddit:
    def __init__(self, utils: Utilities):
        self.utils = utils

    async def parse_preview(self, data: Any) -> ForumPost:
        if not data["data"]["children"]:
            raise ValueError("Bad response")

        # Comment permalink
        if data["data"]["children"][0]["kind"] == "t1":
            data = data["data"]["children"][0]["data"]

            return ForumPost(
                text=await self._parse_text(data.get("body_html", "")),
                markdown=data["body"],
                flair=None,
                sub=data["subreddit_name_prefixed"],
                title="Comment permalink",
                score=await self.utils.parse_interaction(data["score"]),
                upvote_ratio=0,
                upvotes=await self.utils.parse_interaction(data["ups"]),
                downvotes=await self.utils.parse_interaction(data["downs"]),
                post_date=int(data["created"]),
                nsfw=False,
                spoiler=False,
                author=data["author"],
                url=f"https://www.reddit.com{data["permalink"]}",
                comments=0,
                photos=[],
                videos=[],
                qtype="reddit",
                name="👽 Reddit"
            )

        # Post
        data = data["data"]["children"][0]["data"]
        return ForumPost(
            text=await self._parse_text(data.get("selftext_html", "")),
            markdown=data["selftext"],
            flair=data["link_flair_text"],
            sub=data["subreddit_name_prefixed"],
            title=data["title"],
            score=await self.utils.parse_interaction(data["score"]),
            upvote_ratio=int(data["upvote_ratio"] * 100),
            upvotes=await self.utils.parse_interaction(data["ups"]),
            downvotes=await self.utils.parse_interaction(data["downs"]),
            post_date=int(data["created"]),
            nsfw=data["over_18"],
            spoiler=data["spoiler"],
            author=data["author"],
            url=data["url"],
            comments=data["num_comments"],
            photos=await self._parse_photos(data),
            videos=await self._parse_videos(data),
            qtype="reddit",
            name="👽 Reddit"
        )

    async def _parse_text(self, text: str) -> str:
        if not text:
            return ""
        text = text.replace("&lt;!-- SC_OFF --&gt;", "").replace("&lt;!-- SC_ON --&gt;", "")
        return html.unescape(text)

    async def _parse_photos(self, data: Any) -> list[Media]:
        photos: list[Media] = []
        single = data.get("post_hint") == "image"
        if single:
            photo = await self._parse_preview(data)
            photos.append(photo)
        elif data.get("gallery_data"):
            gallery = data["gallery_data"]["items"]
            previews = data["media_metadata"]
            for item in gallery:
                image = previews[item["media_id"]]
                mime = image["m"]
                ext = mimetypes.guess_extension(mime)
                photo = None
                # Choose the first thumbnail that fits user requirements
                # (thumbnails in the list are sorted by size from the smallest to the largest)
                for preview in image["p"]:
                    if (
                            preview["x"] > self.utils.config["thumbnail_small"]
                            or preview["y"] > self.utils.config["thumbnail_small"]
                    ):
                        photo = Media(
                            width=preview["x"],
                            height=preview["y"],
                            url=f"https://i.redd.it/{item["media_id"]}{ext}",
                            thumbnail_url=preview["u"].replace("&amp;", "&"),
                            filetype="p"
                        )
                        break
                # If all thumbnails are smaller than requested, choose the biggest one
                if not photo:
                    photo = Media(
                        width=image["p"][-1]["x"],
                        height=image["p"][-1]["y"],
                        url=f"https://i.redd.it/{item["media_id"]}{ext}",
                        thumbnail_url=image["p"][-1]["u"].replace("&amp;", "&"),
                        filetype="p"
                    )
                photos.append(photo)
        return photos

    async def _parse_preview(self, data: Any) -> Media:
        photo = None
        previews = data["preview"]["images"][0]["resolutions"]
        for preview in previews:
            if (
                    preview["width"] > self.utils.config["thumbnail_large"]
                    or preview["height"] > self.utils.config["thumbnail_large"]
            ):
                photo = Media(
                    width=preview["width"],
                    height=preview["height"],
                    url=data["url"],
                    thumbnail_url=preview["url"].replace("&amp;", "&"),
                    filetype="p"
                )
                break
        # If all thumbnails are smaller than requested, choose the biggest one
        if not photo:
            photo = Media(
                width=previews[-1]["width"],
                height=previews[-1]["height"],
                url=data["url"],
                thumbnail_url=previews[-1]["url"].replace("&amp;", "&"),
                filetype="p"
            )
        return photo

    async def _parse_videos(self, data: Any) -> list[Media]:
        videos: list[Media] = []
        if not data["is_video"]:
            return videos
        video = await self._parse_preview(data)
        if video:
            video.url = self.utils.config["player"] + data["media"]["reddit_video"]["hls_url"]
            video.filetype = "v"
        else:
            video = Media(
                width=0,
                height=0,
                url= self.utils.config["player"] + data["media"]["reddit_video"]["hls_url"],
                thumbnail_url=None,
                filetype="v"
            )
        videos.append(video)
        return videos
