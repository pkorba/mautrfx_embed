import asyncio
from time import strftime, localtime, gmtime

from ..resources.datastructures import Media
from ..resources.utils import Utilities


class SharedFmt:
    def __init__(self, utils: Utilities):
        self.utils = utils

    async def get_media_previews(
            self,
            photos: list[Media],
            videos: list[Media],
            sensitive: bool,
            is_link: bool = False
    ) -> str:
        """
        Get message part that contains media attachment thumbnails
        :param videos: list of videos
        :param photos: list of photos
        :param sensitive: True if contains NSFW media
        :param is_link: True if small thumbnail is requested
        :return: formatted string that contains thumbnails and links to original media
        """
        if len(videos) + len(photos) == 0:
            return ""
        thumbs_data = []
        for i, vid in enumerate(videos):
            if not vid.thumbnail_url:
                continue
            name = f"Vid#{i + 1}" if vid.filetype == "v" else f"Audio#{i + 1}"
            thumbs_data.append((vid, name))

        for i, pic in enumerate(photos):
            thumbs_data.append((pic, f"Pic#{i + 1}"))

        thumbs = []
        for thumb in thumbs_data:
            image_mxc, width, height = await self.utils.get_matrix_image_url(
                thumb[0],
                (
                    self.utils.config["thumbnail_large"]
                    if (len(videos) + len(photos) == 1) and not is_link
                    else self.utils.config["thumbnail_small"]
                ),
                sensitive,
            )
            # To prevent running into ratelimit
            await asyncio.sleep(0.2)
            if image_mxc:
                thumbs.append(f"{await self.get_link(
                    thumb[0].url,
                    await self.get_image(image_mxc, thumb[1], (width, height), True),
                    True
                )}")
        # This can happen if the list contains only audio files without thumbnails
        if not thumbs:
            return ""
        return f"<p>{" ".join(thumbs)}</p>"

    async def get_media_list(self, media: list, nsfw: bool = False, is_html: bool = True) -> str:
        """
        Get message part with a list of media attachments. Also serves as a fallback mechanism
        for client that are not able to display thumbnails
        :param media: list of media attachments
        :param nsfw: True if media contains NSFW content, False otherwise
        :param is_html: True for HTML, False for Markdown
        :return: formatted string with list of media attachments
        """
        if len(media) > 0:
            media_formatted = []
            has_audio = False
            has_video = False
            for i, med in enumerate(media):
                if med.filetype == "v":
                    short = "Vid"
                    has_video = True
                elif med.filetype == "a":
                    short = "Audio"
                    has_audio = True
                else:
                    short = "Pic"
                media_formatted.append(await self.get_link(med.url, f"{short}#{i + 1}", is_html))

            if has_audio and has_video:
                title = "Audio/Videos"
            elif has_audio:
                title = "Audio"
            elif has_video:
                title = "Videos"
            else:
                title = "Photos"
            if nsfw:
                title += " (NSFW)"
            # HTML
            if is_html:
                return f"<p><b>{title}: </b>{', '.join(media_formatted)}</p>"
            # Markdown
            return f"> **{title}:** {', '.join(media_formatted)}  \n>  \n"
        return ""

    async def get_footer(self, name: str, post_date: int, is_html: bool = True) -> str:
        """
        Get message part with footer
        :param name: service's name (e.g. Bluesky)
        :param post_date: post date
        :param is_html: True for HTML, False for Markdown
        :return: formatted string with footer
        """
        date_html = ""
        date_md = ""
        if post_date:
            if self.utils.config["localtime"]:
                time_s = localtime(post_date)
                time_zone = ""
            else:
                time_s = gmtime(post_date)
                time_zone = " UTC"
            date = strftime('%Y-%m-%d %H:%M', time_s)
            date_html = f"<b> • {date}{time_zone}</b>"
            date_md = f" **• {date}{time_zone}**"
        # HTML
        if is_html:
            return f"<p><b>{name}</b>{date_html}</p>"
        # Markdown
        return f"> **{name}**{date_md}"

    async def get_image(
        self,
        src: str,
        alt: str = "",
        size: tuple[int, int] = (0, 0),
        is_html: bool = True
    ) -> str:
        """
        Get inline image
        :param src: source url
        :param alt: alternative text
        :param size: tuple with width and height
        :param is_html: True for HTML, False for Markdown
        :return: formatted string with inline image
        """
        width = f"width=\"{size[0]}\" " if size[0] else ""
        height = f"height=\"{size[1]}\" " if size[1] else ""
        # HTML
        if is_html:
            return f"<img src=\"{src}\" alt=\"{alt}\" {width}{height}/>"
        # Markdown
        return f"![{alt}]({src})"

    async def get_link(self, url: str, text: str, is_html: bool = True) -> str:
        """
        Return a link as HTML or Markdown
        :param url: address
        :param text: displayed text
        :param is_html: True for HTML, False for Markdown
        :return: formatted string with a link
        """
        # HTML
        if is_html:
            return f"<a href=\"{url}\">{text}</a>"
        # Markdown
        return f"[{text}]({url})"
