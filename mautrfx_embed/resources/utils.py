import io
import re
import time
from calendar import timegm
from time import strptime
from typing import Any

import markdown
from PIL import Image, ImageFile, ImageFilter, UnidentifiedImageError
from aiohttp import ClientTimeout, ClientError
from mautrix.errors import MatrixResponseError
from maubot import Plugin

from .datastructures import Media


class Utilities:
    INSTANCE_NAME = re.compile(r"https://(www\.)?(?P<base_url>.+?)/.*")
    SPOILER_TAG = re.compile(r":::\s?spoiler\s(?:(.*?)\n)?(.*?):::", flags=re.I | re.DOTALL)
    INLINE_SPOILER_TAG = re.compile(r"\|\|(.*?)\|\|", re.DOTALL)
    EMPTY_LINK = re.compile(r"\[]\((.+?)\)")
    FLAIRS_TITLE = re.compile(r"^(?P<flairs>(\[[A-Za-z0-9\s]+?]\s?)*)(?P<title>.*)")
    FLAIR_LIST = re.compile(r"\[(.*?)]")

    def __init__(
            self,
            bot: Plugin,
            files: dict[str, bytes]
    ) -> None:
        self.bot = bot
        self.files = files
        self.config = self.bot.config
        self.headers = {
            "User-Agent": "MautrFxEmbedBot/2.0.0"
        }
        self.headers_fake = {
            "User-Agent": "WhatsApp/2"
        }

    async def parse_interaction(self, value: int) -> str:
        """
        Get shortened representation of a number of interactions
        :param value: number of interactions
        :return: shortened number
        """
        if not value:
            return ""
        millions = divmod(value, 1000000)
        thousands = divmod(millions[1], 1000)
        if millions[0]:
            formatted_value = f"{millions[0]}.{millions[1] // 10000}M"
        elif thousands[0]:
            formatted_value = f"{thousands[0]}.{thousands[1] // 100}K"
        else:
            formatted_value = f"{thousands[1]}"
        return formatted_value

    async def parse_date(self, created: str) -> int:
        """
        Convert date string to seconds since Epoch
        :param created: date string
        :return: seconds since Epoch
        """
        if created:
            return int(timegm(strptime(created, "%Y-%m-%dT%H:%M:%S.%f%z")))
        return 0

    async def download_image(self, url: str) -> bytes | None:
        """
        Download image from external URL
        :param url: URL to an image
        :return: image data as bytes or None if download fails for any reason
        """
        timeout = ClientTimeout(total=20)
        try:
            response = await self.bot.http.get(
                url,
                headers=self.headers_fake,
                timeout=timeout,
                raise_for_status=True
            )
            return await response.read()
        except ClientError as e:
            self.bot.log.error(f"Downloading image - connection failed: {url}: {e}")

    async def get_preview(self, url: str) -> Any:
        """
        Get results from the API.
        :param url: source URL
        :return: JSON API response
        """
        timeout = ClientTimeout(total=20)
        try:
            response = await self.bot.http.get(
                url,
                headers=self.headers,
                timeout=timeout,
                raise_for_status=True
            )
            return await response.json()
        except ClientError as e:
            self.bot.log.error(f"Connection failed: {e}")
            return ""

    async def get_html_preview(self, url: str) -> str:
        """
        Get HTML webpage source.
        :param url: source URL
        :return: text content of the response
        """
        timeout = ClientTimeout(total=20)
        try:
            response = await self.bot.http.get(
                url,
                headers=self.headers_fake,
                timeout=timeout,
                raise_for_status=True
            )
            return await response.text()
        except ClientError as e:
            self.bot.log.error(f"Connection failed: {e}")
            return ""

    async def get_location_header(self, url: str) -> str:
        """
        Get HTML webpage location header.
        :param url: source URL
        :return: text content of the location header
        """
        timeout = ClientTimeout(total=20)
        try:
            response = await self.bot.http.get(
                url,
                headers=self.headers_fake,
                timeout=timeout,
                raise_for_status=True,
                allow_redirects=False
            )
            return response.headers["location"]
        except ClientError as e:
            self.bot.log.error(f"Connection failed: {e}")
            return ""
        except KeyError as e:
            self.bot.log.error(f"Missing 'location' header: {e}")
            return ""

    def _get_thumbnail(self, image: tuple[bytes, int, int, bool, bool]) -> tuple[bytes, int, int]:
        """
        Convert original thumbnail/image into one with specified size
        :param image: tuple that contains: image as bytes, width, height, bool that indicates
        whether passed image is a thumbnail to video or just a normal photo,
        bool that indicates whether image should be blurred
        :return: a tuple with thumbnail as bytes, its width, and height
        """
        try:
            img = Image.open(io.BytesIO(image[0]))
            img.thumbnail((image[1], image[2]), Image.Resampling.LANCZOS)
            # Apply blur if it's a NSFW image or video
            if image[4] and not self.config["show_nsfw"]:
                img = img.filter(ImageFilter.GaussianBlur(40))
                # Add NSFW warning
                if image[3]:
                    self._add_overlay(img, self.files["nsfw_vid"])
                else:
                    self._add_overlay(img, self.files["nsfw_pic"])
            # If it's a thumbnail to a video file and not NSFW, add play button overlay
            elif image[3]:
                self._add_overlay(img, self.files["play"])
            # The result is a JPEG so we have to remove the transparency layer if there is one
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format="JPEG", quality=90)
            img_byte_arr.seek(0)
            image = img_byte_arr.getvalue()
        except (OSError, ValueError, TypeError, FileNotFoundError, UnidentifiedImageError) as e:
            self.bot.log.error(f"Error generating thumbnail: {e}")
            return (b'', 0, 0)
        return image, img.width, img.height

    def _add_overlay(self, img: ImageFile, overlay: bytes) -> None:
        """
        Adds an overlay to thumbnails of video files
        :param img: the image to add overlay to
        :param overlay: the overlay image
        :return: image with an overlay in the middle
        """
        if not img:
            return
        img_w, img_h = img.size
        try:
            play_img = Image.open(io.BytesIO(overlay))
            # The default size of overlays is 100x100
            # If overlay is bigger than thumbnail's half size, resize the overlay
            overlay_s = min(img_w, img_h) // 2
            if overlay_s < play_img.width:
                play_img = play_img.resize((overlay_s, overlay_s), Image.Resampling.LANCZOS)
            offset = ((img_w - play_img.width) // 2, (img_h - play_img.width) // 2)
            img.paste(play_img, offset, play_img)
        except (OSError, ValueError, TypeError, FileNotFoundError, UnidentifiedImageError) as e:
            self.bot.log.error(f"Error adding play button overlay to the thumbnail: {e}")
            raise

    async def get_matrix_image_url(
            self,
            media: Media,
            size: int,
            nsfw: bool = False
    ) -> tuple[str, int, int]:
        """
        Download image from external URL and upload its thumbnail to Matrix server
        :param media: Media object with data about an image
        :param size: max size of a generated thumbnail
        :param nsfw: True if image needs blurring, False otherwise
        :return: a tuple with matrix mxc URL, width, and height of the thumbnail
        """
        # Download image from external source
        if media.thumbnail_url:
            url = media.thumbnail_url
        elif media.filetype == "p" and media.url:
            url = media.url
        else:
            return "", 0, 0

        data = await self.download_image(url)
        if not data:
            return "", 0, 0

        # Generate thumbnail
        image_data, width, height = await self.bot.loop.run_in_executor(
            None,
            self._get_thumbnail,
            (data, size, size, media.filetype != "p", nsfw)
        )
        if not image_data:
            return "", 0, 0

        mxc_uri = await self.upload_media(image_data, "image/jpeg", "thumbnail.jpg")
        return mxc_uri, width, height

    async def upload_media(self, data: bytes, mime: str, name: str) -> str:
        """
        Upload image to Matrix server
        :param data: image data
        :param mime: image mimetype
        :param name: image name
        :return: MXC URL address to the image
        """
        try:
            # Upload image to Matrix server
            return await self.bot.client.upload_media(
                data=data,
                mime_type=mime,
                filename=name,
                size=len(data))
        except (ValueError, MatrixResponseError) as e:
            self.bot.log.error(f"Uploading image to Matrix server: {e}")
            return ""

    async def config_item_contains(self, elems: list[str], item_key: str) -> bool:
        """
        Check if any of string from list of elems occurs in a config's 'key' list
        :param elems: a list of string the occurrence we check for
        :param item_key: key identifying the config list of values
        :return: True if any of the strings is in the list, False otherwise
        """
        if not self.config[item_key]:
            return False
        for elem in elems:
            if elem.lower() in (fl.lower() for fl in self.config[item_key]):
                return True
        return False

    async def fedi_forum_parse_title(self, title: str) -> tuple[str, list]:
        """
        Split title string into title and flair
        :param title: Raw title string from API
        :return: tuple with title and flair
        """
        flairs_str = ""
        flairs: list[str] = []
        m_title = self.FLAIRS_TITLE.match(title)
        if m_title:
            flairs_str = m_title.group("flairs")
            title = m_title.group("title")
        if flairs_str:
            flairs = self.FLAIR_LIST.findall(flairs_str)
        return title, flairs

    def fedi_forum_parse_text(self, text: str) -> str:
        """
        Parse Markdown text of a post and convert it into HTML
        :param text: Markdown body of a post
        :return: HTML text
        """
        if not text:
            return ""
        # Don't try to display inline images, fix escaping, fix newlines
        text = text.replace("![", "[").replace("\\", "").replace("\n", "  \n")
        # For links with no alt text use the URL because they're not visible otherwise
        text = self.EMPTY_LINK.sub(r"[\1](\1)", text)
        # Fix custom spoiler tags that markdown lib can't convert on its own
        text = self.SPOILER_TAG.sub(
            r"<details markdown='1'><summary markdown='1'>\1 </summary>\2</details>",
            text
        )
        text = self.INLINE_SPOILER_TAG.sub(
            r"<span data-mx-spoiler markdown='1'>\1</span>",
            text
        )
        text = markdown.markdown(
            text,
            extensions=["tables", "fenced_code", "md_in_html"],
            output_format="html"
        )
        return text

    def fedi_forum_parse_markdown(self, text: str) -> str:
        """
        Removes unnecessary characters from Markdown body of a post
        :param text: Markdown body of a post
        :return: cleaned Markdown text
        """
        if not text:
            return ""
        # Fix custom spoiler tags
        text = self.SPOILER_TAG.sub(r"[\1] ||\2||", text)
        # Don't try to display inline images and replace faulty newlines
        text = text.replace("![", "[").replace("\\", "").replace("\n", "  \n")
        # For links with no alt text use the URL because they're not visible otherwise
        text = self.EMPTY_LINK.sub(r"[\1](\1)", text)
        return text

    async def get_poll_status(self, expires_at: int) -> str:
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
