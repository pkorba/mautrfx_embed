import asyncio
import io
import re
import time
from time import strftime, localtime, strptime, mktime
from typing import Tuple, Any, Type

from PIL import UnidentifiedImageError
import aiohttp
import filetype
import html2text
from PIL import Image
from aiohttp import ClientError, ClientTimeout
from mautrix.types import (
    TextMessageEventContent,
    MediaMessageEventContent,
    MessageEventContent,
    MessageType,
    ImageInfo,
    Format
)
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from maubot import Plugin, MessageEvent
from maubot.handlers import command

from .resources.datastructures import Preview, Photo, Video, Facet, Link, Poll, Choice


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
        canonical_urls = await self.get_canonical_urls(matches)
        if not canonical_urls:
            return
        await evt.mark_read()

        previews = []
        for url in canonical_urls:
            if "kkinstagram.com/reel" in url:
                preview_raw = await self.get_instagram_preview(url)
                # For private reels kkinstagram returns original reel URL
                if "https://www.instagram.com/reel" in preview_raw:
                    continue
            else:
                preview_raw = await self.get_preview(url)
            if preview_raw:
                try:
                    preview = await self.parse_preview(preview_raw, url)
                    previews.append(preview)
                except Exception as e:
                    self.log.error(f"Error parsing preview: {e}")
        for preview in previews:
            content = await self.prepare_message(preview)
            await evt.respond(content)

    async def get_instagram_preview(self, url: str) -> str:
        """
        Get url to Instagram video preview.
        :param url: source URL
        :return: Instagram video preview url
        """
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
            return response.headers["location"]
        except ClientError as e:
            self.log.error(f"Connection failed: {e}")
            return ""
        except KeyError as e:
            self.log.error(f"Missing 'location' header: {e}")
            return ""

    async def parse_preview(self, preview_raw: Any, url: str) -> Preview:
        if "api.fxtwitter.com" in url:
            return await self.parse_twitter_preview(preview_raw)
        if "api.bsky.app" in url:
            return await self.parse_bsky_preview(preview_raw)
        if "www.kkinstagram.com/reel" in url:
            return await self.parse_instagram_preview(preview_raw)
        return await self.parse_mastodon_preview(preview_raw)

    async def parse_instagram_preview(self, preview_url: str) -> Preview:
        return Preview(
            text=None,
            markdown=None,
            replies=None,
            reposts=None,
            likes=None,
            views=None,
            community_note=None,
            author_name="Video link",
            author_screen_name="Instagram",
            author_url=preview_url,
            tweet_date=None,
            mosaic=None,
            photos=[],
            videos=[],
            facets=[],
            poll=None,
            link=None,
            quote_url=None,
            quote_text=None,
            quote_markdown=None,
            quote_author_name=None,
            quote_author_url=None,
            quote_author_screen_name=None
        )

    async def parse_mastodon_preview(self, preview_raw: Any) -> Preview:
        """
        Parse JSON data from Mastodon API
        :param preview_raw: JSON data
        :return: Preview object
        """
        error = preview_raw.get("error")
        if error is not None:
            raise ValueError("Bad response")

        # Quote
        quote_url = ""
        quote_text = ""
        quote_author_name = ""
        quote_author_url = ""
        quote_author_screen_name = ""
        quote = preview_raw.get("quote")
        if quote is not None:
            quote_url = quote["quoted_status"]["url"]
            quote_text = quote["quoted_status"]["content"]
            quote_author_name = quote["quoted_status"]["account"]["display_name"]
            quote_author_url = quote["quoted_status"]["account"]["url"]
            quote_author_screen_name = quote["quoted_status"]["account"]["username"]

        # Multimedia
        media = preview_raw.get("media_attachments")
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

        # Link
        link: Link = None
        card = preview_raw.get("card")
        if card is not None:
            link = Link(
                title=card["title"],
                description=card["description"],
                url=card["url"]
            )

        # Time
        created = None
        if preview_raw["created_at"]:
            created = int(mktime(strptime(preview_raw["created_at"], "%Y-%m-%dT%H:%M:%S.%f%z")))

        # HTML adjustments / Markdown message
        content = ""
        md_text = ""
        md_quote_text = ""
        text_maker = html2text.HTML2Text()
        text_maker.body_width = 65536
        if preview_raw["content"]:
            content = await asyncio.get_event_loop().run_in_executor(
                None,
                self.strip_html_parts,
                preview_raw["content"]
            )
            md_text = await asyncio.get_event_loop().run_in_executor(
                None,
                text_maker.handle,
                content
            )
        if quote_text:
            quote_text = await asyncio.get_event_loop().run_in_executor(
                None,
                self.strip_html_parts,
                quote_text
            )
            md_quote_text = await asyncio.get_event_loop().run_in_executor(
                None,
                text_maker.handle,
                quote_text
            )

        # Poll
        poll = None
        poll_raw = preview_raw.get("poll")
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
                expires_at = int(mktime(strptime(poll_raw["expires_at"], "%Y-%m-%dT%H:%M:%S.%f%z")))
                status = await self.get_mastodon_poll_status(expires_at)
            else:
                status = "Final results"
            poll = Poll(
                ends_at=poll_raw["expires_at"],
                status=status,
                total_voters=poll_raw["voters_count"],
                choices=choices
            )

        # Replies, shares, likes
        replies = await self.format_interaction(preview_raw["replies_count"])
        shares = await self.format_interaction(preview_raw["reblogs_count"])
        likes = await self.format_interaction(preview_raw["favourites_count"])

        return Preview(
            text=content,
            markdown=md_text,
            replies=replies,
            reposts=shares,
            likes=likes,
            views=None,
            community_note=None,
            author_name=preview_raw["account"]["display_name"],
            author_screen_name=preview_raw["account"]["username"],
            author_url=preview_raw["account"]["url"],
            tweet_date=created,
            mosaic=None,
            photos=photos,
            videos=videos,
            facets=[],
            poll=poll,
            link=link,
            quote_url=quote_url,
            quote_text=quote_text,
            quote_markdown=md_quote_text,
            quote_author_name=quote_author_name,
            quote_author_url=quote_author_url,
            quote_author_screen_name=quote_author_screen_name
        )

    async def get_mastodon_poll_status(self, expires_at: int) -> str:
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

    async def format_interaction(self, value: int) -> str:
        millions = divmod(value, 1000000)
        thousands = divmod(millions[1], 1000)
        if millions[0]:
            formatted_value = f"{millions[0]}.{round(millions[1], -4)//10000}M"
        elif thousands[0]:
            formatted_value = f"{thousands[0]}.{round(thousands[1], -2)//100}K"
        else:
            formatted_value = f"{thousands[1]}"
        return formatted_value

    def strip_html_parts(self, text: str) -> str:
        """
        Mastodon provides HTML formatted text ootb. Remove redundant tags
        :param text:
        :return:
        """
        # Remove inline quote, it's redundant
        content = re.sub(r"<p\sclass=\"quote-inline\">.*?</p>", "", text)
        # Replace paragraph tags with newlines
        content = re.sub(r"</p><p>", r"<br>", content)
        content = re.sub(r"<p>|</p>", r"", content)
        # Remove invisible span
        content = re.sub(r"<span\sclass=\"invisible\">[^<>]*?</span>", "", content)
        # Replace ellipsis span with an actual ellipsis
        content = re.sub(r"<span\sclass=\"ellipsis\">([^<>]*?)</span>", r"\1...", content)
        return content

    async def parse_bsky_preview(self, preview_raw: Any) -> Preview:
        """
        Parse JSON data from Bsky API
        :param preview_raw: JSON data
        :return: Preview object
        """
        error = preview_raw.get("error")
        if error is not None:
            raise ValueError("Bad response")

        preview_raw = preview_raw["thread"]["post"]

        # List of elements to substitute for in the raw text message
        facets: list[Facet] = []
        facets_raw = preview_raw["record"].get("facets")
        if facets_raw is not None:
            for fac in facets_raw:
                facet = None
                b_start = fac["index"]["byteStart"]
                b_end = fac["index"]["byteEnd"]
                if "mention" in fac["features"][0]["$type"]:
                    text = preview_raw["record"]["text"][b_start:b_end]
                    facet = Facet(
                        text=text,
                        url=f"https://bsky.app/profile/{fac["features"][0]["did"]}",
                        byte_start=b_start,
                        byte_end=b_end
                    )
                elif "tag" in fac["features"][0]["$type"]:
                    tag = fac["features"][0]["tag"]
                    facet = Facet(
                        text="#" + tag,
                        url=f"https://bsky.app/hashtag/{tag}",
                        byte_start=b_start,
                        byte_end=b_end
                    )
                elif "link" in fac["features"][0]["$type"]:
                    link_text = preview_raw["record"]["text"][b_start:b_end]
                    facet = Facet(
                        text=link_text,
                        url=fac["features"][0]["uri"],
                        byte_start=b_start,
                        byte_end=b_end
                    )
                if facet:
                    facets.append(facet)

        # Multimedia and quotes
        media = preview_raw.get("embed")
        photos: list[Photo] = []
        videos: list[Video] = []
        link = None
        quote_url = ""
        quote_text = ""
        quote_author_name = ""
        quote_author_url = ""
        quote_author_screen_name = ""
        if media is not None:
            if "app.bsky.embed.video" in media["$type"]:
                video = Video(
                    width=media["aspectRatio"]["width"],
                    height=media["aspectRatio"]["height"],
                    url=self.config["bsky_player"] + media["playlist"],
                    thumbnail_url=media["thumbnail"],
                )
                videos.append(video)
            elif "app.bsky.embed.images" in media["$type"]:
                for elem in media["images"]:
                    photo = Photo(
                        width=elem["aspectRatio"]["width"],
                        height=elem["aspectRatio"]["height"],
                        url=elem["fullsize"],
                    )
                    photos.append(photo)
            elif "app.bsky.embed.recordWithMedia" in media["$type"]:
                record = media["record"]
                quote_url = (
                    f"https://bsky.app/profile/{record["record"]["author"]["handle"]}/"
                    f"post/{record["record"]["uri"].split("/")[-1]}"
                )
                quote_text = record["record"]["value"]["text"]
                quote_author_name = record["record"]["author"]["displayName"]
                quote_author_url = f"https://bsky.app/profile/{record["record"]["author"]["handle"]}"

                quote_author_screen_name = record["record"]["author"]["handle"]
                media_rec = media.get("media")
                if media_rec is not None:
                    if "app.bsky.embed.video" in media_rec["$type"]:
                        video = Video(
                            width=media_rec["aspectRatio"]["width"],
                            height=media_rec["aspectRatio"]["height"],
                            url=self.config["bsky_player"] + media_rec["playlist"],
                            thumbnail_url=media_rec["thumbnail"],
                        )
                        videos.append(video)
                    elif "app.bsky.embed.images" in media_rec["$type"]:
                        for elem in media_rec["images"]:
                            photo = Photo(
                                width=elem["aspectRatio"]["width"],
                                height=elem["aspectRatio"]["height"],
                                url=elem["fullsize"],
                            )
                            photos.append(photo)
            elif "app.bsky.embed.record" in media["$type"]:
                quote_url = (
                    f"https://bsky.app/profile/{media["record"]["author"]["handle"]}/"
                    f"post/{media["record"]["uri"].split("/")[-1]}"
                )
                quote_text = media["record"]["value"]["text"]
                quote_author_name = media["record"]["author"]["displayName"]
                quote_author_url = "https://bsky.app/profile/" + media["record"]["author"]["handle"]
                quote_author_screen_name = media["record"]["author"]["handle"]
            elif "app.bsky.embed.external" in media["$type"]:
                link = Link(
                    title=media["external"]["title"],
                    description=media["external"]["description"],
                    url=media["external"]["uri"]
                )

        # Time
        created = None
        if preview_raw["record"]["createdAt"]:
            created = int(mktime(strptime(
                preview_raw["record"]["createdAt"], "%Y-%m-%dT%H:%M:%S.%f%z"
            )))

        # Replies, shares, likes
        replies = await self.format_interaction(preview_raw["replyCount"])
        shares = await self.format_interaction(preview_raw["repostCount"])
        likes = await self.format_interaction(preview_raw["likeCount"])

        return Preview(
            text=preview_raw["record"]["text"],
            markdown=None,
            replies=replies,
            reposts=shares,
            likes=likes,
            views=None,
            community_note="",
            author_name=preview_raw["author"]["displayName"],
            author_screen_name=preview_raw["author"]["handle"],
            author_url="https://bsky.app/profile/" + preview_raw["author"]["handle"],
            tweet_date=created,
            mosaic=None,
            photos=photos,
            videos=videos,
            facets=facets,
            poll=None,
            link=link,
            quote_url=quote_url,
            quote_text=quote_text,
            quote_markdown=None,
            quote_author_name=quote_author_name,
            quote_author_url=quote_author_url,
            quote_author_screen_name=quote_author_screen_name
        )

    async def parse_twitter_preview(self, preview_raw: Any) -> Preview:
        """
        Parse JSON data from FxTwitter API
        :param preview_raw: JSON data
        :return: Preview object
        """
        if not preview_raw["code"] == 200:
            raise ValueError("Bad response")

        preview_raw = preview_raw["tweet"]

        # Quote
        quote_url = ""
        quote_text = ""
        quote_author_name = ""
        quote_author_url = ""
        quote_author_screen_name = ""
        quote = preview_raw.get("quote")
        if quote is not None:
            quote_url = quote["url"]
            quote_text = quote["text"]
            quote_author_name = quote["author"]["name"]
            quote_author_url = quote["author"]["url"]
            quote_author_screen_name = quote["author"]["screen_name"]

        # List of elements to substitute for in the raw text message
        facets: list[Facet] = []
        facets_raw = preview_raw["raw_text"].get("facets")
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
                # Ignore 'media' type because API returns wrong indices for them
                if facet:
                    facets.append(facet)

        # Multimedia
        media = preview_raw.get("media")
        mosaic: Photo = None
        photos: list[Photo] = []
        videos: list[Video] = []
        if media is not None:
            mosaic = media.get("mosaic")
            if mosaic is not None:
                mosaic = Photo(
                    width=int(mosaic.get("width", 0)),
                    height=int(mosaic.get("height", 0)),
                    url=mosaic["formats"]["webp"]
                )

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

        # Community Note
        community_note_text = ""
        community_note = preview_raw.get("community_note")
        if community_note is not None:
            community_note_text = community_note["text"]

        # Remove useless non-functional links added at the end of some tweets with media attached
        text_raw = re.sub(r"https://t\.co/[A-Za-z0-9]{10}", "", preview_raw["raw_text"]["text"])
        quote_text_raw = re.sub(r"https://t\.co/[A-Za-z0-9]{10}", "", quote_text)

        # Poll
        poll = None
        poll_raw = preview_raw.get("poll")
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

        # Replies, shares, likes, views
        replies = await self.format_interaction(preview_raw["replies"])
        shares = await self.format_interaction(preview_raw["retweets"])
        likes = await self.format_interaction(preview_raw["likes"])
        views = await self.format_interaction(preview_raw["views"])

        return Preview(
            text=text_raw,
            markdown=None,
            replies=replies,
            reposts=shares,
            likes=likes,
            views=views,
            community_note=community_note_text,
            author_name=preview_raw["author"]["name"],
            author_screen_name=preview_raw["author"]["screen_name"],
            author_url=preview_raw["author"]["url"],
            tweet_date=preview_raw["created_timestamp"],
            mosaic=mosaic,
            photos=photos,
            videos=videos,
            facets=facets,
            poll=poll,
            link=None,
            quote_url=quote_url,
            quote_text=quote_text_raw,
            quote_markdown=None,
            quote_author_name=quote_author_name,
            quote_author_url=quote_author_url,
            quote_author_screen_name=quote_author_screen_name
        )

    async def replace_facets(self, text: str, facets: list[Facet], is_html: bool = False) -> str:
        """
        Replace mentions, tags, URLs in raw_text with appropriate links
        :param text: raw text of the message
        :param facets: list of elements sorted by byte_start with data about replacements
        :param is_html: should method return text with HTML or Markdown
        :return: text with replacements
        """
        text_array = []
        start = 0
        for facet in facets:
            # Append normal text
            text_array.append(text[start:facet.byte_start])
            # Append text replacement from facet
            if is_html:
                new_text = f"<a href=\"{facet.url}\">{facet.text}</a>"
            else:
                new_text = f"[{facet.text}]({facet.url})"
            text_array.append(new_text)
            start = facet.byte_end
        # Append the remaining text
        text_array.append(text[start:])
        return "".join(text_array)

    async def prepare_message_text(self, preview: Preview) -> Tuple[str, str]:
        """
        Prepare Twitter preview message text
        :param preview: Preview object with data from API
        :return: body and HTML for preview message
        """
        # Author, text
        body_text = preview.text
        html_text = preview.text
        if preview.text and preview.facets:
            preview.facets.sort(key=lambda f: f.byte_start)
            body_text = await self.replace_facets(preview.text, preview.facets)
            html_text = await self.replace_facets(preview.text, preview.facets, is_html=True)
        if preview.markdown:
            body_text = preview.markdown
        author_name = preview.author_name if preview.author_name else preview.author_screen_name
        body = f"> [**{author_name}** **(@{preview.author_screen_name})**]({preview.author_url})   \n>  \n"
        if body_text:
            body += f"> {body_text.replace('\n', '  \n> ')}  \n>  \n"
        html = (
            f"<blockquote>"
            f"<p><a href=\"{preview.author_url}\"><b>{author_name} (@{preview.author_screen_name})</b></a></p>"
        )
        if html_text:
            html += f"<p>{html_text.replace('\n', '<br>')}</p>"

        # Poll
        if preview.poll:
            poll_html = []
            poll_body = []
            for choice in preview.poll.choices:
                poll_body.append(f"> > {await self.get_chart_bar(choice.percentage)}  \n> > {choice.percentage}% {choice.label}  \n")
                poll_html.append(f"{await self.get_chart_bar(choice.percentage)}<br>{choice.percentage}% {choice.label}")
            body += f"{''.join(poll_body)}> >  \n> > {preview.poll.total_voters:,} voters • {preview.poll.status}  \n>  \n".replace(",", " ")
            html += (f"<blockquote><p>{'<br>'.join(poll_html)}</p><p>{preview.poll.total_voters:,} voters • {preview.poll.status}</p></blockquote>"
                     .replace(",", " "))

        # Quote
        if preview.quote_author_screen_name:
            quote_body = preview.quote_markdown if preview.quote_markdown is not None else preview.quote_text
            body += (f"> > [**Quoting**]({preview.quote_url}) {preview.quote_author_name} "
                     f"**([@{preview.quote_author_screen_name}]({preview.quote_author_url}))**  \n")
            if quote_body:
                body += f"> > {quote_body.replace('\n', '  \n> > ')}  \n"
            body += ">  \n"
            html += (f"<blockquote>"
                     f"<p><a href=\"{preview.quote_url}\"><b>Quoting</b></a> <b>{preview.quote_author_name} "
                     f"(</b><a href=\"{preview.quote_author_url}\"><b>@{preview.quote_author_screen_name}</b></a><b>)</b></p>")
            if preview.quote_text:
                html += f"<p>{preview.quote_text.replace('\n', '<br>')}</p>"
            html += "</blockquote>"

        # Replies, retweets, likes, views
        if preview.replies:
            body += f"> 💬 {preview.replies}  🔁 {preview.reposts}  ❤️ {preview.likes} "
            html += f"<p><b>💬 {preview.replies}  🔁 {preview.reposts}  ❤️ {preview.likes} "
            if preview.views:
                body += f" 👁️ {preview.views}"
                html += f" 👁️ {preview.views}"
            body += "  \n>  \n"
            html += "</b></p>"

        # Multimedia list
        if len(preview.videos) > 0:
            i = 1
            videos = []
            videos_html = []
            for video in preview.videos:
                videos.append(f"[Vid#{i}]({video.url})")
                videos_html.append(f"<a href=\"{video.url}\">Vid#{i}</a>")
                i += 1
            body += f"> **Videos:** {', '.join(videos)}  \n>  \n"
            html += f"<p><b>Videos: </b>{', '.join(videos_html)}</p>"
        if len(preview.photos) > 0:
            i = 1
            photos = []
            photos_html = []
            for photo in preview.photos:
                photos.append(f"[Pic#{i}]({photo.url})")
                photos_html.append(f"<a href=\"{photo.url}\">Pic#{i}</a>")
                i += 1
            body += f"> **Photos:** {', '.join(photos)}  \n>  \n"
            html += f"<p><b>Photos: </b>{', '.join(photos_html)}</p>"

        # External link
        if preview.link:
            body += f"> > [**{preview.link.title}**]({preview.link.url})"
            html += f"<blockquote><p><a href=\"{preview.link.url}\"><b>{preview.link.title}</b></a></p>"
            if preview.link.description:
                body += f"  \n> > {preview.link.description}"
                html += f"<p>{preview.link.description}</p>"
            body += "  \n>  \n"
            html += "</blockquote>"

        # Community Note
        if preview.community_note:
            body += f"> > **Community Note:**  \n> > {preview.community_note.replace('\n', '  \n> > ')}  \n>  \n"
            html += f"<blockquote><p><b>Community Note:</b></p><p>{preview.community_note.replace('\n', '<br>')}</p></blockquote>"

        # Footer, date
        body += f"> **MautrFxEmbed**"
        html += f"<p><b><sub>MautrFxEmbed</sub></b>"
        if preview.tweet_date:
            body += f"** • {strftime('%Y-%m-%d %H:%M', localtime(preview.tweet_date))}**"
            html += f"<sub><b> • {strftime('%Y-%m-%d %H:%M', localtime(preview.tweet_date))}</sub></b>"
        html += "</p>"
        return body, html

    async def get_chart_bar(self, percentage: float) -> str:
        dark_block = "█"
        light_block = "░"
        dark_num = round(percentage * 16 / 100)
        return f"{dark_num * dark_block + (16 - dark_num) * light_block}"

    async def prepare_message(self, preview: Preview) -> TextMessageEventContent:
        """
        Prepare Twitter preview message text
        :param preview: Preview object with data from API
        :return: body and HTML for preview message
        """
        # Author, text
        body_text = preview.text
        html_text = preview.text
        if preview.text and preview.facets:
            preview.facets.sort(key=lambda f: f.byte_start)
            body_text = await self.replace_facets(preview.text, preview.facets)
            html_text = await self.replace_facets(preview.text, preview.facets, is_html=True)
        if preview.markdown:
            body_text = preview.markdown
        author_name = preview.author_name if preview.author_name else preview.author_screen_name
        body = f"> [**{author_name}** **(@{preview.author_screen_name})**]({preview.author_url})   \n>  \n"
        if body_text:
            body += f"> {body_text.replace('\n', '  \n> ')}  \n>  \n"
        html = (
            f"<blockquote>"
            f"<p><a href=\"{preview.author_url}\"><b>{author_name} (@{preview.author_screen_name})</b></a></p>"
        )
        if html_text:
            html += f"<p>{html_text.replace('\n', '<br>')}</p>"

        # Poll
        if preview.poll:
            poll_html = []
            poll_body = []
            for choice in preview.poll.choices:
                poll_body.append(f"> > {await self.get_chart_bar(choice.percentage)}  \n> > {choice.percentage}% {choice.label}  \n")
                poll_html.append(f"{await self.get_chart_bar(choice.percentage)}<br>{choice.percentage}% {choice.label}")
            body += f"{''.join(poll_body)}> >  \n> > {preview.poll.total_voters:,} voters • {preview.poll.status}  \n>  \n".replace(",", " ")
            html += (f"<blockquote><p>{'<br>'.join(poll_html)}</p><p>{preview.poll.total_voters:,} voters • {preview.poll.status}</p></blockquote>"
                     .replace(",", " "))

        # Multimedia previews
        if len(preview.videos) + len(preview.photos) == 1:
            if len(preview.videos) > 0:
                image = Photo(
                    url=preview.videos[0].thumbnail_url,
                    width=preview.videos[0].width,
                    height=preview.videos[0].height
                )
                full_url = preview.videos[0].url
            else:
                image = preview.photos[0]
                full_url = image.url
            # Resize the image - maybe get thumbnails from API if available?
            # Upload the resized image
            image_mxc = await self.get_matrix_image_url(image, 200)
            # Wait 0.2s
            # Make preview big, like 200x200
            if image_mxc:
                body += f"> [![]({image_mxc})]({full_url})  \n>  \n"
                html += f"<a href=\"{full_url}\"><img src=\"{image_mxc}\" alt=\"\" height=\"200\" ></a>"
        elif len(preview.videos) + len(preview.photos) > 1:
            thumbs = []
            for vid in preview.videos:
                image = Photo(
                    url=vid.thumbnail_url,
                    width=vid.width,
                    height=vid.height
                )
                full_url = vid.url
                thumbs.append((image, full_url))
            for pic in preview.photos:
                thumbs.append((pic, pic.url))
            body_thumbs = []
            html_thumbs = []
            for thumb in thumbs:
                # Upload the resized image
                image_mxc = await self.get_matrix_image_url(thumb[0], 200)
                # Wait 0.2s
                # Make preview big, like 200x200
                if image_mxc:
                    body_thumbs.append(f"[![]({image_mxc})]({thumb[1]})")
                    html_thumbs.append(f"<a href=\"{thumb[1]}\"><img src=\"{image_mxc}\" alt=\"\" height=\"200\" ></a>")
            body += f"> {" ".join(body_thumbs)}"
            html += f"<p>{" ".join(body_thumbs)}</p>"

        # Multimedia list
        if len(preview.videos) > 0:
            i = 1
            videos = []
            videos_html = []
            for video in preview.videos:
                videos.append(f"[Vid#{i}]({video.url})")
                videos_html.append(f"<a href=\"{video.url}\">Vid#{i}</a>")
                i += 1
            body += f"> **Videos:** {', '.join(videos)}  \n>  \n"
            html += f"<p><b>Videos: </b>{', '.join(videos_html)}</p>"
        if len(preview.photos) > 0:
            i = 1
            photos = []
            photos_html = []
            for photo in preview.photos:
                photos.append(f"[Pic#{i}]({photo.url})")
                photos_html.append(f"<a href=\"{photo.url}\">Pic#{i}</a>")
                i += 1
            body += f"> **Photos:** {', '.join(photos)}  \n>  \n"
            html += f"<p><b>Photos: </b>{', '.join(photos_html)}</p>"

        # Quote
        if preview.quote_author_screen_name:
            quote_body = preview.quote_markdown if preview.quote_markdown is not None else preview.quote_text
            body += (f"> > [**Quoting**]({preview.quote_url}) {preview.quote_author_name} "
                     f"**([@{preview.quote_author_screen_name}]({preview.quote_author_url}))**  \n")
            if quote_body:
                body += f"> > {quote_body.replace('\n', '  \n> > ')}  \n"
            body += ">  \n"
            html += (f"<blockquote>"
                     f"<p><a href=\"{preview.quote_url}\"><b>Quoting</b></a> <b>{preview.quote_author_name} "
                     f"(</b><a href=\"{preview.quote_author_url}\"><b>@{preview.quote_author_screen_name}</b></a><b>)</b></p>")
            if preview.quote_text:
                html += f"<p>{preview.quote_text.replace('\n', '<br>')}</p>"
            html += "</blockquote>"

        # Replies, retweets, likes, views
        if preview.replies:
            body += f"> 💬 {preview.replies}  🔁 {preview.reposts}  ❤️ {preview.likes} "
            html += f"<p><b>💬 {preview.replies}  🔁 {preview.reposts}  ❤️ {preview.likes} "
            if preview.views:
                body += f" 👁️ {preview.views}"
                html += f" 👁️ {preview.views}"
            body += "  \n>  \n"
            html += "</b></p>"

        # External link
        if preview.link:
            body += f"> > [**{preview.link.title}**]({preview.link.url})"
            html += f"<blockquote><p><a href=\"{preview.link.url}\"><b>{preview.link.title}</b></a></p>"
            if preview.link.description:
                body += f"  \n> > {preview.link.description}"
                html += f"<p>{preview.link.description}</p>"
            body += "  \n>  \n"
            html += "</blockquote>"

        # Community Note
        if preview.community_note:
            body += f"> > **Community Note:**  \n> > {preview.community_note.replace('\n', '  \n> > ')}  \n>  \n"
            html += f"<blockquote><p><b>Community Note:</b></p><p>{preview.community_note.replace('\n', '<br>')}</p></blockquote>"

        # Footer, date
        body += f"> **MautrFxEmbed**"
        html += f"<p><b><sub>MautrFxEmbed</sub></b>"
        if preview.tweet_date:
            body += f"** • {strftime('%Y-%m-%d %H:%M', localtime(preview.tweet_date))}**"
            html += f"<sub><b> • {strftime('%Y-%m-%d %H:%M', localtime(preview.tweet_date))}</sub></b>"
        html += "</p>"

        return TextMessageEventContent(
            msgtype=MessageType.NOTICE,
            format=Format.HTML,
            body=body,
            formatted_body=html
        )


    async def get_matrix_image_url(self, image: Photo, new_size: int) -> str | None:
        """
        Download image from external URL and upload it to Matrix
        :param url: external URL
        :return: matrix mxc URL
        """
        try:
            # Download image from external source
            data = await self.get_image(image.url)
            content_type = await asyncio.get_event_loop().run_in_executor(
                None,
                filetype.guess,
                data
            )
            if not content_type:
                raise TypeError("Failed to determine file type")
            if content_type not in filetype.image_matchers:
                raise TypeError("Downloaded file is not an image")
            # API's response doesn't provide information about dimensions for mosaic
            if not image.width and not image.height:
                image.width, image.height = await asyncio.get_event_loop().run_in_executor(
                    None,
                    self.get_image_dimensions,
                    data
                )

            width, height = await self.calculate_dimensions(new_size, image.width, image.height)

            # Generate thumbnail
            image_data = await asyncio.get_event_loop().run_in_executor(
                None,
                self.get_thumbnail,
                (data, width, height)
            )

            # Upload image to Matrix server
            mxc_uri = await self.client.upload_media(
                data=image_data,
                mime_type=content_type.mime,
                filename=f"thumbnail.{content_type.extension}",
                size=len(data))
            return mxc_uri
        except ClientError as e:
            self.log.error(f"Downloading image - connection failed: {e}")
        except Exception as e:
            self.log.error(f"Uploading image to Matrix server: {e}")

    async def calculate_dimensions(self, new_size: int, width: int, height: int) -> tuple[int, int]:
        if width > new_size and height > new_size:
            return width, height
        if width >= height:
            return new_size, int(new_size * height / width)
        return int(new_size * width / height), new_size


    def get_thumbnail(self, image: tuple[bytes, int, int]) -> bytes:
        """
        Convert original thumbnail into 100x100 one
        :param image: image data as bytes
        :return: new image data as bytes
        """
        img = Image.open(io.BytesIO(image[0]))
        img.thumbnail((image[1], image[2]), Image.Resampling.LANCZOS)
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, img.format)
        image = img_byte_arr.getvalue()
        return image

    async def prepare_message_old(self, preview: Preview) -> MessageEventContent:
        """
        Prepare preview message, including image attachment
        :param preview: Preview object with data from API
        :return: Preview message
        """
        image_url = ""
        width = 0
        height = 0
        # Choose an image to be attached to the message
        if preview.mosaic:
            image_url = preview.mosaic.url
            width = preview.mosaic.width
            height = preview.mosaic.height
        elif preview.videos:
            image_url = preview.videos[0].thumbnail_url
            width = preview.videos[0].width
            height = preview.videos[0].height
        elif preview.photos:
            image_url = preview.photos[0].url
            width = preview.photos[0].width
            height = preview.photos[0].height

        await self.replace_urls_base(preview)
        body, html = await self.prepare_message_text(preview)

        if image_url:
            try:
                # Download image from external source
                data = await self.get_image(image_url)
                content_type = await asyncio.get_event_loop().run_in_executor(
                    None,
                    filetype.guess,
                    data
                )
                if not content_type:
                    raise TypeError("Failed to determine file type")
                if content_type not in filetype.image_matchers:
                    raise TypeError("Downloaded file is not an image")
                # API's response doesn't provide information about dimensions for mosaic
                if not width and not height:
                    width, height = await asyncio.get_event_loop().run_in_executor(
                        None,
                        self.get_image_dimensions,
                        data
                    )
                # Upload image to Matrix server
                mxc_uri = await self.client.upload_media(
                    data=data,
                    mime_type=content_type.mime,
                    filename=f"image.{content_type.extension}",
                    size=len(data))
                return MediaMessageEventContent(
                    url=mxc_uri,
                    body=body,
                    format=Format.HTML,
                    formatted_body=html,
                    filename=f"image.{content_type.extension}",
                    msgtype=MessageType.IMAGE,
                    external_url=image_url,
                    info=ImageInfo(
                        mimetype=content_type.mime,
                        size=len(data),
                        width=width,
                        height=height
                    ))
            except aiohttp.ClientError as e:
                self.log.error(f"Downloading image - connection failed: {e}")
            except Exception as e:
                self.log.error(f"Uploading image to Matrix server: {e}")

        return TextMessageEventContent(
            msgtype=MessageType.NOTICE,
            format=Format.HTML,
            body=body,
            formatted_body=html
        )

    async def replace_urls_base(self, preview: Preview) -> None:
        """
        If appropriate config values are set, replace original URL with Nitter equivalents
        :param preview: Preview object with data from API
        :return:
        """
        if not self.config["nitter_redirect"]:
            return
        if self.config["nitter_redirect"]:
            if preview.author_url:
                preview.author_url = preview.author_url.replace("x.com", self.config["nitter_url"])
            if preview.quote_author_url:
                preview.quote_author_url = preview.quote_author_url.replace(
                    "x.com",
                    self.config["nitter_url"]
                )
            if preview.quote_url:
                preview.quote_url = preview.quote_url.replace("x.com", self.config["nitter_url"])
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

    async def get_preview(self, url: str) -> Any:
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

    async def get_canonical_urls(self, urls: list[tuple[str, str]]) -> list[str]:
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
            m = re.match(r"(https://.+\.[A-Za-z]+)/@[A-Za-z0-9_]+/([0-9]+)", url[1])
            if m is not None:
                new_url = m.groups()[0] + "/api/v1/statuses/" + m.groups()[1]
                canonical_urls.append(new_url)
        return canonical_urls

    async def get_image(self, url: str) -> bytes | None:
        """
        Download image from external URL
        :param url: external URL
        :return: image data as bytes
        """
        try:
            response = await self.http.get(url, raise_for_status=True)
            return await response.read()
        except aiohttp.ClientError as e:
            self.log.error(f"Preparing image - connection failed: {url}: {e}")
        except Exception as e:
            self.log.error(f"Preparing image - unknown error: {url}: {e}")

    def get_image_dimensions(self, image: bytes) -> Tuple[int, int]:
        """
        Examine image dimensions
        :param image: image data as bytes
        :return: Tuple with image width and height
        """
        try:
            img = Image.open(io.BytesIO(image))
            return img.width, img.height
        except (ValueError, TypeError, FileNotFoundError, UnidentifiedImageError) as e:
            self.log.error(f"Error reading image dimensions: {e}")
            # Return the default image dimensions for large previews
            return 0, 0

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config
