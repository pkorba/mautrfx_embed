from asyncio import AbstractEventLoop
from typing import Any

from ..resources.datastructures import ForumPost, Media
from ..resources.utils import Utilities


class Piefed:
    def __init__(self, loop: AbstractEventLoop, utils: Utilities):
        self.loop = loop
        self.utils = utils

    async def parse_preview(self, data: Any) -> ForumPost:
        """
        Parse JSON data from Piefed API
        :param data: JSON data
        :return: ForumPost object
        """
        if data.get("code"):
            raise ValueError("Bad response")

        # Comment
        if data.get("comment_view"):
            data = data["comment_view"]
            title, lemmy_flairs = await self.utils.fedi_forum_parse_title(data["post"]["title"])
            # Flair logic explained below, in the Post branch
            flairs = await self._get_flairs(data)
            flairs = flairs if flairs else lemmy_flairs
            return ForumPost(
                text=await self.loop.run_in_executor(
                    None,
                    self.utils.fedi_forum_parse_text,
                    data["comment"].get("body")
                ),
                text_md=await self.loop.run_in_executor(
                    None,
                    self.utils.fedi_forum_parse_markdown,
                    data["comment"].get("body")
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
                # scrollToComments - Piefed doesn't need it, but useful if it's a Lemmy link in here
                url=f"{data["comment"]["ap_id"]}?scrollToComments=true",
                comments=data["counts"]["child_count"],
                photos=[],
                videos=[],
                qtype="piefed",
                name=f"🥧 {self.utils.INSTANCE_NAME.sub(
                    r"\g<base_url>",
                    data["community"]["actor_id"]
                )}",
                is_link=data["post"].get("post_type") == "Link",
                is_comment=True
            )

        # Post
        data = data["post_view"]
        title, lemmy_flairs = await self.utils.fedi_forum_parse_title(data["post"]["title"])
        # Piefed has its own implementation of flairs but can display Lemmy posts too
        # and those can have flairs as a part of the title. If Piefed-style flairs
        # exist, we use these. Otherwise, we check for flairs within the title
        flairs = await self._get_flairs(data)
        flairs = flairs if flairs else lemmy_flairs
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
            qtype="piefed",
            name=f"🥧 {self.utils.INSTANCE_NAME.sub(
                r"\g<base_url>",
                data["community"]["actor_id"]
            )}",
            is_link=data["post"].get("post_type") == "Link",
            is_comment=False
        )

    async def _get_flairs(self, data: Any) -> list[str]:
        """
        Get a list of flairs (Piefed-style)
        :param data: JSON data from API
        :return: list of flairs
        """
        flairs: list[str] = []
        if not data:
            return flairs
        flair_list = data.get("flair_list", [])
        flairs = [flair["flair_title"] for flair in flair_list]
        return flairs

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
        return f"{creator["title"]}{base_url}"

    async def _parse_photos(self, data: Any) -> list[Media]:
        """
        Extract images from JSON post data
        :param data: JSON post data
        :return: list of images
        """
        photos: list[Media] = []
        details = data["post"].get("image_details")
        if details and data["post"].get("post_type") == "Image":
            photo = Media(
                width=details["width"],
                height=details["height"],
                url=data["post"]["url"],
                thumbnail_url=data["post"]["thumbnail_url"],
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
        details = data["post"].get("image_details")
        if thumbnail_url:
            # Use main url because thumbnail will serve as link
            # and this will be the link's destination
            photo = Media(
                width=details["width"] if details else 0,
                height=details["height"] if details else 0,
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
        if data["post"].get("post_type") == "Video":
            video = Media(
                width=0,
                height=0,
                url=data["post"]["url"],
                thumbnail_url=data["post"].get("thumbnail_url"),
                filetype="v"
            )
            videos.append(video)
        return videos
