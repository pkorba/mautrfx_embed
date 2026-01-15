import io
from asyncio import AbstractEventLoop
from time import strptime, mktime
from typing import Any, Mapping

from PIL import Image, ImageFile, UnidentifiedImageError
from aiohttp import ClientSession, ClientTimeout, ClientError
from mautrix.errors import MatrixResponseError
from mautrix.util.logging import TraceLogger
from maubot.client import MaubotMatrixClient

from .datastructures import Media
from ..resources.assets import play


class Utilities:
    def __init__(
            self,
            client: MaubotMatrixClient,
            http: ClientSession,
            loop: AbstractEventLoop,
            log: TraceLogger,
            headers: Mapping[str, str]
    ) -> None:
        self.http = http
        self.log = log
        self.client = client
        self.loop = loop
        self.headers = headers

    async def parse_interaction(self, value: int) -> str:
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
        # Time
        if created:
            return int(mktime(strptime(created, "%Y-%m-%dT%H:%M:%S.%f%z")))
        return 0

    async def download_image(self, url: str) -> bytes | None:
        """
        Download image from external URL
        :param headers:
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

    async def get_preview(self, url: str) -> Any:
        """
        Get results from the API.
        :param headers:
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

    def _get_thumbnail(self, image: tuple[bytes, int, int, bool]) -> tuple[bytes, int, int]:
        """
        Convert original thumbnail into 100x100 one
        :param image: image data as bytes
        :return: new image data as bytes
        """
        try:
            img = Image.open(io.BytesIO(image[0]))
            img.thumbnail((image[1], image[2]), Image.Resampling.LANCZOS)
            if image[3]:
                self._add_playbutton_overlay(img)

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

    def _add_playbutton_overlay(self, img: ImageFile) -> None:
        if not img:
            return
        img_w, img_h = img.size
        try:
            play_img = Image.open(io.BytesIO(play))
            overlay_s = min(img_w, img_h) // 2
            if overlay_s < play_img.width:
                play_img = play_img.resize((overlay_s, overlay_s), Image.Resampling.LANCZOS)
            offset = ((img_w - play_img.width) // 2, (img_h - play_img.width) // 2)
            img.paste(play_img, offset, play_img)
        except (OSError, ValueError, TypeError, FileNotFoundError, UnidentifiedImageError) as e:
            self.log.error(f"Error adding play button overlay to the thumbnail: {e}")
            raise

    async def get_matrix_image_url(
            self,
            image: Media,
            size: int,
            is_video: bool = False
    ) -> tuple[str, int, int]:
        """
        Download image from external URL and upload it to Matrix
        :param url: external URL
        :return: matrix mxc URL
        """
        try:
            # Download image from external source
            data = await self.download_image(image.url)
            if not data:
                return "", 0, 0

            # Generate thumbnail
            image_data, width, height = await self.loop.run_in_executor(
                None,
                self._get_thumbnail,
                (data, size, size, is_video)
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
