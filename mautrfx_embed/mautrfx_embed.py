import re
from typing import Any, Type

from mautrix.types import TextMessageEventContent, MessageType, Format
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from maubot import Plugin, MessageEvent
from maubot.handlers import command

from .formatters.blog import Blog
from .parsers.bsky import Bsky
from .parsers.mastodon import Mastodon
from .parsers.twitter import Twitter
from .parsers.miscellaneous import Miscellaneous
from .resources.datastructures import Post
from .resources.utils import Utilities


class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("nitter_redirect")
        helper.copy("nitter_url")
        helper.copy("player")
        helper.copy("show_nsfw")
        helper.copy("thumbnail_large")
        helper.copy("thumbnail_small")
        helper.copy("twitter_domains")
        helper.copy("bluesky_domains")
        helper.copy("instagram_domains")


class MautrFxEmbedBot(Plugin):
    utils = None
    blog = None
    mastodon = None
    bsky = None
    twitter = None
    misc = None

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
        self.blog = Blog(
            utils=self.utils
        )
        self.mastodon = Mastodon(
            loop=self.loop,
            utils=self.utils
        )
        self.bsky = Bsky(
            loop=self.loop,
            utils=self.utils
        )
        self.twitter = Twitter(
            utils=self.utils
        )
        self.misc = Miscellaneous(
            loop=self.loop
        )

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
            if url.startswith(("https://www.instagram.com/reel", "https://vm.tiktok.com")):
                preview_raw = await self.utils.get_html_preview(url)
            else:
                preview_raw = await self.utils.get_preview(url)
            if preview_raw:
                try:
                    preview = await self._parse_preview(preview_raw, url)
                    previews.append(preview)
                except ValueError as e:
                    self.log.error(f"Error parsing preview: {e}")
        for preview in previews:
            content = await self._prepare_message(preview)
            await evt.respond(content)

    async def _get_canonical_urls(self, urls: list[tuple[str, str]]) -> list[str]:
        """
        Extract canonical URLs from a list of URLs
        :param urls: list of URLs
        :return: list of canonical URLs
        """
        canonical_urls = []
        for url in urls:
            for domain in self.config["twitter_domains"]:
                if url[1].startswith(f"https://{domain}"):
                    canonical_urls.append(url[1].replace(domain, "api.fxtwitter.com"))
                    continue
            for domain in self.config["bluesky_domains"]:
                if url[1].startswith(f"https://{domain}/profile"):
                    new_url = (
                        url[1]
                        .replace(
                            f"{domain}/profile",
                            "api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri=at:/"
                        )
                        .replace("/post/", "/app.bsky.feed.post/")
                    )
                    new_url += "&depth=0"
                    canonical_urls.append(new_url)
                    continue
            for domain in self.config["instagram_domains"]:
                if url[1].startswith(f"https://{domain}/reel"):
                    canonical_urls.append(url[1].replace(domain, "www.instagram.com"))
                    continue
            if url[1].startswith(f"https://vm.tiktok.com"):
                canonical_urls.append(url[1])
            # Mastodon post links
            m = re.match(r"(https://.+\.[A-Za-z]+)/@[A-Za-z0-9_]+/([0-9]+)", url[1])
            if m is not None:
                new_url = m.groups()[0] + "/api/v1/statuses/" + m.groups()[1]
                canonical_urls.append(new_url)
        return canonical_urls

    async def _parse_preview(self, preview_raw: Any, url: str) -> Post:
        if url.startswith("https://api.fxtwitter.com"):
            return await self.twitter.parse_preview(preview_raw)
        if url.startswith("https://api.bsky.app"):
            return await self.bsky.parse_preview(preview_raw)
        if url.startswith("https://www.instagram.com/reel"):
            return await self.misc.parse_instagram_preview(preview_raw)
        if url.startswith("https://vm.tiktok.com"):
            return await self.misc.parse_tiktok_preview(preview_raw)
        return await self.mastodon.parse_preview(preview_raw)

    async def _prepare_message(self, preview: Post) -> TextMessageEventContent:
        """
        Prepare preview message text for blog type of post
        :param preview: Post object with data from API
        :return: text message content
        """
        await self.blog.tw_replace_urls(preview)

        html = ""
        body = ""

        # Author
        html += await self.blog.get_author(preview)
        body += await self.blog.get_author(preview, False)

        # Text
        html += await self.blog.get_text(preview)
        body += await self.blog.get_text(preview, False)

        # Translation
        html += await self.blog.get_translation(preview)
        body += await self.blog.get_translation(preview, False)

        # Poll
        html += await self.blog.get_poll(preview)
        body += await self.blog.get_poll(preview, False)

        # Multimedia previews only for HTML version
        html += await self.blog.get_media_previews(preview)

        # Multimedia list for clients that have problems displaying images/links
        # Videos
        html += await self.blog.get_media_list(preview.videos, preview.sensitive)
        body += await self.blog.get_media_list(preview.videos, preview.sensitive, False)
        # Photos
        html += await self.blog.get_media_list(preview.photos, preview.sensitive)
        body += await self.blog.get_media_list(preview.photos, preview.sensitive, False)

        # Quote
        html += await self.blog.get_quote(preview.quote)
        body += await self.blog.get_quote(preview.quote, False)

        # External link
        html += await self.blog.get_external_link(preview.link)
        body += await self.blog.get_external_link(preview.link, False)

        # Replies, retweets, likes, views
        html += await self.blog.get_interactions(preview)
        body += await self.blog.get_interactions(preview, False)

        # Community Note
        html += await self.blog.get_community_note(preview.community_note)
        body += await self.blog.get_community_note(preview.community_note, False)

        # Footer, date
        html += await self.blog.get_footer(preview.name, preview.post_date)
        body += await self.blog.get_footer(preview.name, preview.post_date, False)

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
