import re
from typing import Any, Type

from mautrix.types import TextMessageEventContent, MessageType, Format
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from maubot import Plugin, MessageEvent
from maubot.handlers import command

from .formatters.blog import Blog
from .formatters.forum import Forum
from .formatters.sharedfmt import SharedFmt
from .parsers.bsky import Bsky
from .parsers.mastodon import Mastodon
from .parsers.twitter import Twitter
from .parsers.reddit import Reddit
from .parsers.instagram import Instagram
from .parsers.tiktok import Tiktok
from .parsers.lemmy import Lemmy
from .resources.datastructures import BlogPost, ForumPost
from .resources.utils import Utilities


class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("nitter_redirect")
        helper.copy("nitter_url")
        helper.copy("player")
        helper.copy("show_nsfw")
        helper.copy("thumbnail_large")
        helper.copy("thumbnail_small")
        helper.copy("forum_max_length")
        helper.copy("twitter_domains")
        helper.copy("bluesky_domains")
        helper.copy("instagram_domains")
        helper.copy("tiktok_domains")
        helper.copy("reddit_domains")
        helper.copy("lemmy_domains")


class MautrFxEmbedBot(Plugin):
    REDDIT_PATTERN = re.compile(
        r"https://[A-Za-z0-9.]*?/r/[A-Za-z0-9]+/comments/([A-Za-z0-9].*?)/.*?/([A-Za-z0-9]+)?"
    )
    MASTODON_PATTERN = re.compile(r"(https://.+\.[A-Za-z]+)/@[A-Za-z0-9_]+/([0-9]+)")

    utils = None
    blog = None
    forum = None
    sharedfmt = None
    parsers = None

    async def start(self) -> None:
        await super().start()
        self.config.load_and_update()
        files = {
            "play": await self.loader.read_file("mautrfx_embed/blobs/play.png"),
            "nsfw_vid": await self.loader.read_file("mautrfx_embed/blobs/warning_video.png"),
            "nsfw_pic": await self.loader.read_file("mautrfx_embed/blobs/warning_image.png"),
        }
        self.utils = Utilities(
            bot=self,
            files=files
        )
        self.sharedfmt = SharedFmt(
            utils=self.utils
        )
        self.blog = Blog(
            utils=self.utils,
            fmt=self.sharedfmt
        )
        self.forum = Forum(
            utils=self.utils,
            fmt=self.sharedfmt
        )
        self.parsers = {
            "mastodon": Mastodon(loop=self.loop, utils=self.utils),
            "bsky": Bsky(loop=self.loop, utils=self.utils),
            "twitter": Twitter(utils=self.utils),
            "reddit": Reddit(utils=self.utils),
            "instagram": Instagram(loop=self.loop),
            "tiktok": Tiktok(loop=self.loop),
            "lemmy": Lemmy(utils=self.utils)
        }

    @command.passive(r"(https?://\S+)", multiple=True)
    async def embed(self, evt: MessageEvent, matches: list[tuple[str, str]]) -> None:
        if evt.sender == self.client.mxid:
            return
        canonical_urls = await self._get_api_urls(matches)
        if not canonical_urls:
            return
        await evt.mark_read()

        previews = []
        for url in canonical_urls:
            if url[0] in ("instagram", "tiktok"):
                preview_raw = await self.utils.get_html_preview(url[1])
            else:
                preview_raw = await self.utils.get_preview(url[1])
            if preview_raw:
                try:
                    preview = await self._parse_preview(preview_raw, url[0])
                    previews.append(preview)
                except ValueError as e:
                    self.log.error(f"Error parsing preview: {e}")
        for preview in previews:
            content = await self._prepare_message(preview)
            await evt.respond(content)

    async def _get_api_urls(self, urls: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """
        Extract canonical URLs from a list of URLs
        :param urls: list of URLs
        :return: list of canonical URLs
        """
        canonical_urls = []
        handlers = [
            self._handle_twitter,
            self._handle_bluesky,
            self._handle_instagram,
            self._handle_tiktok,
            self._handle_reddit,
            self._handle_mastodon,
            self._handle_lemmy
        ]
        for _, url in urls:
            for handler in handlers:
                result = await handler(url)
                if result:
                    canonical_urls.append(result)
                    break
        return canonical_urls

    async def _handle_twitter(self, url: str) -> tuple[str, str] | None:
        for domain in self.config["twitter_domains"]:
            if url.startswith(f"https://{domain}"):
                return "twitter", url.replace(domain, "api.fxtwitter.com")
        return None

    async def _handle_bluesky(self, url: str) -> tuple[str, str] | None:
        for domain in self.config["bluesky_domains"]:
            if url.startswith(f"https://{domain}/profile"):
                new_url = (
                    url
                    .replace(
                        f"{domain}/profile",
                        "api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri=at:/"
                    )
                    .replace("/post/", "/app.bsky.feed.post/")
                )
                return "bsky", f"{new_url}&depth=0"
        return None

    async def _handle_instagram(self, url: str) -> tuple[str, str] | None:
        for domain in self.config["instagram_domains"]:
            if url.startswith(f"https://{domain}/reel"):
                return "instagram", url.replace(domain, "www.instagram.com")
        return None

    async def _handle_tiktok(self, url: str) -> tuple[str, str] | None:
        for domain in self.config["tiktok_domains"]:
            if url.startswith(f"https://{domain}"):
                return "tiktok", url.replace(domain, "vm.tiktok.com")
        return None

    async def _handle_reddit(self, url: str) -> tuple[str, str] | None:
        for domain in self.config["reddit_domains"]:
            if url.startswith(f"https://{domain}"):
                m = self.REDDIT_PATTERN.match(url)
                if m is not None:
                    if m.group(2) is not None:
                        return "reddit", f"https://api.reddit.com/api/info/?id=t1_{m.group(2)}"
                    return "reddit", f"https://api.reddit.com/api/info/?id=t3_{m.group(1)}"
        return None

    async def _handle_mastodon(self, url: str) -> tuple[str, str] | None:
        m = self.MASTODON_PATTERN.match(url)
        if m is not None:
            return "mastodon", f"{m.group(1)}/api/v1/statuses/{m.group(2)}"
        return None

    async def _handle_lemmy(self, url: str) -> tuple[str, str] | None:
        for domain in self.config["lemmy_domains"]:
            if url.startswith(f"https://{domain}/post"):
                parameters_start = url.find("?")
                if parameters_start != -1:
                    url = url[:parameters_start]
                return "lemmy", url.replace("/post/", "/api/v3/post?id=")
        return None

    async def _parse_preview(self, preview_raw: Any, service: str) -> BlogPost | ForumPost | None:
        for key, parser in self.parsers.items():
            if service == key:
                return await parser.parse_preview(preview_raw)
        return None

    async def _prepare_message(self, data: Any) -> TextMessageEventContent:
        if data.qtype in ["twitter", "bsky", "mastodon"]:
            return await self._blog_message(data)
        return await self._forum_message(data)

    async def _blog_message(self, post: BlogPost) -> TextMessageEventContent:
        """
        Prepare preview message text for blog type of post
        :param post: BlogPost object with data from API
        :return: text message content
        """
        await self.blog.tw_replace_urls(post)

        html = ""
        body = ""

        # Author
        html += await self.blog.get_author(post)
        body += await self.blog.get_author(post, False)

        # Text
        html += await self.blog.get_text(post)
        body += await self.blog.get_text(post, False)

        # Translation
        html += await self.blog.get_translation(post)
        body += await self.blog.get_translation(post, False)

        # Poll
        html += await self.blog.get_poll(post)
        body += await self.blog.get_poll(post, False)

        # Multimedia previews only for HTML version
        html += await self.sharedfmt.get_media_previews(post.photos, post.videos, post.sensitive)

        # Multimedia list for clients that have problems displaying images/links
        # Videos
        html += await self.sharedfmt.get_media_list(post.videos, post.sensitive)
        body += await self.sharedfmt.get_media_list(post.videos, post.sensitive, False)
        # Photos
        html += await self.sharedfmt.get_media_list(post.photos, post.sensitive)
        body += await self.sharedfmt.get_media_list(post.photos, post.sensitive, False)

        # Quote
        html += await self.blog.get_quote(post.quote)
        body += await self.blog.get_quote(post.quote, False)

        # External link
        html += await self.blog.get_external_link(post.link)
        body += await self.blog.get_external_link(post.link, False)

        # Replies, retweets, likes, views
        html += await self.blog.get_interactions(post)
        body += await self.blog.get_interactions(post, False)

        # Community Note
        html += await self.blog.get_community_note(post.community_note)
        body += await self.blog.get_community_note(post.community_note, False)

        # Footer, date
        html += await self.sharedfmt.get_footer(post.name, post.post_date)
        body += await self.sharedfmt.get_footer(post.name, post.post_date, False)

        html = f"<blockquote>{html}</blockquote>"

        return TextMessageEventContent(
            msgtype=MessageType.NOTICE,
            format=Format.HTML,
            body=body,
            formatted_body=html
        )

    async def _forum_message(self, post: ForumPost) -> TextMessageEventContent:
        """
        Prepare preview message text for forum type of post
        :param post: ForumPost object with data from API
        :return: text message content
        """
        html = ""
        body = ""

        # Author
        html += await self.forum.get_title(post)
        body += await self.forum.get_title(post, False)

        # Text
        html += await self.forum.get_text(post)
        body += await self.forum.get_text(post, False)

        # Multimedia previews only for HTML version
        if not post.spoiler:
            html += await self.sharedfmt.get_media_previews(post.photos, post.videos, post.nsfw)

        if not post.is_link:
            # Multimedia list for clients that have problems displaying images/links
            # Should not be displayed for simple website thumbnails
            # Videos
            html += await self.sharedfmt.get_media_list(post.videos, post.nsfw)
            body += await self.sharedfmt.get_media_list(post.videos, post.nsfw, False)
            # Photos
            html += await self.sharedfmt.get_media_list(post.photos, post.nsfw)
            body += await self.sharedfmt.get_media_list(post.photos, post.nsfw, False)

        # Replies, retweets, likes, views
        html += await self.forum.get_interactions(post)
        body += await self.forum.get_interactions(post, False)

        # Footer, date
        html += await self.sharedfmt.get_footer(post.name, post.post_date)
        body += await self.sharedfmt.get_footer(post.name, post.post_date, False)

        html = f"<blockquote>{html}</blockquote>"

        return TextMessageEventContent(
            msgtype=MessageType.NOTICE,
            format=Format.HTML,
            body=body,
            formatted_body=html
        )

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config
