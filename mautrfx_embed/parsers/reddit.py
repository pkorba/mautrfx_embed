import html
import mimetypes
from typing import Any

from ..resources.datastructures import ForumPost, Media
from ..resources.utils import Utilities


class Reddit:
    def __init__(self, utils: Utilities):
        self.utils = utils

    async def parse_preview(self, data: Any) -> ForumPost:
        """
        Parse JSON data from Reddit API
        :param data: JSON data
        :return: ForumPost object
        """
        if not data["data"]["children"]:
            raise ValueError("Bad response")

        # Comment permalink
        if data["data"]["children"][0]["kind"] == "t1":
            data = data["data"]["children"][0]["data"]

            return ForumPost(
                text=await self._parse_text(data.get("body_html", "")),
                text_md=await self._parse_markdown(data["body"]),
                flair=None,
                sub=data["subreddit_name_prefixed"],
                sub_url=f"https://www.reddit.com/{data["subreddit_name_prefixed"]}",
                title="Comment permalink",
                score=await self.utils.parse_interaction(data["score"]),
                upvote_ratio=0,
                upvotes=await self.utils.parse_interaction(data["ups"]),
                downvotes=await self.utils.parse_interaction(data["downs"]),
                post_date=int(data["created"]),
                nsfw=False,
                spoiler=False,
                author=data["author"],
                author_url=f"https://www.reddit.com/u/{data["author"]}",
                url=f"https://www.reddit.com{data["permalink"]}",
                comments=0,
                photos=[],
                videos=[],
                qtype="reddit",
                name="👽 Reddit",
                is_link=False,
                is_comment=True
            )

        # Post
        data = data["data"]["children"][0]["data"]
        return ForumPost(
            text=await self._parse_text(data.get("selftext_html", "")),
            text_md=await self._parse_markdown(data["selftext"]),
            flair=data["link_flair_text"],
            sub=data["subreddit_name_prefixed"],
            sub_url=f"https://www.reddit.com/{data["subreddit_name_prefixed"]}",
            title=data["title"],
            score=await self.utils.parse_interaction(data["score"]),
            upvote_ratio=int(data["upvote_ratio"] * 100),
            upvotes=await self.utils.parse_interaction(data["ups"]),
            downvotes=await self.utils.parse_interaction(data["downs"]),
            post_date=int(data["created"]),
            nsfw=data["over_18"],
            spoiler=data["spoiler"],
            author=data["author"],
            author_url=f"https://www.reddit.com/u/{data["author"]}",
            url=data["url"],
            comments=data["num_comments"],
            photos=await self._parse_photos(data),
            videos=await self._parse_videos(data),
            qtype="reddit",
            name="👽 Reddit",
            is_link=data.get("post_hint") in ("link", "rich:video"),
            is_comment=False
        )

    async def _parse_text(self, text: str) -> str:
        """
        Remove needless HTML comments from the content of Reddit post, fix spoiler tag
        :param text: HTML content of a post
        :return: HTML text
        """
        if not text:
            return ""
        # Remove comments
        text = text.replace("&lt;!-- SC_OFF --&gt;", "").replace("&lt;!-- SC_ON --&gt;", "")
        # Fix spoilers
        text = text.replace(
            "&lt;span class=\"md-spoiler-text\"&gt;",
            "&lt;span data-mx-spoiler&gt;"
        )
        return html.unescape(text)

    async def _parse_markdown(self, text: str) -> str:
        """
        Fix spoiler tag in Markdown version of the post
        :param text: Markdown content of a post
        :return: Markdown text
        """
        if not text:
            return ""
        return text.replace("&gt;!", "||").replace("!&lt;", "||")

    async def _parse_photos(self, data: Any) -> list[Media]:
        """
        Extract images from Reddit post JSON data
        :param data: post JSON data
        :return: list of images
        """
        photos: list[Media] = []
        hint = data.get("post_hint")
        if hint == "image":
            photo = await self._parse_preview(data, "thumbnail_large")
            if photo:
                photos.append(photo)
        elif hint in ("link", "rich:video"):
            photo = await self._parse_preview(data, "thumbnail_small")
            # Check if thumbnail_url exists because for this object
            # thumbnail cannot be generated based on the main URL
            if photo and photo.thumbnail_url:
                photos.append(photo)
        elif data.get("gallery_data"):
            gallery = data["gallery_data"]["items"]
            previews = data["media_metadata"]
            for item in gallery:
                image = previews[item["media_id"]]
                mime = image["m"]
                # Reddit returns incorrect mimetype for JPG images
                mime = "image/jpeg" if mime == "image/jpg" else mime
                ext = mimetypes.guess_extension(mime)
                photo = None
                # Choose the first thumbnail that fits user requirements
                # (thumbnails in the list are sorted by size from the smallest to the largest)
                for preview in image["p"]:
                    if (
                            preview["x"] > self.utils.config["thumbnail_small"]
                            or preview["y"] > self.utils.config["thumbnail_small"]
                    ):
                        photo = Media(
                            width=preview["x"],
                            height=preview["y"],
                            url=f"https://i.redd.it/{item["media_id"]}{ext}",
                            thumbnail_url=preview["u"].replace("&amp;", "&"),
                            filetype="p"
                        )
                        break
                # If all thumbnails are smaller than requested, choose the biggest one
                if not photo:
                    photo = Media(
                        width=image["p"][-1]["x"],
                        height=image["p"][-1]["y"],
                        url=f"https://i.redd.it/{item["media_id"]}{ext}",
                        thumbnail_url=image["p"][-1]["u"].replace("&amp;", "&"),
                        filetype="p"
                    )
                photos.append(photo)
        return photos

    async def _parse_preview(self, data: Any, size_type: str) -> Media | None:
        """
        Extract single preview image from Reddit post JSON data
        :param data: post JSON data
        :param size_type: 'thumbnail_large' or 'thumbnail_small'
        :return: preview image closest to choosen size
        """
        photo = None
        if not data.get("preview"):
            return None
        previews = data["preview"]["images"][0]["resolutions"]
        for preview in previews:
            if (
                    preview["width"] > self.utils.config[size_type]
                    or preview["height"] > self.utils.config[size_type]
            ):
                photo = Media(
                    width=preview["width"],
                    height=preview["height"],
                    url=data["url"],
                    thumbnail_url=preview["url"].replace("&amp;", "&"),
                    filetype="p"
                )
                break
        # If all thumbnails are smaller than requested, choose the biggest one
        if not photo:
            photo = Media(
                width=previews[-1]["width"],
                height=previews[-1]["height"],
                url=data["url"],
                thumbnail_url=previews[-1]["url"].replace("&amp;", "&"),
                filetype="p"
            )
        return photo

    async def _parse_videos(self, data: Any) -> list[Media]:
        """
        Extract video from reddit post JSON data
        :param data: post JSON data
        :return: list of videos
        """
        videos: list[Media] = []
        if not data["is_video"]:
            return videos
        video = await self._parse_preview(data, "thumbnail_large")
        if video:
            video.url = self.utils.config["player"] + data["media"]["reddit_video"]["hls_url"]
            video.filetype = "v"
        else:
            video = Media(
                width=0,
                height=0,
                url=self.utils.config["player"] + data["media"]["reddit_video"]["hls_url"],
                thumbnail_url=None,
                filetype="v"
            )
        videos.append(video)
        return videos
