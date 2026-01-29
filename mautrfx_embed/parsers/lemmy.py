import re
from typing import Any

from ..resources.datastructures import ForumPost, Media
from ..resources.utils import Utilities


class Lemmy:
    def __init__(self, utils: Utilities):
        self.utils = utils

    async def parse_preview(self, data: Any) -> ForumPost:
        if data.get("error"):
            raise ValueError("Bad response")

        # Post
        data = data["post_view"]
        return ForumPost(
            text=data["post"].get("body"),
            markdown=data["post"].get("body"),
            flair=None,
            sub=f"c/{data["community"]["name"]}",
            sub_url=data["community"]["actor_id"],
            title=data["post"]["name"],
            score=await self.utils.parse_interaction(data["counts"]["score"]),
            upvote_ratio=0,
            upvotes=await self.utils.parse_interaction(data["counts"]["upvotes"]),
            downvotes=await self.utils.parse_interaction(data["counts"]["downvotes"]),
            post_date=await self.utils.parse_date(data["post"]["published"]),
            nsfw=data["post"]["nsfw"],
            spoiler=False,
            author=data["creator"]["name"],
            author_url=data["creator"]["actor_id"],
            url=(
                data["post"]["url"] if data["post"].get("url") is not None
                else data["post"]["ap_id"]
            ),
            comments=data["counts"]["comments"],
            photos=await self._parse_photos(data),
            videos=await self._parse_videos(data),
            qtype="lemmy",
            name=f"🐹 {re.sub(r"https://(www\.)?(.*?)/.*", r"\2", data["post"]["ap_id"])}",
            is_link="text/html" in data["post"].get("url_content_type", ""),
        )

    async def _parse_text(self, text: str) -> str:
        pass

    async def _parse_markdown(self, text: str) -> str:
        if not text:
            return ""
        return text.replace("&gt;!", "||").replace("!&lt;", "||")

    async def _parse_photos(self, data: Any) -> list[Media]:
        photos: list[Media] = []
        details = data.get("image_details")
        if details:
            photo = Media(
                width=details["width"],
                height=details["height"],
                url=details["link"],
                thumbnail_url=details["link"],
                filetype="p"
            )
            photos.append(photo)
        else:
            thumbnail = await self._parse_thumbnail(data)
            if thumbnail:
                photos.append(thumbnail)
        return photos

    async def _parse_thumbnail(self, data: Any) -> Media | None:
        photo = None
        thumbnail_url = data["post"].get("thumbnail_url")
        if thumbnail_url:
            photo = Media(
                width=0,
                height=0,
                url=data["post"]["url"],
                thumbnail_url=thumbnail_url,
                filetype="p"
            )
        return photo

    async def _parse_videos(self, data: Any) -> list[Media]:
        videos: list[Media] = []
        is_video = data["post"].get("url_content_type", "") in (
            "video/x-msvideo",
            "video/mp4",
            "video/mpeg",
            "video/ogg",
            "video/webm",
            "video/mp2t",
            "video/3gpp",
            "video/3gpp2",
            "video/matroska"
        )
        if is_video:
            video = Media(
                width=0,
                height=0,
                url=data["post"]["url"],
                thumbnail_url=data["post"].get("thumbnail_url"),
                filetype="v"
            )
            videos.append(video)
        return videos
