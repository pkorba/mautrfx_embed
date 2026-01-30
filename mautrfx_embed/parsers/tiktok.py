from asyncio import AbstractEventLoop
from typing import Any

from lxml import html

from ..resources.datastructures import ForumPost, Media


class Tiktok:
    def __init__(self, loop: AbstractEventLoop):
        self.loop = loop

    async def parse_preview(self, preview_raw: Any) -> ForumPost:
        """
        Build a Post object for TikTok videos
        :param preview_url: URL to video
        :return: Post object
        """
        return await self.loop.run_in_executor(None, self._parse_tiktok_preview, preview_raw)

    def _parse_tiktok_preview(self, data: Any) -> ForumPost:
        page = html.fromstring(data)
        if page is None:
            raise ValueError("Bad response")

        title = page.xpath("//meta[@property='og:title']/@content")
        desc = page.xpath("//meta[@property='og:description']/@content")
        image = page.xpath("//meta[@property='og:image']/@content")
        video = page.xpath("//meta[@name='lark:url:video_iframe_url']/@content")
        video = video[0] if video is not None else None
        if video is None:
            raise ValueError("No video found")
        videos = [
            Media(
                width=0,
                height=0,
                url=video,
                thumbnail_url=image[0] if image is not None else None,
                filetype="v"
            )
        ]

        return ForumPost(
            text=f"<p>{desc[0].replace('\n', '<br>')}</p>" if desc is not None else "",
            markdown=desc[0] if desc is not None else "",
            flair=None,
            sub=None,
            sub_url=None,
            title=title[0] if title is not None else "TikTok video",
            score=None,
            upvote_ratio=0,
            upvotes=None,
            downvotes=None,
            post_date=None,
            nsfw=False,
            spoiler=False,
            author=None,
            author_url=None,
            url=video,
            comments=0,
            photos=[],
            videos=videos,
            qtype="tiktok",
            name="🎞️ TikTok",
            is_link=False
        )
