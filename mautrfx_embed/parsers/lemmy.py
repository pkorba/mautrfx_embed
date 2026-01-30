import re
from asyncio import AbstractEventLoop
from typing import Any

import markdown

from ..resources.datastructures import ForumPost, Media
from ..resources.utils import Utilities


class Lemmy:
    def __init__(self, loop: AbstractEventLoop, utils: Utilities):
        self.loop = loop
        self.utils = utils
        self.SPOILER_TAG = re.compile(r":::\sspoiler\s(.*?)\n(.*?)\n:::", flags=re.I | re.DOTALL)
        self.INSTANCE_NAME = re.compile(r"https://(www\.)?(.*?)/.*")
        self.EMPTY_LINK = re.compile(r"\[]\((.+?)\)")

    async def parse_preview(self, data: Any) -> ForumPost:
        if data.get("error"):
            raise ValueError("Bad response")

        # Comment
        if data.get("comment_view") is not None:
            data = data["comment_view"]
            return ForumPost(
                text=await self.loop.run_in_executor(
                    None,
                    self._parse_text,
                    data["comment"].get("content")
                ),
                markdown=await self.loop.run_in_executor(
                    None,
                    self._parse_markdown,
                    data["comment"].get("content")
                ),
                flair=None,
                sub=f"c/{data["community"]["name"]}",
                sub_url=data["community"]["actor_id"],
                title=data["post"]["name"],
                score=None,
                upvote_ratio=0,
                upvotes=await self.utils.parse_interaction(data["counts"]["upvotes"]),
                downvotes=await self.utils.parse_interaction(data["counts"]["downvotes"]),
                post_date=await self.utils.parse_date(data["comment"]["published"]),
                nsfw=data["post"]["nsfw"],
                spoiler=False,
                author=data["creator"]["name"],
                author_url=data["creator"]["actor_id"],
                url=data["comment"]["ap_id"],
                comments=data["counts"]["child_count"],
                photos=[],
                videos=[],
                qtype="lemmy",
                name=f"🐹 {self.INSTANCE_NAME.sub( r"\2", data["post"]["ap_id"])}",
                is_link="text/html" in data["post"].get("url_content_type", ""),
            )

        # Post
        data = data["post_view"]
        return ForumPost(
            text=await self.loop.run_in_executor(None, self._parse_text, data["post"].get("body")),
            markdown=await self.loop.run_in_executor(
                None,
                self._parse_markdown,
                data["post"].get("body")
            ),
            flair=None,
            sub=f"c/{data["community"]["name"]}",
            sub_url=data["community"]["actor_id"],
            title=data["post"]["name"],
            score=None,
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
            name=f"🐹 {self.INSTANCE_NAME.sub( r"\2", data["post"]["ap_id"])}",
            is_link="text/html" in data["post"].get("url_content_type", ""),
        )

    def _parse_text(self, text: str) -> str:
        if not text:
            return ""
        # Don't try to display inline images and replace faulty newlines
        text = text.replace("![", "[").replace("\\\n", "  \n")
        # For links with no alt text use the URL because they're not visible otherwise
        text = self.EMPTY_LINK.sub(r"[\1](\1)", text)
        # Fix custom spoiler tags
        text = self.SPOILER_TAG.sub(self._md_group, text)
        text = markdown.markdown(text, extensions=["tables", "fenced_code"], output_format="html")
        return text

    def _md_group(self, match) -> str:
        return (
            "<details>"
            f"<summary>{match.group(1)} </summary>"
            f"{markdown.markdown(
                match.group(2),
                extensions=['tables', 'fenced_code'],
                output_format='html'
            )}"
            "</details>"
        )

    def _parse_markdown(self, text: str) -> str:
        if not text:
            return ""
        # Fix custom spoiler tags
        text = self.SPOILER_TAG.sub(r"[\1] ||\2||", text)
        # Don't try to display inline images and replace faulty newlines
        text = text.replace("![", "[").replace("\\\n", "\n  ")
        # For links with no alt text use the URL because they're not visible otherwise
        text = self.EMPTY_LINK.sub(r"[\1](\1)", text)
        return text

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
