import asyncio
import mimetypes
import re
import time
from asyncio import AbstractEventLoop
from typing import Any

import html2text

from ..resources.datastructures import BlogPost, Media, Link, Poll, Choice
from ..resources.utils import Utilities


class Mastodon:
    INSTANCE_NAME = re.compile(r"https://(www\.)?(?P<base_url>.+?)/.*")
    QUOTE_PARAGRAPH = re.compile(r"<p\sclass=\"quote-inline\">.*?</p>")
    INVISIBLE_SPAN = re.compile(r"<span\sclass=\"invisible\">[^<>]*?</span>")
    ELLIPSIS_SPAN = re.compile(r"<span\sclass=\"ellipsis\">([^<>]*?)</span>")

    def __init__(self, loop: AbstractEventLoop, utils: Utilities):
        self.loop = loop
        self.utils = utils

    async def parse_preview(self, data: Any) -> BlogPost:
        """
        Parse JSON data from Mastodon API
        :param data: JSON data
        :return: Post object
        """
        error = data.get("error")
        if error is not None:
            raise ValueError("Bad response")

        content = await self.loop.run_in_executor(None, self._parse_text, data["content"])
        md_text = await self.loop.run_in_executor(None, self._parse_markdown, content)
        content = await self._replace_emoji_codes(data["emojis"], content)

        return BlogPost(
            text=content,
            url=None,
            text_md=md_text,
            replies=await self.utils.parse_interaction(data["replies_count"]),
            reposts=await self.utils.parse_interaction(data["reblogs_count"]),
            likes=await self.utils.parse_interaction(data["favourites_count"]),
            views=None,
            quotes=await self.utils.parse_interaction(data.get("quotes_count")),
            community_note=None,
            author_name=await self._replace_emoji_codes(
                data["account"]["emojis"],
                data["account"]["display_name"]
            ),
            author_name_md=data["account"]["display_name"],
            author_screen_name=data["account"]["username"],
            author_url=data["account"]["url"],
            post_date=await self.utils.parse_date(data["created_at"]),
            photos=await self._parse_photos(data),
            videos=await self._parse_videos(data),
            facets=[],
            poll=await self._parse_poll(data),
            link=await self._parse_link(data),
            quote=await self.parse_quote(data),
            translation=None,
            translation_lang=None,
            qtype="mastodon",
            name=f"🐘 {self.INSTANCE_NAME.sub(r"\g<base_url>", data["url"])}",
            sensitive=data["sensitive"],
            spoiler_text=data["spoiler_text"]
        )

    async def parse_quote(self, data: Any) -> BlogPost | None:
        """
        Parse JSON data of a quote post from Mastodon API
        :param data: JSON data of a quote post
        :return: Post object
        """
        quote = data.get("quote")
        if not quote:
            return None
        quote_text = await self.loop.run_in_executor(
            None,
            self._parse_text,
            quote["quoted_status"]["content"]
        )
        md_quote_text = await self.loop.run_in_executor(None, self._parse_markdown, quote_text)

        quote_text = await self._replace_emoji_codes(
            quote["quoted_status"]["emojis"],
            quote_text
        )

        return BlogPost(
                text=quote_text,
                url=quote["quoted_status"]["url"],
                text_md=md_quote_text,
                replies=None,
                reposts=None,
                likes=None,
                views=None,
                quotes=None,
                community_note=None,
                author_name=await self._replace_emoji_codes(
                    quote["quoted_status"]["account"]["emojis"],
                    quote["quoted_status"]["account"]["display_name"]
                ),
                author_name_md=quote["quoted_status"]["account"]["display_name"],
                author_url=quote["quoted_status"]["account"]["url"],
                author_screen_name=quote["quoted_status"]["account"]["username"],
                post_date=None,
                photos=await self._parse_photos(quote["quoted_status"]),
                videos=await self._parse_videos(quote["quoted_status"]),
                facets=[],
                poll=await self._parse_poll(quote["quoted_status"]),
                link=await self._parse_link(quote["quoted_status"]),
                quote=await self._get_child_quote_info(quote["quoted_status"]["quote"]),
                translation=None,
                translation_lang=None,
                qtype="mastodon",
                name=f"🐘 {self.INSTANCE_NAME.sub(r"\g<base_url>", quote["quoted_status"]["url"])}",
                sensitive=quote["quoted_status"]["sensitive"],
                spoiler_text=quote["quoted_status"]["spoiler_text"]
            )

    def _parse_text(self, text: str) -> str:
        """
        Remove needless HTML tags from the content of Mastodon post
        :param text: text content of a post
        :return: tuple of cleaned HTML text and Markdown version of the same text
        """
        if not text:
            return ""
        # Remove inline quote, it's redundant
        content = self.QUOTE_PARAGRAPH.sub("", text)
        # Remove invisible span
        content = self.INVISIBLE_SPAN.sub("", content)
        # Replace ellipsis span with an actual ellipsis
        content = self.ELLIPSIS_SPAN.sub(r"\1...", content)
        # Remove the outmost paragraph to prevent too much whitespace in some clients
        content = content.removeprefix("<p>")
        content = content.removesuffix("</p>")
        return content

    def _parse_markdown(self, text: str) -> str:
        if not text:
            return ""
        # Markdown
        text_maker = html2text.HTML2Text()
        text_maker.body_width = 65536
        md_text = text_maker.handle(text).strip()
        return md_text

    async def _parse_videos(self, data: Any) -> list[Media]:
        """
        Extract video attachments from JSON
        :param data: post's JSON from Mastodon API
        :return: list containing Media video objects
        """
        videos: list[Media] = []
        media = data.get("media_attachments")
        if not media:
            return videos

        for elem in media:
            if elem["type"] not in ["video", "gifv", "audio"]:
                continue
            metadata = elem["meta"].get("small")
            if not metadata:
                metadata = elem["meta"].get("original")
            video = Media(
                width=metadata.get("width", 0),
                height=metadata.get("height", 0),
                url=elem["url"],
                thumbnail_url=elem["preview_url"],
                filetype="a" if elem["type"] == "audio" else "v"
            )
            videos.append(video)
        return videos

    async def _parse_photos(self, data: Any) -> list[Media]:
        """
        Extract photo attachments from JSON
        :param data: post's JSON from Mastodon API
        :return: list containing Media photo objects
        """
        photos: list[Media] = []
        media = data.get("media_attachments")
        if not media:
            return photos

        for elem in media:
            if elem["type"] != "image":
                continue
            metadata = elem["meta"].get("small")
            thumb = elem["preview_url"]
            if (
                not metadata or (
                    len(media) == 1 and
                    max(metadata.get("width", 0),
                        metadata.get("height", 0)) < self.utils.config["thumbnail_large"]
                )
                or (
                    len(media) > 1 and
                    max(metadata.get("width", 0),
                        metadata.get("height", 0)) < self.utils.config["thumbnail_small"]
                )
            ):
                metadata = elem["meta"].get("original")
                thumb = elem["url"]
            photo = Media(
                width=metadata.get("width", 0),
                height=metadata.get("height", 0),
                url=elem["url"],
                thumbnail_url=thumb,
                filetype="p"
            )
            photos.append(photo)
        return photos

    async def _parse_link(self, data: Any) -> Link | None:
        """
        Extract link data from JSON
        :param data: post's JSON from Mastodon API
        :return: Link object
        """
        card = data.get("card")
        if card:
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
        if poll_raw:
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
        time_diff = time_diff if time_diff > 0 else 0
        d = divmod(time_diff, 86400)  # days
        h = divmod(d[1], 3600)  # hours
        m = divmod(h[1], 60)  # minutes
        s = m[1]  # seconds
        if d[0]:
            status = f"{d[0]} day{"s" if d[0] > 1 else ""} left"
        elif h[0]:
            round_up = 1 if m[0] > 30 else 0
            status = f"{h[0] + round_up} hour{"s" if h[0] + round_up > 1 else ""} left"
        elif m[0]:
            status = f"{m[0] + 1} minutes left"
        else:
            status = f"{s + 1} second{"s" if s > 0 else ""} left"
        return status

    async def _replace_emoji_codes(self, emojis: list[Any], text: str) -> str:
        """
        Replace emoji shortcodes with emoji images
        :param emojis: list of objects with emoji data
        :param text: text that contains emoji shortcodes
        :return: text with emoji shortcodes replaced with emoji images
        """
        for emoji in emojis:
            image = await self.utils.download_image(emoji["url"])
            if not image:
                continue
            mime = mimetypes.guess_type(emoji["url"])
            if not mime:
                continue
            mime = mime[0]
            extension = mimetypes.guess_extension(mime)
            image_mxc = await self.utils.upload_media(image, mime, f"emoji{extension}")
            if not image_mxc:
                continue
            text = text.replace(
                f":{emoji["shortcode"]}:",
                f"<img src=\"{image_mxc}\" alt=\":{emoji["shortcode"]}:\" height=\"24\" />"
            )
            # To prevent running into ratelimit
            await asyncio.sleep(0.2)

        return text

    async def _get_child_quote_info(self, quote: Any) -> BlogPost | None:
        if not quote:
            return None

        return BlogPost(
                text="<b>Quoted another post</b>",
                url=None,
                text_md="**Quoted another post**",
                replies=None,
                reposts=None,
                likes=None,
                views=None,
                quotes=None,
                community_note=None,
                author_name=None,
                author_name_md=None,
                author_url=None,
                author_screen_name=None,
                post_date=None,
                photos=[],
                videos=[],
                facets=[],
                poll=None,
                link=None,
                quote=None,
                translation=None,
                translation_lang=None,
                qtype="mastodon",
                name=None,
                sensitive=False,
                spoiler_text=None
            )
