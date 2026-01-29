from asyncio import AbstractEventLoop
from typing import Any

from lxml import html

from ..resources.datastructures import ForumPost, Media


class Instagram:
    def __init__(self, loop: AbstractEventLoop):
        self.loop = loop

    async def parse_preview(self, preview_raw: Any) -> ForumPost:
        """
        Build a Post object for Instagram reels
        :param preview_url: URL to video
        :return: Post object
        """
        return await self.loop.run_in_executor(None, self._parse_instagram_preview, preview_raw)

    def _parse_instagram_preview(self, data: Any) -> ForumPost:
        page = html.fromstring(data)
        if page is None:
            raise ValueError("Bad response")

        link = page.xpath("//link[@rel='canonical']/@href")
        desc = page.xpath("//meta[@property='og:title']/@content")
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

        return ForumPost(
            text=f"<p>{desc[0].replace('\n', '<br>')}</p>" if desc is not None else "",
            markdown=desc[0] if desc is not None else "",
            flair=None,
            sub=None,
            title="Instagram reel",
            score=None,
            upvote_ratio=0,
            upvotes=None,
            downvotes=None,
            post_date=None,
            nsfw=False,
            spoiler=False,
            author=None,
            url=link[0] if link is not None else "",
            comments=0,
            photos=[],
            videos=videos,
            qtype="instagram",
            name="🖼️ Instagram",
            is_link=False
        )
