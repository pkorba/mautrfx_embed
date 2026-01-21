import re
import time
from asyncio import AbstractEventLoop
from typing import Any

import html2text

from ..resources.datastructures import Post, Media, Link, Poll, Choice
from ..resources.utils import Utilities


class Mastodon:
    def __init__(self, loop: AbstractEventLoop, utils: Utilities):
        self.loop = loop
        self.utils = utils

    async def parse_preview(self, preview_raw: Any) -> Post:
        """
        Parse JSON data from Mastodon API
        :param preview_raw: JSON data
        :return: Post object
        """
        error = preview_raw.get("error")
        if error is not None:
            raise ValueError("Bad response")

        content, md_text = await self.loop.run_in_executor(
            None,
            self._parse_text,
            preview_raw["content"]
        )
        videos, photos = await self._parse_media(preview_raw)
        return Post(
            text=content,
            url=None,
            markdown=md_text,
            replies=await self.utils.parse_interaction(preview_raw["replies_count"]),
            reposts=await self.utils.parse_interaction(preview_raw["reblogs_count"]),
            likes=await self.utils.parse_interaction(preview_raw["favourites_count"]),
            views=None,
            quotes=await self.utils.parse_interaction(preview_raw["quotes_count"]),
            community_note=None,
            author_name=preview_raw["account"]["display_name"],
            author_screen_name=preview_raw["account"]["username"],
            author_url=preview_raw["account"]["url"],
            post_date=await self.utils.parse_date(preview_raw["created_at"]),
            photos=photos,
            videos=videos,
            facets=[],
            poll=await self._parse_poll(preview_raw),
            link=await self._parse_link(preview_raw),
            quote=await self.parse_quote(preview_raw),
            translation=None,
            translation_lang=None,
            qtype="mastodon",
            name=f"🐘 {re.sub(r"https://(www\.)?(.*?)/.*", r"\2", preview_raw["url"])}",
            sensitive=preview_raw["sensitive"],
            spoiler_text=preview_raw["spoiler_text"]
        )

    async def parse_quote(self, data: Any) -> Post | None:
        """
        Parse JSON data of a quote post from Mastodon API
        :param data: JSON data of a quote post
        :return: Post object
        """
        quote = data.get("quote")
        if not quote:
            return None
        quote_text, md_quote_text = await self.loop.run_in_executor(
            None,
            self._parse_text,
            quote["quoted_status"]["content"]
        )
        q_videos, q_photos = await self._parse_media(quote["quoted_status"])
        return Post(
                text=quote_text,
                url=quote["quoted_status"]["url"],
                markdown=md_quote_text,
                replies=None,
                reposts=None,
                likes=None,
                views=None,
                quotes=await self.utils.parse_interaction(data["quotes_count"]),
                community_note=None,
                author_name=quote["quoted_status"]["account"]["display_name"],
                author_url=quote["quoted_status"]["account"]["url"],
                author_screen_name=quote["quoted_status"]["account"]["username"],
                post_date=None,
                photos=q_photos,
                videos=q_videos,
                facets=[],
                poll=await self._parse_poll(quote["quoted_status"]),
                link=await self._parse_link(quote["quoted_status"]),
                quote=None,
                translation=None,
                translation_lang=None,
                qtype="mastodon",
                name=f"🐘 {re.sub(
                    r"https://(www\.)?(.*?)/.*", r"\2", quote["quoted_status"]["url"]
                )}",
                sensitive=quote["quoted_status"]["sensitive"],
                spoiler_text=quote["quoted_status"]["spoiler_text"]
            )

    def _parse_text(self, text: str) -> tuple[str, str]:
        """
        Remove needless HTML tags from the content of Mastodon post
        :param text: text content of a post
        :return: tuple of cleaned HTML text and Markdown version of the same text
        """
        if not text:
            return "", ""

        # HTML
        # Remove inline quote, it's redundant
        content = re.sub(r"<p\sclass=\"quote-inline\">.*?</p>", "", text)
        # Remove invisible span
        content = re.sub(r"<span\sclass=\"invisible\">[^<>]*?</span>", "", content)
        # Replace ellipsis span with an actual ellipsis
        content = re.sub(r"<span\sclass=\"ellipsis\">([^<>]*?)</span>", r"\1...", content)
        # Remove the outmost paragraph to prevent too much whitespace in some clients
        content = content.removeprefix("<p>")
        content = content.removesuffix("</p>")

        # Markdown
        text_maker = html2text.HTML2Text()
        text_maker.body_width = 65536
        md_text = text_maker.handle(content)

        return content, md_text

    async def _parse_media(self, data: Any) -> tuple[list, list]:
        """
        Extract media attachments from JSON
        :param data: post's JSON from Mastodon API
        :return: tuple with two lists containing Media objects for videos and photos
        """
        media = data.get("media_attachments")
        photos: list[Media] = []
        videos: list[Media] = []
        if media is not None:
            for elem in media:
                if elem["type"] in ["video", "gifv", "audio"]:
                    metadata = elem["meta"].get("small")
                    if metadata is None:
                        metadata = elem["meta"].get("original")
                    video = Media(
                        width=metadata.get("width", 0) if metadata is not None else 0,
                        height=metadata.get("height", 0) if metadata is not None else 0,
                        url=elem["url"],
                        thumbnail_url=elem["preview_url"],
                        filetype="a" if elem["type"] == "audio" else "v"
                    )
                    videos.append(video)
                elif elem["type"] == "image":
                    photo = Media(
                        width=elem["meta"]["original"]["width"],
                        height=elem["meta"]["original"]["height"],
                        url=elem["url"],
                        thumbnail_url=elem["preview_url"],
                        filetype="p"
                    )
                    photos.append(photo)
        return videos, photos

    async def _parse_link(self, data: Any) -> Link | None:
        """
        Extract link data from JSON
        :param data: post's JSON from Mastodon API
        :return: Link object
        """
        card = data.get("card")
        if card is not None:
            return Link(
                title=card["title"],
                description=card["description"],
                url=card["url"]
            )
        return None

    async def _parse_poll(self, data: Any) -> Poll:
        """
        Extract poll data from JSON
        :param data: post's JSON from Mastodon API
        :return: Poll object
        """
        poll = None
        poll_raw = data.get("poll")
        if poll_raw is not None:
            choices: list[Choice] = []
            for option in poll_raw["options"]:
                choice = Choice(
                    label=option["title"],
                    votes_count=option["votes_count"],
                    percentage=round(option["votes_count"] / poll_raw["voters_count"] * 100, 1),
                )
                choices.append(choice)
            if not poll_raw["expired"]:
                expires_at = await self.utils.parse_date(poll_raw["expires_at"])
                status = await self._get_poll_status(expires_at)
            else:
                status = "Final results"
            poll = Poll(
                ends_at=poll_raw["expires_at"],
                status=status,
                total_voters=poll_raw["voters_count"],
                choices=choices
            )
        return poll

    async def _get_poll_status(self, expires_at: int) -> str:
        """
        Calculate time difference between current time and poll's expiration time
        :param expires_at: seconds since Epoch marking the end time when poll closes
        :return: human friendly string indicating how much time is left until the poll closes
        """
        time_diff = expires_at - int(time.time())
        d = divmod(time_diff, 86400)  # days
        h = divmod(d[1], 3600)  # hours
        m = divmod(h[1], 60)  # minutes
        s = m[1]  # seconds
        if d[0]:
            status = f"{d[0]} days left"
        elif h[0]:
            status = f"{h[0] + 1} hours left"
        elif m[0]:
            status = f"{m[0] + 1} minutes left"
        else:
            status = f"{s + 1} seconds left"
        return status
