from .sharedfmt import SharedFmt
from ..resources.datastructures import ForumPost
from ..resources.utils import Utilities


class Forum:
    def __init__(self, utils: Utilities, fmt: SharedFmt):
        self.utils = utils
        self.fmt = fmt

    async def get_title(self, post: ForumPost, is_html: bool = True) -> str:
        """
        Get title of the post along with flair, information about user who posted it, and subreddit
        :param post: ForumPost object
        :param is_html: True for HTML, False for Markdown
        :return: Title of the post
        """
        title = await self.fmt.get_link(post.url, post.title, is_html)
        user = ""
        sub = ""
        if post.author:
            user = await self.fmt.get_link(
                post.author_url,
                f"u/{post.author}",
                is_html
            )
        if post.sub:
            sub = await self.fmt.get_link(
                post.sub_url,
                post.sub,
                is_html
            )
        subtext = f"{user} on {sub}" if user and sub else ""
        # HTML
        if is_html:
            flair = "<code>SPOILER</code> " if post.spoiler else ""
            flair += f"<code>{post.flair.title()}</code> " if post.flair else ""
            subtext = f"<br>{subtext}" if subtext else ""
            return f"<p>{flair}<b>{title}</b>{subtext}</p>"
        # Markdown
        flair = "`SPOILER` " if post.spoiler else ""
        flair += f"`{post.flair.title()}` " if post.flair else ""
        subtext = f"  \n> {subtext}" if subtext else ""
        return f"> {flair}**{title}**{subtext}  \n>  \n"

    async def get_text(self, data: ForumPost, is_html: bool = True) -> str:
        """
        Get text content of the post. Content is wrapped in 'details' HTML element if the content
        is longer that 'forum_max_length'
        :param data: ForumPost data
        :param is_html: True for HTML, False for Markdown
        :return: Post text content
        """
        if not data.text or data.spoiler:
            return ""
        if is_html:
            if len(data.text) > self.utils.config["forum_max_length"]:
                return f"<details><summary><b>Post content:</b> </summary><br>{data.text}</details>"
            return data.text
        return f"> {data.text_md.replace("\n", "\n> ")}  \n>  \n"

    async def get_interactions(self, data: ForumPost, is_html: bool = True) -> str:
        """
        Get number of user interactions with the post/comment
        :param data: ForumPost object
        :param is_html: True for HTML, False for Markdown
        :return: Number of user interactions with the post/comment
        """
        text = []
        if data.qtype == "reddit":
            if data.score:
                text.append(f"⬆️ {data.score}")
            if data.upvote_ratio:
                text.append(f"({data.upvote_ratio}%)")
            if data.comments:
                text.append(f"💬 {data.comments}")
        else:
            if data.upvotes:
                text.append(f"⬆️ {data.upvotes}")
            if data.downvotes:
                text.append(f"⬇️ {data.downvotes}")
            if data.comments:
                text.append(f"💬 {data.comments}")

        if text:
            # HTML
            if is_html:
                return f"<p><b>{" ".join(text)}</b></p>"
            # Markdown
            return f"> **{" ".join(text)}**  \n>  \n"
        return ""
