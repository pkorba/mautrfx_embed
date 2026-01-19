import io
from time import strptime, mktime
from typing import Any

from PIL import Image, ImageFile, ImageFilter, UnidentifiedImageError
from aiohttp import ClientTimeout, ClientError
from mautrix.errors import MatrixResponseError
from maubot import Plugin

from .datastructures import Media


class Utilities:
    def __init__(
            self,
            bot: Plugin,
            files: dict[str, bytes]
    ) -> None:
        self.bot = bot
        self.files = files
        self.config = self.bot.config
        self.headers = {
            "User-Agent": "MautrFxEmbedBot/1.1.2"
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
            return int(mktime(strptime(created, "%Y-%m-%dT%H:%M:%S.%f%z")))
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
                headers=self.headers,
                timeout=timeout,
                raise_for_status=True
            )
            return await response.read()
        except ClientError as e:
            self.bot.log.error(f"Preparing image - connection failed: {url}: {e}")

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

    def _get_thumbnail(self, image: tuple[bytes, int, int, bool, bool]) -> tuple[bytes, int, int]:
        """
        Convert original thumbnail into 100x100 one
        :param image: tuple that contains image as bytes, width, height, bool that indicates
        whether passed image is a thumbnail to video or just a normal photo,
        bool that indicates whether image should be blurred
        :return: a tuple with thumbnail as bytes, its width and height
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
        Adds a play button overlay to thumbnails of video files
        :param img: the image to add overlay to
        :param overlay: the overlay
        :return: image with a play button overlay
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
            image: Media,
            size: int,
            is_video: bool = False,
            nsfw: bool = False
    ) -> tuple[str, int, int]:
        """
        Download image from external URL and upload its thumbnail to Matrix
        :param image: Media object with data about an image
        :param size: max size of a generated thumbnail
        :param is_video: video file thumbnails get play button overlay added to them
        :param nsfw: True if image needs blurring, False otherwise
        :return: a tuple with matrix mxc URL, width, and height of the thumbnail
        """
        try:
            # Download image from external source
            url = image.thumbnail_url if image.thumbnail_url else image.url
            data = await self.download_image(url)
            if not data:
                return "", 0, 0

            # Generate thumbnail
            image_data, width, height = await self.bot.loop.run_in_executor(
                None,
                self._get_thumbnail,
                (data, size, size, is_video, nsfw)
            )
            if not image_data:
                return "", 0, 0

            # Upload image to Matrix server
            mxc_uri = await self.bot.client.upload_media(
                data=image_data,
                mime_type="image/jpeg",
                filename="thumbnail.jpg",
                size=len(image_data))
            return mxc_uri, width, height
        except ClientError as e:
            self.bot.log.error(f"Downloading image - connection failed: {e}")
            return "", 0, 0
        except (ValueError, MatrixResponseError) as e:
            self.bot.log.error(f"Uploading image to Matrix server: {e}")
            return "", 0, 0

    async def get_instagram_preview(self, url: str) -> str:
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
            response = await self.bot.http.get(
                url,
                headers=headers,
                timeout=timeout,
                raise_for_status=True,
                allow_redirects=False)
            # This header contains direct URL to the video
            return response.headers["location"]
        except ClientError as e:
            self.bot.log.error(f"Connection failed: {e}")
            return ""
        except KeyError as e:
            self.bot.log.error(f"Missing 'location' header: {e}")
            return ""
