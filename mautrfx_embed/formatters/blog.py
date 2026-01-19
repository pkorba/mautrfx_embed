import asyncio
import re
from time import strftime, localtime

from ..resources.datastructures import Post, Facet, Link
from ..resources.utils import Utilities


class Blog:
    def __init__(self, utils: Utilities):
        self.utils = utils

    async def get_author(self, data: Post, is_html: bool = True) -> str:
        """
        Get message part that contains data about the author, including link to their profile
        author_display_name (@author_username)
        :param data: Post data
        :param is_html: True for HTML, False for Markdown
        :return: formatted string with data about the author
        """
        author_name = data.author_name if data.author_name else data.author_screen_name
        # HTML
        if is_html:
            return f"<p>{await self._get_link(
                data.author_url,
                f"<b>{author_name} (@{data.author_screen_name})</b>"
            )}</p>"
        # Markdown
        return f"> {await self._get_link(
            data.author_url,
            f"**{author_name}** **(@{data.author_screen_name})**",
            False
        )}   \n>  \n"

    async def get_text(self, data: Post, is_html: bool = True) -> str:
        """
        Get message part that contains the blog post content. Strips Twitter posts from useless
        t.co links and replaces facets.
        :param data: Post data
        :param is_html: True for HTML, False for Markdown
        :return: formatted string with post content
        """
        text = data.text
        if not text:
            return ""
        #HTML
        if is_html:
            if data.facets:
                text = await self._replace_facets(data.text, data.facets, data.qtype)
            # Remove useless t.co links that are added to raw text by the FxTwitter API
            # This has to be done AFTER the facets have been substituted
            if data.qtype == "twitter":
                text = re.sub(r"https://t\.co/[A-Za-z0-9]{10}", "", text)
            if data.spoiler_text:
                return (
                    f"<details>"
                    f"<summary><b>CW:</b> {data.spoiler_text}</summary><br>"
                    f"<p>{text.replace('\n', '<br>')}</p>"
                    f"</details>"
                )
            return f"<p>{text.replace('\n', '<br>')}</p>"

        if data.facets:
            text = await self._replace_facets(data.text, data.facets, data.qtype, False)
        if data.qtype == "twitter":
            text = re.sub(r"https://t\.co/[A-Za-z0-9]{10}", "", text)
        # It's for Mastodon's case, so there are no facets which is why the previous step is ignored
        # Markdown
        if data.markdown:
            text = data.markdown
        return f"> {text.replace('\n', '  \n> ')}  \n>  \n"

    async def get_translation(self, data: Post, is_html: bool = True) -> str:
        """
        Get message part that contains the translation of the post.
        :param data: Post data
        :param is_html: True for HTML, False for Markdown
        :return: formatted string with translation of the post
        """
        if not data.translation:
            return ""

        src_lang = f"from {data.translation_lang}" if data.translation_lang is not None else "text"
        # HTML
        if is_html:
            return (
                f"<blockquote>📝 <b>Translated {src_lang}</b><br>"
                f"{data.translation.replace('\n', '<br>')}"
                f"</blockquote>"
            )
        # Markdown
        return (
            f"> > 📝 **Translated {src_lang}**  \n"
            f"> > {data.translation.replace('\n', '  \n> > ')}  \n>  \n")

    async def get_poll(self, data: Post, is_html: bool = True) -> str:
        """
        Get message part that contains poll
        :param data: Post data
        :param is_html: True for HTML, False for Markdown
        :return: formatted string with poll
        """
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
        # HTML
        if is_html:
            return (
                f"<blockquote>"
                f"<p>{'<br>'.join(poll)}</p>"
                f"<p>{data.poll.total_voters:,} voters • {data.poll.status}</p>"
                f"</blockquote>"
                .replace(",", " ")
            )
        # Markdown
        return (
            f"{''.join(poll)}> >  \n"
            f"> > {data.poll.total_voters:,} voters • {data.poll.status}  \n>  \n"
            .replace(",", " ")
        )

    async def get_media_previews(self, data: Post) -> str:
        """
        Get message part that contains media attachment thumbnails
        :param data: Post data
        :param is_html: True for HTML, False for Markdown
        :return: formatted string that contains thumbnails and links to original media
        """
        if len(data.videos) + len(data.photos) == 0:
            return ""
        thumbs_data = []
        for i, vid in enumerate(data.videos):
            if not vid.thumbnail_url:
                continue
            name = f"Vid#{i + 1}" if vid.filetype == "v" else f"Audio#{i + 1}"
            thumbs_data.append((vid, name, True))

        for i, pic in enumerate(data.photos):
            thumbs_data.append((pic, f"Pic#{i + 1}", False))

        thumbs = []
        for thumb in thumbs_data:
            image_mxc, width, height = await self.utils.get_matrix_image_url(
                thumb[0],
                self.utils.config["thumbnail_large"] if (len(data.videos) + len(data.photos) == 1)
                else self.utils.config["thumbnail_small"],
                thumb[2],
                data.sensitive,
            )
            await asyncio.sleep(0.2)
            if image_mxc:
                thumbs.append(f"{await self._get_link(
                    thumb[0].url,
                    await self._get_image(image_mxc, thumb[1], (width, height), True),
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
            is_audio = False
            is_video = False
            for i, med in enumerate(media):
                if med.filetype == "v":
                    short = "Vid"
                    is_video = True
                elif med.filetype == "a":
                    short = "Audio"
                    is_audio = True
                else:
                    short = "Pic"
                media_formatted.append(await self._get_link(med.url, f"{short}#{i + 1}", is_html))

            if is_audio and is_video:
                title = "Audio/Videos"
            elif is_audio:
                title = "Audio"
            elif is_video:
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

    async def get_quote(self, data: Post, is_html: bool = True) -> str:
        """
        Get message part with quote post
        :param data: Quoted post data
        :param is_html: True for HTML, False for Markdown
        :return: formatted string with quoted post
        """
        if not data:
            return ""
        text = ""
        text += await self.get_quote_author(data, is_html)
        res = await self.get_text(data, is_html)
        text += res if is_html else res.replace("> ", "> > ")
        res = await self.get_poll(data, is_html)
        text += res if is_html else res.replace("> > ", "> > > ")
        if is_html:
            text += await self.get_media_previews(data)
        res = await self.get_media_list(data.videos, data.sensitive, is_html)
        text += res if is_html else res.replace("> ", "> > ")
        res = await self.get_media_list(data.photos, data.sensitive, is_html)
        text += res if is_html else res.replace("> ", "> > ")
        res = await self.get_external_link(data.link, is_html)
        text += res if is_html else res.replace("> > ", "> > > ")
        # HTML
        if is_html:
            return f"<blockquote>{text}</blockquote>"
        # Markdown
        return text

    async def get_quote_author(self, data: Post, is_html: bool = True) -> str:
        """
        Get message part with a link to quoted post and information about its author
        :param data: Quoted post data
        :param is_html: True for HTML, False for Markdown
        :return: formatted string with quoted post link and author name
        """
        if not data.author_screen_name:
            return ""

        link = await self._get_link(data.author_url, f"@{data.author_screen_name}", is_html)
        # HTML
        if is_html:
            return (
                f"<p><b>"
                f"{await self._get_link(data.url, "Quoting")} {data.author_name} ({link})"
                f"</b></p>"
            )
        # Markdown
        return (
            f"> > {await self._get_link(data.url, "**Quoting**", False)} "
            f"{data.author_name} **({link})**  \n> >  \n"
        )

    async def get_interactions(self, data: Post, is_html: bool = True) -> str:
        """
        Get message part with number of interactions with the post
        :param data: Post data
        :param is_html: True for HTML, False for Markdown
        :return: formatted string with number of interactions with the post
        """
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
            # HTML
            if is_html:
                return f"<p><b>{' '.join(text)}</b></p>"
            # Markdown
            return f"> **{' '.join(text)}**  \n>  \n"
        return ""

    async def get_external_link(self, data: Link, is_html: bool = True) -> str:
        """
        Get message part with data from external link
        :param data: Link data
        :param is_html: True for HTML, False for Markdown
        :return: formatted string with external link and its description
        """
        if not data:
            return ""

        text = ""
        link = await self._get_link(data.url, data.title, is_html)
        if is_html:
            # HTML
            text += f"<blockquote><p><b>{link}</b></p>"
            if data.description:
                text += f"<p>{data.description}</p>"
            text += "</blockquote>"
        else:
            # Markdown
            text += f"> > **{link}**"
            if data.description:
                text += f"  \n> > {data.description}"
            text += "  \n>  \n"
        return text

    async def get_community_note(self, note: str, is_html: bool = True) -> str:
        """
        Get message part with community note
        :param note: content of a community note
        :param is_html: True for HTML, False for Markdown
        :return: formatted string with community note
        """
        if not note:
            return ""
        # HTML
        if is_html:
            return (
                "<blockquote>"
                "<p><b>Community Note:</b></p>"
                f"<p>{note.replace('\n', '<br>')}</p>"
                "</blockquote>"
            )
        # Markdown
        return (
            f"> > **Community Note:**  \n"
            f"> > {note.replace('\n', '  \n> > ')}  \n>  \n"
        )

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
            date = strftime('%Y-%m-%d %H:%M', localtime(post_date))
            date_html = f"<b> • {date}</b>"
            date_md = f" **• {date}**"
        # HTML
        if is_html:
            return f"<p><b>{name}</b>{date_html}</p>"
        # Markdown
        return f"> **{name}**{date_md}"

    async def tw_replace_urls(self, data: Post) -> None:
        """
        If appropriate config values are set, replaces original URL with Nitter equivalents
        :param data: Preview object with data from API
        :return:
        """
        if data.qtype != "twitter" or not self.utils.config["nitter_redirect"]:
            return

        if data.author_url:
            data.author_url = data.author_url.replace("x.com", self.utils.config["nitter_url"])
        if data.url:
            data.url = data.url.replace("x.com", self.utils.config["nitter_url"])

        if len(data.facets) > 0:
            for facet in data.facets:
                facet.url = facet.url.replace(
                    "https://x.com",
                    f"https://{self.utils.config["nitter_url"]}"
                )

        if data.quote:
            await self.tw_replace_urls(data.quote)

    async def _get_image(
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
        #HTML
        if is_html:
            return f"<img src=\"{src}\" alt=\"{alt}\" {width}{height}/>"
        # Markdown
        return f"![{alt}]({src})"

    async def _get_link(self, url: str, text: str, is_html: bool = True) -> str:
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

    async def _replace_facets(
            self,
            text: str,
            facets: list[Facet],
            qtype: str,
            is_html: bool = True
    ) -> str:
        """
        Replace mentions, tags, URLs in text with appropriate links
        :param text: raw text of the message
        :param facets: list of elements sorted by byte_start with data about replacements
        :param is_html: True for HTML, False for Markdown
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
