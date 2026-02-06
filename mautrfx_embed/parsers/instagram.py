from asyncio import AbstractEventLoop
from typing import Any

from lxml import html

from ..resources.datastructures import ForumPost, Media
from ..resources.utils import Utilities


class Instagram:
    def __init__(self, loop: AbstractEventLoop, utils: Utilities):
        self.loop = loop
        self.utils = utils

    async def parse_preview(self, data: Any) -> ForumPost:
        """
        Build a ForumPost object for Instagram reels
        :param data: Website content of canonical URL
        :return: ForumPost object
        """
        link, desc, image = await self.loop.run_in_executor(None, self._parse_canonical_page, data)
        if not link:
            raise ValueError("Bad response - missing canonical URL")

        video_url = await self.utils.get_location_header(link.replace("instagram", "kkinstagram"))
        # kkinstagram returns canonical URL if unsuccessful
        if not video_url or "www.instagram.com/reel" in video_url:
            raise ValueError("Bad response - missing video URL")

        videos = [
            Media(
                width=0,
                height=0,
                url=video_url,
                thumbnail_url=image,
                filetype="v"
            )
        ]

        return ForumPost(
            text=f"<p>{desc.replace('\n', '<br>')}</p>" if desc else "",
            text_md=desc,
            flair=None,
            sub=None,
            sub_url=None,
            title="Instagram reel",
            score=None,
            upvote_ratio=0,
            upvotes=None,
            downvotes=None,
            post_date=None,
            nsfw=False,
            spoiler=False,
            author=None,
            author_url=None,
            url=link,
            comments=0,
            photos=[],
            videos=videos,
            qtype="instagram",
            name="🖼️ Instagram",
            is_link=False
        )

    def _parse_canonical_page(self, data: Any) -> tuple[str, str, str]:
        """
        Parse Instagram page and extrack link, description, and thumbnail from HTML
        :param data: Instagram page
        :return: link, description, thumbnail
        """
        page = html.fromstring(data)
        if page is None:
            raise ValueError("Bad response")

        link = page.xpath("//link[@rel='canonical']/@href")
        link = link[0] if link else ""
        desc = page.xpath("//meta[@property='og:title']/@content")
        desc = desc[0] if desc else ""
        image = page.xpath("//meta[@name='twitter:image']/@content")
        image = image[0] if image else ""
        return link, desc, image
