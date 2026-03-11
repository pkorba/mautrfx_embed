from asyncio import AbstractEventLoop
from typing import Any

from ..resources.datastructures import ForumPost, Media
from ..resources.utils import Utilities


class Lemmy:
    def __init__(self, loop: AbstractEventLoop, utils: Utilities):
        self.loop = loop
        self.utils = utils

    async def parse_preview(self, data: Any) -> ForumPost:
        """
        Parse JSON data from Lemmy API
        :param data: JSON data
        :return: ForumPost object
        """
        if data.get("error"):
            raise ValueError("Bad response")

        # Comment
        if data.get("comment_view"):
            data = data["comment_view"]
            title, flairs = await self.utils.fedi_forum_parse_title(data["post"]["name"])
            return ForumPost(
                text=await self.loop.run_in_executor(
                    None,
                    self.utils.fedi_forum_parse_text,
                    data["comment"].get("content")
                ),
                text_md=await self.loop.run_in_executor(
                    None,
                    self.utils.fedi_forum_parse_markdown,
                    data["comment"].get("content")
                ),
                flairs=[fl for fl in flairs if fl.lower() != "spoiler"],
                sub=f"c/{data["community"]["name"]}",
                sub_url=data["community"]["actor_id"],
                title=title,
                score=None,
                upvote_ratio=0,
                upvotes=await self.utils.parse_interaction(data["counts"]["upvotes"]),
                downvotes=await self.utils.parse_interaction(data["counts"]["downvotes"]),
                post_date=await self.utils.parse_date(data["comment"]["published"]),
                nsfw=data["post"]["nsfw"],
                spoiler="spoiler" in (fl.lower() for fl in flairs),
                skip_content=await self.utils.config_item_contains(
                    flairs,
                    "fedi_excluded_comment_flairs"
                ),
                author=await self._parse_author(data["creator"], data["community"]),
                author_url=data["creator"]["actor_id"],
                url=f"{data["comment"]["ap_id"]}?scrollToComments=true",
                comments=data["counts"]["child_count"],
                photos=[],
                videos=[],
                poll=None,
                qtype="lemmy",
                name=f"🐹 {self.utils.INSTANCE_NAME.sub(
                    r"\g<base_url>",
                    data["community"]["actor_id"]
                )}",
                is_link="text/html" in data["post"].get("url_content_type", ""),
                is_comment=True
            )

        # Post
        data = data["post_view"]
        title, flairs = await self.utils.fedi_forum_parse_title(data["post"]["name"])
        return ForumPost(
            text=await self.loop.run_in_executor(
                None,
                self.utils.fedi_forum_parse_text,
                data["post"].get("body")
            ),
            text_md=await self.loop.run_in_executor(
                None,
                self.utils.fedi_forum_parse_markdown,
                data["post"].get("body")
            ),
            flairs=[fl for fl in flairs if fl.lower() != "spoiler"],
            sub=f"c/{data["community"]["name"]}",
            sub_url=data["community"]["actor_id"],
            title=title,
            score=None,
            upvote_ratio=0,
            upvotes=await self.utils.parse_interaction(data["counts"]["upvotes"]),
            downvotes=await self.utils.parse_interaction(data["counts"]["downvotes"]),
            post_date=await self.utils.parse_date(data["post"]["published"]),
            nsfw=data["post"]["nsfw"],
            spoiler="spoiler" in (fl.lower() for fl in flairs),
            skip_content=await self.utils.config_item_contains(flairs, "fedi_excluded_flairs"),
            author=await self._parse_author(data["creator"], data["community"]),
            author_url=data["creator"]["actor_id"],
            url=(
                data["post"]["url"] if data["post"].get("url") is not None
                else data["post"]["ap_id"]
            ),
            comments=data["counts"]["comments"],
            photos=await self._parse_photos(data),
            videos=await self._parse_videos(data),
            poll=None,
            qtype="lemmy",
            name=f"🐹 {self.utils.INSTANCE_NAME.sub(
                r"\g<base_url>",
                data["community"]["actor_id"]
            )}",
            is_link="text/html" in data["post"].get("url_content_type", ""),
            is_comment=False
        )

    async def _parse_author(self, creator: Any, community: Any) -> str:
        """
        Get post author's name
        :param creator: author section JSON data
        :param community: community section JSON data
        :return: author's username link
        """
        community_url = self.utils.INSTANCE_NAME.sub(r"\g<base_url>", community["actor_id"])
        creator_url = self.utils.INSTANCE_NAME.sub(r"\g<base_url>", creator["actor_id"])
        base_url = "" if community_url == creator_url else f"@{creator_url}"
        return f"{creator["name"]}{base_url}"


    async def _parse_photos(self, data: Any) -> list[Media]:
        """
        Extract images from JSON post data
        :param data: JSON post data
        :return: list of images
        """
        photos: list[Media] = []
        details = data.get("image_details")
        if details:
            photo = Media(
                width=details["width"],
                height=details["height"],
                url=details["link"],
                thumbnail_url=details["link"],
                filetype="p"
            )
            photos.append(photo)
        else:
            thumbnail = await self._parse_thumbnail(data)
            if thumbnail:
                photos.append(thumbnail)
        return photos

    async def _parse_thumbnail(self, data: Any) -> Media | None:
        """
        Extract thumbnail from JSON post data
        :param data: JSON post data
        :return: thumbnail or None
        """
        photo = None
        thumbnail_url = data["post"].get("thumbnail_url")
        if thumbnail_url:
            # Use main url because thumbnail will serve as link
            # and this will be the link's destination
            photo = Media(
                width=0,
                height=0,
                url=data["post"]["url"],
                thumbnail_url=thumbnail_url,
                filetype="p"
            )
        return photo

    async def _parse_videos(self, data: Any) -> list[Media]:
        """
        Extract video from JSON post data
        :param data: JSON post data
        :return: video
        """
        videos: list[Media] = []
        is_video = data["post"].get("url_content_type", "") in (
            "video/x-msvideo",
            "video/mp4",
            "video/mpeg",
            "video/ogg",
            "video/webm",
            "video/mp2t",
            "video/3gpp",
            "video/3gpp2",
            "video/matroska"
        )
        if is_video:
            video = Media(
                width=0,
                height=0,
                url=data["post"]["url"],
                thumbnail_url=data["post"].get("thumbnail_url"),
                filetype="v"
            )
            videos.append(video)
        return videos
