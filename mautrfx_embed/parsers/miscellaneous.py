from asyncio import AbstractEventLoop
from typing import Any

from lxml import html

from ..resources.datastructures import Post, Media


class Miscellaneous:
    def __init__(self, loop: AbstractEventLoop):
        self.loop = loop

    async def parse_instagram_preview(self, preview_raw: Any) -> Post:
        """
        Build a Post object for Instagram reels
        :param preview_url: URL to video
        :return: Post object
        """
        return await self.loop.run_in_executor(None, self._parse_instagram_preview, preview_raw)

    def _parse_instagram_preview(self, data: Any) -> Post:
        page = html.fromstring(data)
        if page is None:
            raise ValueError("Bad response")

        link = page.xpath("//link[@rel='canonical']/@href")
        description = page.xpath("//meta[@property='og:title']/@content")
        image = page.xpath("//meta[@name='twitter:image']/@content")
        video = page.xpath("//meta[@property='og:video']/@content")
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

        return Post(
            text=description[0] if description is not None else "",
            url=None,
            markdown=None,
            replies=None,
            reposts=None,
            likes=None,
            views=None,
            quotes=None,
            community_note=None,
            author_name="Instagram reel",
            author_screen_name="Instagram",
            author_url=link[0] if link is not None else "",
            post_date=None,
            photos=[],
            videos=videos,
            facets=[],
            poll=None,
            link=None,
            quote=None,
            translation=None,
            translation_lang=None,
            qtype="instagram",
            name="🖼️ Instagram",
            sensitive=False,
            spoiler_text=None
        )

    async def parse_tiktok_preview(self, preview_raw: Any) -> Post:
        """
        Build a Post object for TikTok videos
        :param preview_url: URL to video
        :return: Post object
        """
        return await self.loop.run_in_executor(None, self._parse_tiktok_preview, preview_raw)

    def _parse_tiktok_preview(self, data: Any) -> Post:
        page = html.fromstring(data)
        if page is None:
            raise ValueError("Bad response")

        title = page.xpath("//meta[@property='og:title']/@content")
        description = page.xpath("//meta[@property='og:description']/@content")
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

        return Post(
            text=description[0] if description is not None else "",
            url=None,
            markdown=None,
            replies=None,
            reposts=None,
            likes=None,
            views=None,
            quotes=None,
            community_note=None,
            author_name=title[0] if title is not None else "TikTok video",
            author_screen_name="TikTok",
            author_url=video,
            post_date=None,
            photos=[],
            videos=videos,
            facets=[],
            poll=None,
            link=None,
            quote=None,
            translation=None,
            translation_lang=None,
            qtype="tiktok",
            name="🎞️ TikTok",
            sensitive=False,
            spoiler_text=None
        )
