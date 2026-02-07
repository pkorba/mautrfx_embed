from asyncio import AbstractEventLoop
from typing import Any

from ..resources.datastructures import BlogPost, Media, Link, Facet
from ..resources.utils import Utilities


class Bsky:
    def __init__(self, loop: AbstractEventLoop, utils: Utilities):
        self.loop = loop
        self.utils = utils

    async def parse_preview(self, data: Any) -> BlogPost:
        """
        Parse JSON data from Bsky API
        :param data: JSON data
        :return: BlogPost object
        """
        error = data.get("error")
        if error is not None:
            raise ValueError("Bad response")

        data = data["thread"]["post"]

        # Multimedia and quotes
        media = data.get("embed")
        photos: list[Media] = []
        videos: list[Media] = []
        link: Link = None
        quote: BlogPost = None
        if media is not None:
            videos = await self._parse_videos(media)
            photos = await self._parse_photos(media)
            link = await self._parse_external(media)
            quote = await self.parse_quote(media)

        return BlogPost(
            text=data["record"]["text"],
            url=None,
            text_md=None,
            replies=await self.utils.parse_interaction(data["replyCount"]),
            reposts=await self.utils.parse_interaction(data["repostCount"]),
            likes=await self.utils.parse_interaction(data["likeCount"]),
            views=None,
            quotes=None,
            community_note=None,
            author_name=data["author"]["displayName"],
            author_name_md=data["author"]["displayName"],
            author_screen_name=data["author"]["handle"],
            author_url="https://bsky.app/profile/" + data["author"]["handle"],
            post_date=await self.utils.parse_date(data["record"]["createdAt"]),
            photos=photos,
            videos=videos,
            facets=await self._parse_facets(data["record"]),
            poll=None,
            link=link,
            quote=quote,
            translation=None,
            translation_lang=None,
            qtype="bsky",
            name="🦋 Bluesky",
            sensitive=len(data["labels"]) > 0,
            spoiler_text=None
        )

    async def _parse_photos(self, media: Any) -> list[Media]:
        """
        Extract data about image attachments into Media objects
        :param media: JSON with data about image attachments
        :return: list of images
        """
        photos: list[Media] = []
        if "app.bsky.embed.images" in media["$type"]:
            for elem in media["images"]:
                aspect_ratio = elem.get("aspectRatio")
                photo = Media(
                    width=aspect_ratio["width"] if aspect_ratio is not None else 0,
                    height=aspect_ratio["height"] if aspect_ratio is not None else 0,
                    url=elem["fullsize"],
                    thumbnail_url=elem["thumb"],
                    filetype="p"
                )
                photos.append(photo)
        # Posts with quotes have different structure
        if "app.bsky.embed.recordWithMedia" in media["$type"]:
            photos += await self._parse_photos(media["media"])
        return photos

    async def _parse_videos(self, media: Any) -> list[Media]:
        """
        Extract data about video attachments into Media objects
        :param media: JSON with data about video attachments
        :return: list of videos
        """
        videos: list[Media] = []
        if "app.bsky.embed.video" in media["$type"]:
            aspect_ratio = media.get("aspectRatio")
            video = Media(
                width=aspect_ratio["width"] if aspect_ratio is not None else 0,
                height=aspect_ratio["height"] if aspect_ratio is not None else 0,
                url=self.utils.config["player"] + media["playlist"],
                thumbnail_url=media["thumbnail"],
                filetype="v"
            )
            videos.append(video)
        # Posts with quotes have different structure
        if "app.bsky.embed.recordWithMedia" in media["$type"]:
            videos += await self._parse_videos(media["media"])
        return videos

    async def parse_quote(self, media: Any) -> BlogPost | None:
        """
        Parse JSON data about quote post from Bsky API
        :param media: JSON data
        :return: BlogPost object
        """
        if "app.bsky.embed.record" in media["$type"]:
            if "app.bsky.embed.recordWithMedia" in media["$type"]:
                media = media["record"]
            photos: list[Media] = []
            videos: list[Media] = []
            link: Link = None
            media_rec = media["record"].get("embeds")
            if media_rec is not None:
                for elem in media_rec:
                    photos = await self._parse_photos(elem)
                    videos = await self._parse_videos(elem)
                    link = await self._parse_external(elem)

            return BlogPost(
                text=media["record"]["value"]["text"],
                url=(
                    f"https://bsky.app/profile/{media["record"]["author"]["handle"]}/"
                    f"post/{media["record"]["uri"].split("/")[-1]}"
                ),
                text_md=None,
                replies=None,
                reposts=None,
                likes=None,
                views=None,
                quotes=None,
                community_note=None,
                author_name=media["record"]["author"]["displayName"],
                author_name_md=media["record"]["author"]["displayName"],
                author_screen_name=media["record"]["author"]["handle"],
                author_url=f"https://bsky.app/profile/{media["record"]["author"]["handle"]}",
                post_date=None,
                photos=photos,
                videos=videos,
                facets=await self._parse_facets(media["record"]["value"]),
                poll=None,
                link=link,
                quote=None,
                translation=None,
                translation_lang=None,
                qtype="bsky",
                name="🦋 Bluesky",
                sensitive=len(media["record"]["labels"]) > 0,
                spoiler_text=None
            )
        return None

    async def _parse_external(self, media: Any) -> Link | None:
        """
        Extract data about external links into Link object
        :param media: external link JSON data
        :return: Link object
        """
        if "app.bsky.embed.external" in media["$type"]:
            return Link(
                title=media["external"]["title"],
                description=media["external"]["description"],
                url=media["external"]["uri"]
            )
        return None

    async def _parse_facets(self, data: Any) -> list[Facet]:
        """
        Extract data about facets into a list of Facet objects
        :param data: JSON facet data
        :return: list of Facets
        """
        facets: list[Facet] = []
        facets_raw = data.get("facets")
        if facets_raw is not None:
            for fac in facets_raw:
                facet = None
                b_start = fac["index"]["byteStart"]
                b_end = fac["index"]["byteEnd"]
                text = data["text"].encode('utf-8')
                if fac["features"][0]["$type"] == "app.bsky.richtext.facet#mention":
                    text = text[b_start:b_end].decode('utf-8')
                    facet = Facet(
                        text=text,
                        url=f"https://bsky.app/profile/{fac["features"][0]["did"]}",
                        byte_start=b_start,
                        byte_end=b_end
                    )
                elif fac["features"][0]["$type"] == "app.bsky.richtext.facet#tag":
                    tag = fac["features"][0]["tag"]
                    facet = Facet(
                        text="#" + tag,
                        url=f"https://bsky.app/hashtag/{tag}",
                        byte_start=b_start,
                        byte_end=b_end
                    )
                elif fac["features"][0]["$type"] == "app.bsky.richtext.facet#link":
                    link_text = text[b_start:b_end].decode('utf-8')
                    facet = Facet(
                        text=link_text,
                        url=fac["features"][0]["uri"],
                        byte_start=b_start,
                        byte_end=b_end
                    )
                if facet:
                    facets.append(facet)
                facets.sort(key=lambda f: f.byte_start)
        return facets
