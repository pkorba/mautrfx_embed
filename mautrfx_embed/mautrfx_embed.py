import asyncio
import io
import re
import time
from time import strftime, localtime, strptime, mktime
from typing import Any, Type

import html2text
from PIL import Image
from PIL import UnidentifiedImageError
from aiohttp import ClientError, ClientTimeout
from mautrix.errors import MatrixResponseError
from mautrix.types import TextMessageEventContent, MessageType, Format
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from maubot import Plugin, MessageEvent
from maubot.handlers import command

from .resources.datastructures import Post, Photo, Video, Facet, Link, Poll, Choice


class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("nitter_redirect")
        helper.copy("nitter_url")
        helper.copy("bsky_player")


class MautrFxEmbedBot(Plugin):
    headers = {
        "User-Agent": "MautrFxEmbedBot/1.0.0"
    }
    twitter_domains = [
        "x.com",
        "twitter.com",
        "fixupx.com",
        "fxtwitter.com",
        "fixvx.com",
        "vxtwitter.com",
        "fixvtwitter.com"
        "stupidpenisx.com",
        "girlcockx.com",
        "nitter.net",
        "xcancel.com",
        "nitter.poast.org",
        "nitter.privacyredirect.com",
        "lightbrd.com",
        "nitter.space",
        "nitter.tierkoetter.com",
        "nuku.trabun.org",
        "nitter.catsarch.com"
    ]
    bsky_domains = [
        "bsky.app/profile",
        "fxbsky.app/profile",
        "skyview.social/?url=https://bsky.app/profile/",
        "skyview.social/?url=bsky.app/profile/"
    ]
    instagram_domains = [
        "www.instagram.com/reel",
        "instagram.com/reel",
        "www.kkinstagram.com/reel",
        "kkinstagram.com/reel",
        "www.uuinstagram.com/reel",
        "uuinstagram.com/reel"
    ]

    async def start(self) -> None:
        await super().start()
        self.config.load_and_update()

    @command.passive(r"(https?://\S+)", multiple=True)
    async def embed(self, evt: MessageEvent, matches: list[tuple[str, str]]) -> None:
        if evt.sender == self.client.mxid:
            return
        canonical_urls = await self._get_canonical_urls(matches)
        if not canonical_urls:
            return
        await evt.mark_read()

        previews = []
        for url in canonical_urls:
            if "kkinstagram.com/reel" in url:
                preview_raw = await self._get_instagram_preview(url)
                # For private reels kkinstagram returns original reel URL
                if "https://www.instagram.com/reel" in preview_raw:
                    continue
            else:
                preview_raw = await self._get_preview(url)
            if preview_raw:
                try:
                    preview = await self._parse_preview(preview_raw, url)
                    previews.append(preview)
                except ValueError as e:
                    self.log.error(f"Error parsing preview: {e}")
        for preview in previews:
            content = await self._prepare_message(preview)
            await evt.respond(content)

    async def _get_instagram_preview(self, url: str) -> str:
        """
        Get url to Instagram video preview.
        :param url: source URL
        :return: Instagram video preview url
        """
        # Use Discord's user agent because kkinstagram serves different responses based on it
        headers = {
            'User-Agent': "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)"
        }
        timeout = ClientTimeout(total=20)
        try:
            response = await self.http.get(
                url,
                headers=headers,
                timeout=timeout,
                raise_for_status=True,
                allow_redirects=False)
            # Contains direct URL to the video
            return response.headers["location"]
        except ClientError as e:
            self.log.error(f"Connection failed: {e}")
            return ""
        except KeyError as e:
            self.log.error(f"Missing 'location' header: {e}")
            return ""

    async def _parse_preview(self, preview_raw: Any, url: str) -> Post:
        if "api.fxtwitter.com" in url:
            return await self._parse_twitter_preview(preview_raw)
        if "api.bsky.app" in url:
            return await self._parse_bsky_preview(preview_raw)
        if "www.kkinstagram.com/reel" in url:
            return await self._parse_instagram_preview(preview_raw)
        return await self._parse_mastodon_preview(preview_raw)

    async def _parse_instagram_preview(self, preview_url: str) -> Post:
        return Post(
            text=None,
            url=None,
            markdown=None,
            replies=None,
            reposts=None,
            likes=None,
            views=None,
            community_note=None,
            author_name="Video link",
            author_screen_name="Instagram",
            author_url=preview_url,
            post_date=None,
            photos=[],
            videos=[],
            facets=[],
            poll=None,
            link=None,
            quote=None,
            translation=None,
            translation_lang=None,
            qtype="instagram"
        )

    async def _parse_mastodon_preview(self, preview_raw: Any) -> Post:
        """
        Parse JSON data from Mastodon API
        :param preview_raw: JSON data
        :return: Preview object
        """
        error = preview_raw.get("error")
        if error is not None:
            raise ValueError("Bad response")

        content, md_text = await asyncio.get_event_loop().run_in_executor(
            None,
            self._parse_text,
            preview_raw["content"]
        )
        videos, photos = await self._masto_parse_media(preview_raw)
        return Post(
            text=content,
            url=None,
            markdown=md_text,
            replies=await self._parse_interaction(preview_raw["replies_count"]),
            reposts=await self._parse_interaction(preview_raw["reblogs_count"]),
            likes=await self._parse_interaction(preview_raw["favourites_count"]),
            views=None,
            community_note=None,
            author_name=preview_raw["account"]["display_name"],
            author_screen_name=preview_raw["account"]["username"],
            author_url=preview_raw["account"]["url"],
            post_date=await self._parse_date(preview_raw["created_at"]),
            photos=photos,
            videos=videos,
            facets=[],
            poll=await self._masto_parse_poll(preview_raw),
            link=await self._masto_parse_link(preview_raw),
            quote=await self._masto_parse_quote(preview_raw),
            translation=None,
            translation_lang=None,
            qtype="twitter"
        )

    async def _masto_parse_quote(self, data: Any) -> Post | None:
        quote = data.get("quote")
        if not quote:
            return None
        quote_text, md_quote_text = await asyncio.get_event_loop().run_in_executor(
            None,
            self._parse_text,
            quote["quoted_status"]["content"]
        )
        q_videos, q_photos = await self._masto_parse_media(quote["quoted_status"])
        return Post(
                text=quote_text,
                url=quote["quoted_status"]["url"],
                markdown=md_quote_text,
                replies=None,
                reposts=None,
                likes=None,
                views=None,
                community_note=None,
                author_name=quote["quoted_status"]["account"]["display_name"],
                author_url=quote["quoted_status"]["account"]["url"],
                author_screen_name=quote["quoted_status"]["account"]["username"],
                post_date=None,
                photos=q_photos,
                videos=q_videos,
                facets=[],
                poll=await self._tw_parse_poll(quote["quoted_status"]),
                link=await self._masto_parse_link(quote["quoted_status"]),
                quote=None,
                translation=None,
                translation_lang=None,
                qtype="mastodon"
            )

    def _parse_text(self, text: str) -> tuple[str, str]:
        if not text:
            return "", ""

        # HTML
        # Remove inline quote, it's redundant
        content = re.sub(r"<p\sclass=\"quote-inline\">.*?</p>", "", text)
        # Replace paragraph tags with newlines
        # content = re.sub(r"</p><p>", r"<br>", content)
        # content = re.sub(r"<p>|</p>", r"", content)
        # Remove invisible span
        content = re.sub(r"<span\sclass=\"invisible\">[^<>]*?</span>", "", content)
        # Replace ellipsis span with an actual ellipsis
        content = re.sub(r"<span\sclass=\"ellipsis\">([^<>]*?)</span>", r"\1...", content)

        # Markdown
        text_maker = html2text.HTML2Text()
        text_maker.body_width = 65536
        md_text = text_maker.handle(content)

        return content, md_text

    async def _masto_parse_media(self, data: Any) -> tuple[list, list]:
        # Multimedia
        media = data.get("media_attachments")
        photos: list[Photo] = []
        videos: list[Video] = []
        if media is not None:
            for elem in media:
                if elem["type"] in ["video", "gifv", "audio"]:
                    video = Video(
                        width=elem["meta"]["small"]["width"],
                        height=elem["meta"]["small"]["height"],
                        url=elem["url"],
                        thumbnail_url=elem["preview_url"],
                    )
                    videos.append(video)
                elif elem["type"] == "image":
                    photo = Photo(
                        width=elem["meta"]["original"]["width"],
                        height=elem["meta"]["original"]["height"],
                        url=elem["url"],
                    )
                    photos.append(photo)
        return videos, photos

    async def _masto_parse_link(self, data: Any) -> Link | None:
        # Link
        card = data.get("card")
        if card is not None:
            return Link(
                title=card["title"],
                description=card["description"],
                url=card["url"]
            )
        return None

    async def _parse_date(self, created: str) -> int:
        # Time
        if created:
            return int(mktime(strptime(created, "%Y-%m-%dT%H:%M:%S.%f%z")))
        return 0

    async def _masto_parse_poll(self, data: Any) -> Poll:
        # Poll
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
                expires_at = await self._parse_date(poll_raw["expires_at"])
                status = await self._get_mastodon_poll_status(expires_at)
            else:
                status = "Final results"
            poll = Poll(
                ends_at=poll_raw["expires_at"],
                status=status,
                total_voters=poll_raw["voters_count"],
                choices=choices
            )
        return poll

    async def _get_mastodon_poll_status(self, expires_at: int) -> str:
        time_diff = expires_at - int(time.time())
        d = divmod(time_diff, 86400)  # days
        h = divmod(d[1], 3600)  # hours
        m = divmod(h[1], 60)  # minutes
        s = m[1]  # seconds
        if d[0]:
            status = f"{d[0] + 1} days left"
        elif h[0]:
            status = f"{h[0] + 1} hours left"
        elif m[0]:
            status = f"{m[0] + 1} minutes left"
        else:
            status = f"{s + 1} seconds left"
        return status

    async def _parse_interaction(self, value: int) -> str:
        millions = divmod(value, 1000000)
        thousands = divmod(millions[1], 1000)
        if millions[0]:
            formatted_value = f"{millions[0]}.{round(millions[1], -4)//10000}M"
        elif thousands[0]:
            formatted_value = f"{thousands[0]}.{round(thousands[1], -2)//100}K"
        else:
            formatted_value = f"{thousands[1]}"
        return formatted_value

    async def _parse_bsky_preview(self, preview_raw: Any) -> Post:
        """
        Parse JSON data from Bsky API
        :param preview_raw: JSON data
        :return: Preview object
        """
        error = preview_raw.get("error")
        if error is not None:
            raise ValueError("Bad response")

        preview_raw = preview_raw["thread"]["post"]

        # Multimedia and quotes
        media = preview_raw.get("embed")
        photos: list[Photo] = []
        videos: list[Video] = []
        link: Link = None
        quote: Post = None
        if media is not None:
            videos = await self._bsky_parse_videos(media)
            photos = await self._bsky_parse_images(media)
            link = await self._bsky_parse_external(media)
            quote = await self._bsky_parse_quote(media)

        return Post(
            text=preview_raw["record"]["text"],
            url=None,
            markdown=None,
            replies=await self._parse_interaction(preview_raw["replyCount"]),
            reposts=await self._parse_interaction(preview_raw["repostCount"]),
            likes=await self._parse_interaction(preview_raw["likeCount"]),
            views=None,
            community_note=None,
            author_name=preview_raw["author"]["displayName"],
            author_screen_name=preview_raw["author"]["handle"],
            author_url="https://bsky.app/profile/" + preview_raw["author"]["handle"],
            post_date=await self._parse_date(preview_raw["record"]["createdAt"]),
            photos=photos,
            videos=videos,
            facets=await self._bsky_parse_facets(preview_raw["record"]),
            poll=None,
            link=link,
            quote=quote,
            translation=None,
            translation_lang=None,
            qtype="bsky"
        )

    async def _bsky_parse_images(self, media: Any) -> list[Photo]:
        photos: list[Photo] = []
        if "app.bsky.embed.images" in media["$type"]:
            for elem in media["images"]:
                photo = Photo(
                    width=elem["aspectRatio"]["width"],
                    height=elem["aspectRatio"]["height"],
                    url=elem["fullsize"],
                )
                photos.append(photo)
        if "app.bsky.embed.recordWithMedia" in media["$type"]:
            photos += await self._bsky_parse_images(media["media"])
        return photos

    async def _bsky_parse_videos(self, media: Any) -> list[Video]:
        videos: list[Video] = []
        if "app.bsky.embed.video" in media["$type"]:
            video = Video(
                width=media["aspectRatio"]["width"],
                height=media["aspectRatio"]["height"],
                url=self.config["bsky_player"] + media["playlist"],
                thumbnail_url=media["thumbnail"],
            )
            videos.append(video)
        if "app.bsky.embed.recordWithMedia" in media["$type"]:
            videos += await self._bsky_parse_videos(media["media"])
        return videos

    async def _bsky_parse_quote(self, media: Any) -> Post | None:
        if "app.bsky.embed.record" in media["$type"]:
            if "app.bsky.embed.recordWithMedia" in media["$type"]:
                media = media["record"]
            photos: list[Photo] = []
            videos: list[Video] = []
            link: Link = None
            media_rec = media["record"].get("embeds")
            if media_rec is not None:
                for elem in media_rec:
                    photos = await self._bsky_parse_images(elem)
                    videos = await self._bsky_parse_videos(elem)
                    link = await self._bsky_parse_external(elem)

            return Post(
                text=media["record"]["value"]["text"],
                url=(
                    f"https://bsky.app/profile/{media["record"]["author"]["handle"]}/"
                    f"post/{media["record"]["uri"].split("/")[-1]}"
                ),
                markdown=None,
                replies=None,
                reposts=None,
                likes=None,
                views=None,
                community_note=None,
                author_name=media["record"]["author"]["displayName"],
                author_screen_name=media["record"]["author"]["handle"],
                author_url=f"https://bsky.app/profile/{media["record"]["author"]["handle"]}",
                post_date=None,
                photos=photos,
                videos=videos,
                facets=await self._bsky_parse_facets(media["record"]["value"]),
                poll=None,
                link=link,
                quote=None,
                translation=None,
                translation_lang=None,
                qtype="bsky"
            )
        return None

    async def _bsky_parse_external(self, media: Any) -> Link | None:
        if "app.bsky.embed.external" in media["$type"]:
            return Link(
                title=media["external"]["title"],
                description=media["external"]["description"],
                url=media["external"]["uri"]
            )
        return None

    async def _bsky_parse_facets(self, data: Any) -> list[Facet]:
        # List of elements to substitute for in the raw text message
        facets: list[Facet] = []
        facets_raw = data.get("facets")
        if facets_raw is not None:
            for fac in facets_raw:
                facet = None
                b_start = fac["index"]["byteStart"]
                b_end = fac["index"]["byteEnd"]
                text = data["text"].encode('utf-8')
                if fac["features"][0]["$type"] == "app.bsky.richtext.facet#mention":
                    text = text[b_start:b_end].decode('utf-8')
                    facet = Facet(
                        text=text,
                        url=f"https://bsky.app/profile/{fac["features"][0]["did"]}",
                        byte_start=b_start,
                        byte_end=b_end
                    )
                elif fac["features"][0]["$type"] == "app.bsky.richtext.facet#tag":
                    tag = fac["features"][0]["tag"]
                    facet = Facet(
                        text="#" + tag,
                        url=f"https://bsky.app/hashtag/{tag}",
                        byte_start=b_start,
                        byte_end=b_end
                    )
                elif fac["features"][0]["$type"] == "app.bsky.richtext.facet#link":
                    link_text = text[b_start:b_end].decode('utf-8')
                    facet = Facet(
                        text=link_text,
                        url=fac["features"][0]["uri"],
                        byte_start=b_start,
                        byte_end=b_end
                    )
                if facet:
                    facets.append(facet)
                facets.sort(key=lambda f: f.byte_start)
        return facets

    async def _parse_twitter_preview(self, preview_raw: Any) -> Post:
        """
        Parse JSON data from FxTwitter API
        :param preview_raw: JSON data
        :return: Preview object
        """
        if not preview_raw["code"] == 200:
            raise ValueError("Bad response")

        preview_raw = preview_raw["tweet"]

        videos, photos = await self._tw_parse_media(preview_raw)
        translation = preview_raw.get("translation")

        post = Post(
            # Remove non-functional links added at the end of some tweets with media attached
            text=preview_raw["raw_text"]["text"],
            url=None,
            markdown=None,
            replies=await self._parse_interaction(preview_raw["replies"]),
            reposts=await self._parse_interaction(preview_raw["retweets"]),
            likes=await self._parse_interaction(preview_raw["likes"]),
            views=await self._parse_interaction(preview_raw["views"]),
            community_note=await self._tw_parse_community_note(preview_raw),
            author_name=preview_raw["author"]["name"],
            author_screen_name=preview_raw["author"]["screen_name"],
            author_url=preview_raw["author"]["url"],
            post_date=preview_raw["created_timestamp"],
            photos=photos,
            videos=videos,
            facets=await self._tw_parse_facets(preview_raw),
            poll=await self._tw_parse_poll(preview_raw),
            link=None,
            quote=await self._tw_parse_quote(preview_raw),
            translation=translation["text"] if translation is not None else None,
            translation_lang=translation["source_lang_en"] if translation is not None else None,
            qtype="twitter"
        )

        return post

    async def _tw_parse_quote(self, data: Any) -> Post | None:
        quote = data.get("quote")
        if not quote:
            return None
        q_videos, q_photos = await self._tw_parse_media(quote)
        return Post(
                text=quote["raw_text"]["text"],
                url=quote["url"],
                markdown=None,
                replies=None,
                reposts=None,
                likes=None,
                views=None,
                community_note=None,
                author_name=quote["author"]["name"],
                author_url=quote["author"]["url"],
                author_screen_name=quote["author"]["screen_name"],
                post_date=None,
                photos=q_photos,
                videos=q_videos,
                facets=await self._tw_parse_facets(quote),
                poll=await self._tw_parse_poll(quote),
                link=None,
                quote=None,
                translation=None,
                translation_lang=None,
                qtype="twitter"
            )

    async def _tw_parse_community_note(self, data: Any) -> str:
        # Community Note
        community_note = data.get("community_note")
        if community_note is not None:
            return community_note["text"]
        return ""

    async def _tw_parse_media(self, data: Any) -> tuple[list, list]:
        # Multimedia
        media = data.get("media")
        photos: list[Photo] = []
        videos: list[Video] = []
        if media is not None:
            for elem in media["all"]:
                if elem["type"] in ["video", "gif"]:
                    video = Video(
                        width=elem["width"],
                        height=elem["height"],
                        url=elem["url"],
                        thumbnail_url=elem["thumbnail_url"],
                    )
                    videos.append(video)
                elif elem["type"] == "photo":
                    photo = Photo(
                        width=elem["width"],
                        height=elem["height"],
                        url=elem["url"],
                    )
                    photos.append(photo)
        return videos, photos

    async def _tw_parse_poll(self, data: Any) -> Poll:
        # Poll
        poll = None
        poll_raw = data.get("poll")
        if poll_raw is not None:
            choices: list[Choice] = []
            for option in poll_raw["choices"]:
                choice = Choice(
                    label=option["label"],
                    votes_count=option["count"],
                    percentage=option["percentage"],
                )
                choices.append(choice)
            poll = Poll(
                ends_at=poll_raw["ends_at"],
                status=poll_raw["time_left_en"],
                total_voters=poll_raw["total_votes"],
                choices=choices
            )
        return poll

    async def _tw_parse_facets(self, data: Any) -> list[Facet]:
        # List of elements to substitute for in the raw text message
        facets: list[Facet] = []
        facets_raw = data["raw_text"].get("facets")
        if facets_raw is not None:
            for fac in facets_raw:
                facet = None
                b_start = fac["indices"][0]
                b_end = fac["indices"][1]
                if fac["type"] in "url":
                    facet = Facet(
                        text=fac["display"],
                        url=fac["replacement"],
                        byte_start=b_start,
                        byte_end=b_end,
                    )
                elif fac["type"] == "mention":
                    facet = Facet(
                        text="@" + fac["original"],
                        url="https://x.com/" + fac["original"],
                        byte_start=b_start,
                        byte_end=b_end,
                    )
                elif fac["type"] == "hashtag":
                    facet = Facet(
                        text="#" + fac["original"],
                        url="https://x.com/hashtag/" + fac["original"],
                        byte_start=b_start,
                        byte_end=b_end,
                    )
                # Ignore 'media' type because API returns wrong indices in them
                if facet:
                    facets.append(facet)
            facets.sort(key=lambda f: f.byte_start)
        return facets

    async def _replace_facets(
            self,
            text: str,
            facets: list[Facet],
            qtype: str,
            is_html: bool = True
    ) -> str:
        """
        Replace mentions, tags, URLs in raw_text with appropriate links
        :param text: raw text of the message
        :param facets: list of elements sorted by byte_start with data about replacements
        :param is_html: should method return text with HTML or Markdown
        :return: text with replacements
        """
        text = text.encode("utf-8") if qtype == "bsky" else text
        text_array = []
        start = 0
        for facet in facets:
            # Append normal text
            text_array.append(text[start:facet.byte_start])
            # Append text replacement from facet
            link = await self._get_link(facet.url, facet.text, is_html)
            link = link.encode("utf-8") if qtype == "bsky" else link
            text_array.append(link)
            start = facet.byte_end
        # Append the remaining text
        text_array.append(text[start:])
        return b"".join(text_array).decode("utf-8") if qtype == "bsky" else "".join(text_array)

    async def _get_chart_bar(self, percentage: float) -> str:
        """
        Get ASCII chart bar to represent result in a poll
        :param percentage: percentage of votes (0-100)
        :return: ASCII chart bar
        """
        dark_block = "█"
        light_block = "░"
        dark_num = round(percentage * 16 / 100)
        return f"{dark_num * dark_block + (16 - dark_num) * light_block}"

    async def _prepare_message(self, preview: Post) -> TextMessageEventContent:
        """
        Prepare Twitter preview message text
        :param preview: Preview object with data from API
        :return: body and HTML for preview message
        """
        # Replace Twitter links with Nitter where possible
        await self._replace_urls_base(preview)

        html = ""
        body = ""

        # Author
        html += await self._get_author(preview)
        body += await self._get_author(preview, False)

        # Text
        html += await self._get_text(preview)
        body += await self._get_text(preview, False)

        # Translation
        html += await self._get_translation(preview)
        body += await self._get_translation(preview, False)

        # Poll
        html += await self._get_poll(preview)
        body += await self._get_poll(preview, False)

        # Multimedia previews
        html += await self._get_media_previews(preview)
        body += await self._get_media_previews(preview, False)

        # Multimedia list for clients that have problems displaying images/links
        # Videos
        html += await self._get_media_list(preview.videos)
        body += await self._get_media_list(preview.videos, False)
        # Photos
        html += await self._get_media_list(preview.photos)
        body += await self._get_media_list(preview.photos, False)

        # Quote
        html += await self._get_quote(preview.quote)
        body += await self._get_quote(preview.quote, False)

        # External link
        html += await self._get_external_link(preview.link)
        body += await self._get_external_link(preview.link, False)

        # Replies, retweets, likes, views
        html += await self._get_interactions(preview)
        body += await self._get_interactions(preview, False)

        # Community Note
        html += await self._get_community_note(preview.community_note)
        body += await self._get_community_note(preview.community_note, False)

        # Footer, date
        html += await self._get_footer(preview.post_date)
        body += await self._get_footer(preview.post_date, False)

        html = f"<blockquote>{html}</blockquote>"

        return TextMessageEventContent(
            msgtype=MessageType.NOTICE,
            format=Format.HTML,
            body=body,
            formatted_body=html
        )

    async def _get_link(self, url: str, text: str, is_html: bool = True) -> str:
        """
        Return a link as HTML or Markdown
        :param url: address
        :param text: displayed text
        :param is_html: True for HTML, False for Markdown
        :return: formatted link
        """
        # HTML
        if is_html:
            return f"<a href=\"{url}\">{text}</a>"

        # Markdown
        return f"[{text}]({url})"

    async def _get_author(self, data: Post, is_html: bool = True) -> str:
        author_name = data.author_name if data.author_name else data.author_screen_name

        if is_html:
            return f"<p>{await self._get_link(
                data.author_url,
                f"<b>{author_name} (@{data.author_screen_name})</b>"
            )}</p>"

        return f"> {await self._get_link(
            data.author_url,
            f"**{author_name}** **(@{data.author_screen_name})**",
            False
        )}   \n>  \n"

    async def _get_text(self, data: Post, is_html: bool = True) -> str:
        text = data.text
        if not text:
            return ""

        if is_html:
            if data.text and data.facets:
                text = await self._replace_facets(data.text, data.facets, data.qtype)
            return f"<p>{text.replace('\n', '<br>')}</p>"

        if data.text and data.facets:
            text = await self._replace_facets(data.text, data.facets, data.qtype, False)
        # It's for Mastodon's case, so there are no facets which is why the previous step is ignored
        if data.markdown:
            text = data.markdown
        return f"> {text.replace('\n', '  \n> ')}  \n>  \n"

    async def _get_translation(self, data: Post, is_html: bool = True) -> str:
        if not data.translation:
            return ""

        if is_html:
            return (
                f"<blockquote><b>Translated from {data.translation_lang}</b><br>"
                f"{data.translation.replace('\n', '<br>')}"
                f"</blockquote>"
            )
        return (
            f"> > **Translated from {data.translation_lang}**  \n"
            f"> > {data.translation.replace('\n', '  \n> > ')}  \n>  \n")

    async def _get_poll(self, data: Post, is_html: bool = True) -> str:
        if not data.poll:
            return ""

        poll = []
        for choice in data.poll.choices:
            if is_html:
                poll.append(
                    f"{await self._get_chart_bar(choice.percentage)}"
                    f"<br>{choice.percentage}% {choice.label}"
                )
            else:
                poll.append(
                    f"> > {await self._get_chart_bar(choice.percentage)}  \n"
                    f"> > {choice.percentage}% {choice.label}  \n"
                )

        if is_html:
            return (
                f"<blockquote>"
                f"<p>{'<br>'.join(poll)}</p>"
                f"<p>{data.poll.total_voters:,} voters • {data.poll.status}</p>"
                f"</blockquote>"
                .replace(",", " ")
            )
        return (
            f"{''.join(poll)}> >  \n"
            f"> > {data.poll.total_voters:,} voters • {data.poll.status}  \n>  \n"
            .replace(",", " ")
        )

    async def _get_media_previews(self, data: Post, is_html: bool = True) -> str:
        if len(data.videos) + len(data.photos) == 0:
            return ""
        thumbs_data = []
        for i, vid in enumerate(data.videos):
            image = Photo(
                url=vid.thumbnail_url,
                width=vid.width,
                height=vid.height
            )
            full_url = vid.url
            thumbs_data.append((image, full_url, f"Vid#{i + 1}"))

        for i, pic in enumerate(data.photos):
            thumbs_data.append((pic, pic.url, f"Pic#{i + 1}"))
        thumbs = []

        for thumb in thumbs_data:
            image_mxc, width, height = await self._get_matrix_image_url(
                thumb[0],
                300 if (len(data.videos) + len(data.photos) == 1) else 100
            )
            await asyncio.sleep(0.2)
            if image_mxc:
                thumbs.append(f"{await self._get_link(
                    thumb[1],
                    await self._get_image(image_mxc, thumb[2], (width, height), is_html),
                    is_html
                )}")
        if is_html:
            return f"<p>{" ".join(thumbs)}</p>"
        return f"> {" ".join(thumbs)}  \n>  \n"

    async def _get_image(
        self,
        src: str,
        alt: str = "",
        size: tuple[int, int] = (0, 0),
        is_html: bool = True
    ) -> str:
        """
        Get link
        :param src: source url
        :param alt: alternative text
        :param size: width and height
        :param is_html: True for HTML, False for Markdown
        :return: formatted image
        """
        width = f"width=\"{size[0]}\" " if size[0] else ""
        height = f"height=\"{size[1]}\" " if size[1] else ""
        if is_html:
            return f"<img src=\"{src}\" alt=\"{alt}\" {width}{height}/>"
        return f"![{alt}]({src})"

    async def _get_media_list(self, media: list, is_html: bool = True) -> str:
        if len(media) > 0:
            if isinstance(media[0], Video):
                title = "Videos"
                short = "Vid"
            else:
                title = "Photos"
                short = "Pic"
            i = 1
            media_formatted = []
            for video in media:
                media_formatted.append(await self._get_link(video.url, f"{short}#{i}", is_html))
                i += 1
            if is_html:
                return f"<p><b>{title}: </b>{', '.join(media_formatted)}</p>"
            return f"> **{title}:** {', '.join(media_formatted)}  \n>  \n"
        return ""

    async def _get_quote(self, data: Post, is_html: bool = True) -> str:
        if not data:
            return ""
        text = ""
        text += await self._get_quote_author(data, is_html)
        res = await self._get_text(data, is_html)
        text += res if is_html else res.replace("> ", "> > ")
        res = await self._get_poll(data, is_html)
        text += res if is_html else res.replace("> > ", "> > > ")
        res = await self._get_media_previews(data, is_html)
        text += res if is_html else res.replace("> ", "> > ")
        res = await self._get_media_list(data.videos, is_html)
        text += res if is_html else res.replace("> ", "> > ")
        res = await self._get_media_list(data.photos, is_html)
        text += res if is_html else res.replace("> ", "> > ")
        res = await self._get_external_link(data.link, is_html)
        text += res if is_html else res.replace("> > ", "> > > ")
        if is_html:
            return f"<blockquote>{text}</blockquote>"
        return text

    async def _get_quote_author(self, data: Post, is_html: bool = True) -> str:
        if not data.author_screen_name:
            return ""
        link = await self._get_link(data.author_url, f"@{data.author_screen_name}", is_html)
        if is_html:
            return (
                f"<p><b>"
                f"{await self._get_link(data.url, "Quoting")} {data.author_name} ({link})"
                f"</b></p>"
            )
        return (
            f"> > {await self._get_link(data.url, "**Quoting**", False)} "
            f"{data.author_name} **({link})**  \n> >  \n"
        )

    async def _get_interactions(self, data: Post, is_html: bool = True) -> str:
        text = []
        if data.replies:
            text.append(f"💬 {data.replies}")
        if data.reposts:
            text.append(f"🔁 {data.reposts}")
        if data.likes:
            text.append(f"❤️ {data.likes}")
        if data.views:
            text.append(f"👁️ {data.views}")
        if text:
            if is_html:
                return f"<p><b>{' '.join(text)}</b></p>"
            return f"> {' '.join(text)}  \n>  \n"
        return ""

    async def _get_external_link(self, data: Link, is_html: bool = True) -> str:
        if not data:
            return ""

        text = ""
        link = await self._get_link(data.url, data.title, is_html)
        if is_html:
            text += f"<blockquote><p><b>{link}</b></p>"
            if data.description:
                text += f"<p>{data.description}</p>"
            text += "</blockquote>"
        else:
            text += f"> > **{link}**"
            if data.description:
                text += f"  \n> > {data.description}"
            text += "  \n>  \n"
        return text

    async def _get_community_note(self, note: str, is_html: bool = True) -> str:
        if not note:
            return ""

        if is_html:
            return (
                "<blockquote>"
                "<p><b>Community Note:</b></p>"
                f"<p>{note.replace('\n', '<br>')}</p>"
                "</blockquote>"
            )
        return (
            f"> > **Community Note:**  \n"
            f"> > {note.replace('\n', '  \n> > ')}  \n>  \n"
        )

    async def _get_footer(self, post_date: int, is_html: bool = True) -> str:
        date_html = ""
        date_md = ""
        if post_date:
            date = strftime('%Y-%m-%d %H:%M', localtime(post_date))
            date_html = f"<b><sub> • {date}</sub></b>"
            date_md = f"** • {date}**"
        if is_html:
            return f"<p><b><sub>MautrFxEmbed</sub></b>{date_html}</p>"
        return f"> **MautrFxEmbed**{date_md}"

    async def _get_matrix_image_url(self, image: Photo, size: int) -> tuple[str, int, int]:
        """
        Download image from external URL and upload it to Matrix
        :param url: external URL
        :return: matrix mxc URL
        """
        try:
            # Download image from external source
            data = await self._download_image(image.url)
            if not data:
                return "", 0, 0

            # Generate thumbnail
            image_data, width, height = await asyncio.get_event_loop().run_in_executor(
                None,
                self._get_thumbnail,
                (data, size, size)
            )
            if not image_data:
                return "", 0, 0

            # Upload image to Matrix server
            mxc_uri = await self.client.upload_media(
                data=image_data,
                mime_type="image/jpeg",
                filename="thumbnail.jpg",
                size=len(image_data))
            return mxc_uri, width, height
        except ClientError as e:
            self.log.error(f"Downloading image - connection failed: {e}")
            return "", 0, 0
        except (ValueError, MatrixResponseError) as e:
            self.log.error(f"Uploading image to Matrix server: {e}")
            return "", 0, 0

    def _get_thumbnail(self, image: tuple[bytes, int, int]) -> tuple[bytes, int, int]:
        """
        Convert original thumbnail into 100x100 one
        :param image: image data as bytes
        :return: new image data as bytes
        """
        try:
            img = Image.open(io.BytesIO(image[0]))
            img.thumbnail((image[1], image[2]), Image.Resampling.LANCZOS)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format="JPEG", quality=90)
            img_byte_arr.seek(0)
            image = img_byte_arr.getvalue()
        except (OSError, ValueError, TypeError, FileNotFoundError, UnidentifiedImageError) as e:
            self.log.error(f"Error generating thumbnail: {e}")
            return (b'', 0, 0)
        return image, img.width, img.height

    async def _replace_urls_base(self, preview: Post) -> None:
        """
        If appropriate config values are set, replace original URL with Nitter equivalents
        :param preview: Preview object with data from API
        :return:
        """
        if not self.config["nitter_redirect"]:
            return

        if preview.author_url:
            preview.author_url = preview.author_url.replace("x.com", self.config["nitter_url"])
        if preview.url:
            preview.url = preview.url.replace("x.com", self.config["nitter_url"])
        if len(preview.photos) > 0:
            for photo in preview.photos:
                photo.url = photo.url.replace(
                    "pbs.twimg.com",
                    f"{self.config['nitter_url']}/pic/orig"
                )
        if len(preview.facets) > 0:
            for facet in preview.facets:
                facet.url = facet.url.replace(
                    "https://x.com",
                    f"https://{self.config['nitter_url']}"
                )
        if preview.quote:
            await self._replace_urls_base(preview.quote)

    async def _get_preview(self, url: str) -> Any:
        """
        Get results from the API.
        :param url: source URL
        :return: JSON API response
        """
        timeout = ClientTimeout(total=20)
        try:
            response = await self.http.get(
                url,
                headers=self.headers,
                timeout=timeout,
                raise_for_status=True
            )
            return await response.json()
        except ClientError as e:
            self.log.error(f"Connection failed: {e}")
            return ""

    async def _get_canonical_urls(self, urls: list[tuple[str, str]]) -> list[str]:
        """
        Extract canonical URLs from a list of URLs
        :param urls: list of URLs
        :return: list of canonical URLs
        """
        canonical_urls = []
        for url in urls:
            for domain in self.twitter_domains:
                if f"https://{domain}" in url[1]:
                    canonical_urls.append(url[1].replace(domain, "api.fxtwitter.com"))
                    continue
            for domain in self.bsky_domains:
                if f"https://{domain}" in url[1]:
                    new_url = (
                        url[1]
                        .replace(
                            domain,
                            "api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri=at:/"
                        )
                        .replace("post", "app.bsky.feed.post"))
                    new_url += "&depth=0"
                    canonical_urls.append(new_url)
                    continue
            for domain in self.instagram_domains:
                if f"https://{domain}" in url[1]:
                    canonical_urls.append(url[1].replace(domain, "www.kkinstagram.com/reel"))
                    continue
            # Mastodon post links
            m = re.match(r"(https://.+\.[A-Za-z]+)/@[A-Za-z0-9_]+/([0-9]+)", url[1])
            if m is not None:
                new_url = m.groups()[0] + "/api/v1/statuses/" + m.groups()[1]
                canonical_urls.append(new_url)
        return canonical_urls

    async def _download_image(self, url: str) -> bytes | None:
        """
        Download image from external URL
        :param url: external URL
        :return: image data as bytes
        """
        timeout = ClientTimeout(total=20)
        try:
            response = await self.http.get(
                url,
                headers=self.headers,
                timeout=timeout,
                raise_for_status=True
            )
            return await response.read()
        except ClientError as e:
            self.log.error(f"Preparing image - connection failed: {url}: {e}")

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config
