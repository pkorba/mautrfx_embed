import re

from .sharedfmt import SharedFmt
from ..resources.datastructures import BlogPost, Facet, Link
from ..resources.utils import Utilities


class Blog:
    def __init__(self, utils: Utilities, fmt: SharedFmt):
        self.utils = utils
        self.fmt = fmt

    async def get_author(self, data: BlogPost, is_html: bool = True) -> str:
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
            return f"<p>{await self.fmt.get_link(
                data.author_url,
                f"<b>{author_name} (@{data.author_screen_name})</b>"
            )}</p>"
        # Markdown
        return f"> {await self.fmt.get_link(
            data.author_url,
            f"**{author_name}** **(@{data.author_screen_name})**",
            False
        )}   \n>  \n"

    async def get_text(self, data: BlogPost, is_html: bool = True) -> str:
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

    async def get_translation(self, data: BlogPost, is_html: bool = True) -> str:
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

    async def get_poll(self, data: BlogPost, is_html: bool = True) -> str:
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

    async def get_quote(self, data: BlogPost, is_html: bool = True) -> str:
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
            text += await self.fmt.get_media_previews(data.photos, data.videos, data.sensitive)
        res = await self.fmt.get_media_list(data.videos, data.sensitive, is_html)
        text += res if is_html else res.replace("> ", "> > ")
        res = await self.fmt.get_media_list(data.photos, data.sensitive, is_html)
        text += res if is_html else res.replace("> ", "> > ")
        res = await self.get_external_link(data.link, is_html)
        text += res if is_html else res.replace("> > ", "> > > ")
        # HTML
        if is_html:
            return f"<blockquote>{text}</blockquote>"
        # Markdown
        return text

    async def get_quote_author(self, data: BlogPost, is_html: bool = True) -> str:
        """
        Get message part with a link to quoted post and information about its author
        :param data: Quoted post data
        :param is_html: True for HTML, False for Markdown
        :return: formatted string with quoted post link and author name
        """
        if not data.author_screen_name:
            return ""

        link = await self.fmt.get_link(data.author_url, f"@{data.author_screen_name}", is_html)
        # HTML
        if is_html:
            return (
                f"<p><b>"
                f"{await self.fmt.get_link(data.url, "Quoting")} {data.author_name} ({link})"
                f"</b></p>"
            )
        # Markdown
        return (
            f"> > {await self.fmt.get_link(data.url, "**Quoting**", False)} "
            f"{data.author_name} **({link})**  \n> >  \n"
        )

    async def get_interactions(self, data: BlogPost, is_html: bool = True) -> str:
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
        if data.quotes:
            text.append(f"❞ {data.quotes}")
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
        link = await self.fmt.get_link(data.url, data.title, is_html)
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

    async def tw_replace_urls(self, data: BlogPost) -> None:
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
            link = await self.fmt.get_link(facet.url, facet.text, is_html)
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
