from .sharedfmt import SharedFmt
from ..resources.datastructures import ForumPost
from ..resources.utils import Utilities


class Forum:
    def __init__(self, utils: Utilities, fmt: SharedFmt):
        self.utils = utils
        self.fmt = fmt

    async def get_title(self, post: ForumPost, is_html: bool = True) -> str:
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
        if not data.text or data.spoiler:
            return ""
        if is_html:
            if len(data.text) > self.utils.config["forum_max_length"]:
                return f"<details><summary><b>Post content:</b> </summary><br>{data.text}</details>"
            return data.text
        return f"> {data.text_md.replace("\n", "\n> ")}  \n>  \n"

    async def get_interactions(self, data: ForumPost, is_html: bool = True) -> str:
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
