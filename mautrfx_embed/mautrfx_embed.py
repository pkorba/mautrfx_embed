import asyncio
import aiohttp
import io
import filetype
from aiohttp import ClientError, ClientTimeout
from maubot import Plugin, MessageEvent
from maubot.handlers import command
from mautrix.types import TextMessageEventContent, MediaMessageEventContent, MessageEventContent, MessageType, ImageInfo, Format
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from PIL import Image
from time import strftime, localtime
from typing import Tuple, Any, Type
from .resources.datastructures import Preview, Photo, Video


class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("nitter_redirect")
        helper.copy("nitter_url")


class MautrFxEmbedBot(Plugin):
    headers = {
        "User-Agent": "MautrFxEmbedBot/1.0.0"
    }
    twitter_domains = ["x.com", "twitter.com",
                       "fixupx.com", "fxtwitter.com",
                       "fixvx.com", "vxtwitter.com",
                       "stupidpenisx.com", "girlcockx.com",
                       "nitter.net", "xcancel.com", "nitter.poast.org", "nitter.privacyredirect.com",
                       "lightbrd.com", "nitter.space", "nitter.tierkoetter.com", "nuku.trabun.org",
                       "nitter.catsarch.com"]
    bsky_domains = ["bsky.app", "fxbsky.app", "skyview.social"]
    # For mastodon domains anything that matches https://?.?/@?/[0-9]? regular expression

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
            preview_raw = await self.get_preview(url)
            if preview_raw:
                preview = await self.parse_twitter_preview(preview_raw)
                previews.append(preview)
        for preview in previews:
            content = await self.prepare_twitter_message(preview)
            await evt.respond(content)

    async def get_preview(self, url: str) -> Any:
        """
        Get results from the API.
        :param url: source URL
        :return: JSON API response
        """
        timeout = ClientTimeout(total=20)
        try:
            response = await self.http.get(url, headers=self.headers, timeout=timeout, raise_for_status=True)
            return await response.json()
        except ClientError as e:
            self.log.error(f"Connection failed: {e}")
            return ""

    async def parse_twitter_preview(self, preview_raw: Any) -> Preview:
        """
        Parse JSON data from FxTwitter API
        :param preview_raw: JSON data
        :return: Preview object
        """
        preview_raw = preview_raw["tweet"]
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
                        width=int(elem["width"]),
                        height=int(elem["height"]),
                        url=elem["url"],
                        thumbnail_url=elem["thumbnail_url"],
                    )
                    videos.append(video)
                elif elem["type"] == "photo":
                    photo = Photo(
                        width=int(elem["width"]),
                        height=int(elem["height"]),
                        url=elem["url"],
                    )
                    photos.append(photo)
        community_note_text = ""
        community_note = preview_raw.get("community_note")
        if community_note is not None:
            community_note_text = community_note["text"]
        return Preview(
            text=preview_raw["text"],
            replies=preview_raw["replies"],
            retweets=preview_raw["retweets"],
            likes=preview_raw["likes"],
            views=preview_raw["views"],
            community_note=community_note_text,
            author_name=preview_raw["author"]["name"],
            author_screen_name=preview_raw["author"]["screen_name"],
            author_url=preview_raw["author"]["url"],
            tweet_date=preview_raw["created_timestamp"],
            mosaic=mosaic,
            photos=photos,
            videos=videos,
            quote_url=quote_url,
            quote_text=quote_text,
            quote_author_name=quote_author_name,
            quote_author_url=quote_author_url,
            quote_author_screen_name=quote_author_screen_name
        )

    async def get_canonical_urls(self, urls: list[tuple[str, str]]) -> list[str]:
        """
        Extract canonical URLs from a list of URLs
        :param urls: list of URLs
        :return: list of canonical URLs
        """
        canonical_urls = []
        for url in urls:
            for domain in self.twitter_domains:
                if domain in url[1]:
                    canonical_urls.append(url[1].replace(domain, "api.fxtwitter.com"))
        return canonical_urls

    async def prepare_twitter_message_text(self, preview: Preview) -> Tuple[str, str]:
        """
        Prepare Twitter preview message text
        :param preview: Preview object with data from API
        :return: body and HTML for preview message
        """
        # Author, text
        body = (f"> [**{preview.author_name}** **(@{preview.author_screen_name})**]({preview.author_url})   \n>  \n"
                f"> {preview.text.replace('\n', '  \n> ')}  \n>  \n")
        html = (
            f"<blockquote>"
            f"<p><a href=\"{preview.author_url}\"><b>{preview.author_name} (@{preview.author_screen_name})</b></a></p>"
            f"<p>{preview.text.replace('\n', '<br>')}</p>"
        )
        # Quote
        if preview.quote_text:
            body += (f"> > [**Quoting**]({preview.quote_url}) {preview.quote_author_name} "
                     f"**([@{preview.quote_author_screen_name}]({preview.quote_author_url}))**  \n> >  \n"
                     f"> > {preview.quote_text.replace('\n', '  \n> > ')}  \n>  \n")
            html += (f"<blockquote>"
                     f"<p><a href=\"{preview.quote_url}\"><b>Quoting</b></a> <b>{preview.quote_author_name} "
                     f"(</b><a href=\"{preview.quote_author_url}\"><b>@{preview.quote_author_screen_name}</b></a><b>)</b></p>"
                     f"<p>{preview.quote_text.replace('\n', '<br>')}</p></blockquote>")
        # Replies, retweets, likes, views
        body += f"> 💬 {preview.replies}  🔁 {preview.retweets}  ❤️ {preview.likes}  👁️ {preview.views}  \n>  \n"
        html += f"<p><b>💬 {preview.replies}  🔁 {preview.retweets}  ❤️ {preview.likes}  👁️ {preview.views}</b></p>"
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
        # Community Note
        if preview.community_note:
            body += f"> > **Community Note:**  \n> >  \n> > {preview.community_note.replace('\n', '  \n> > ')}  \n>  \n"
            html += f"<blockquote><p><b>Community Note:</b></p><p>{preview.community_note.replace('\n', '<br>')}</p></blockquote>"
        # Footer, date
        body += f"> **MautrFxEmbed • {strftime('%Y-%m-%d %H:%M', localtime(preview.tweet_date))}**"
        html += f"<p><b><sub>MautrFxEmbed • {strftime('%Y-%m-%d %H:%M', localtime(preview.tweet_date))}</sub></b></p>"
        return body, html

    async def prepare_twitter_message(self, preview: Preview) -> MessageEventContent:
        """
        Prepare Twitter preview message, including image attachment
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
        body, html = await self.prepare_twitter_message_text(preview)

        if image_url:
            try:
                # Download image from external source
                data = await self.get_image(image_url)
                content_type = await asyncio.get_event_loop().run_in_executor(None, filetype.guess, data)
                if not content_type:
                    raise TypeError("Failed to determine file type")
                if content_type not in filetype.image_matchers:
                    raise TypeError("Downloaded file is not an image")
                # API's response doesn't provide information about dimensions for mosaic
                if not width and not height:
                    width, height = await asyncio.get_event_loop().run_in_executor(None, self.get_image_dimensions, data)
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
        preview.author_url = preview.author_url.replace("x.com", self.config["nitter_url"])
        preview.quote_author_url = preview.quote_author_url.replace("x.com", self.config["nitter_url"])
        preview.quote_url = preview.quote_url.replace("x.com", self.config["nitter_url"])
        if len(preview.photos) > 0:
            for photo in preview.photos:
                photo.url = photo.url.replace("pbs.twimg.com", f"{self.config['nitter_url']}/pic/orig")

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
        img = Image.open(io.BytesIO(image))
        return img.width, img.height

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config
