from asyncio import AbstractEventLoop
from typing import Any

from ..resources.datastructures import Post, Media, Link, Facet
from ..resources.utils import Utilities


class Bsky:
    def __init__(self, loop: AbstractEventLoop, utils: Utilities, player: str):
        self.loop = loop
        self.utils = utils
        self.player = player

    async def parse_preview(self, preview_raw: Any) -> Post:
        """
        Parse JSON data from Bsky API
        :param preview_raw: JSON data
        :return: Preview object
        """
        error = preview_raw.get("error")
        if error is not None:
            raise ValueError("Bad response")

        preview_raw = preview_raw["thread"]["post"]

        # Multimedia and quotes
        media = preview_raw.get("embed")
        photos: list[Media] = []
        videos: list[Media] = []
        link: Link = None
        quote: Post = None
        if media is not None:
            videos = await self._parse_videos(media)
            photos = await self._parse_images(media)
            link = await self._parse_external(media)
            quote = await self.parse_quote(media)

        return Post(
            text=preview_raw["record"]["text"],
            url=None,
            markdown=None,
            replies=await self.utils.parse_interaction(preview_raw["replyCount"]),
            reposts=await self.utils.parse_interaction(preview_raw["repostCount"]),
            likes=await self.utils.parse_interaction(preview_raw["likeCount"]),
            views=None,
            community_note=None,
            author_name=preview_raw["author"]["displayName"],
            author_screen_name=preview_raw["author"]["handle"],
            author_url="https://bsky.app/profile/" + preview_raw["author"]["handle"],
            post_date=await self.utils.parse_date(preview_raw["record"]["createdAt"]),
            photos=photos,
            videos=videos,
            facets=await self._parse_facets(preview_raw["record"]),
            poll=None,
            link=link,
            quote=quote,
            translation=None,
            translation_lang=None,
            qtype="bsky"
        )

    async def _parse_images(self, media: Any) -> list[Media]:
        photos: list[Media] = []
        if "app.bsky.embed.images" in media["$type"]:
            for elem in media["images"]:
                photo = Media(
                    width=elem["aspectRatio"]["width"],
                    height=elem["aspectRatio"]["height"],
                    url=elem["fullsize"],
                    thumbnail_url=elem["thumb"],
                    filetype="p"
                )
                photos.append(photo)
        if "app.bsky.embed.recordWithMedia" in media["$type"]:
            photos += await self._parse_images(media["media"])
        return photos

    async def _parse_videos(self, media: Any) -> list[Media]:
        videos: list[Media] = []
        if "app.bsky.embed.video" in media["$type"]:
            video = Media(
                width=media["aspectRatio"]["width"],
                height=media["aspectRatio"]["height"],
                url=self.player + media["playlist"],
                thumbnail_url=media["thumbnail"],
                filetype="v"
            )
            videos.append(video)
        if "app.bsky.embed.recordWithMedia" in media["$type"]:
            videos += await self._parse_videos(media["media"])
        return videos

    async def parse_quote(self, media: Any) -> Post | None:
        if "app.bsky.embed.record" in media["$type"]:
            if "app.bsky.embed.recordWithMedia" in media["$type"]:
                media = media["record"]
            photos: list[Media] = []
            videos: list[Media] = []
            link: Link = None
            media_rec = media["record"].get("embeds")
            if media_rec is not None:
                for elem in media_rec:
                    photos = await self._parse_images(elem)
                    videos = await self._parse_videos(elem)
                    link = await self._parse_external(elem)

            return Post(
                text=media["record"]["value"]["text"],
                url=(
                    f"https://bsky.app/profile/{media["record"]["author"]["handle"]}/"
                    f"post/{media["record"]["uri"].split("/")[-1]}"
                ),
                markdown=None,
                replies=None,
                reposts=None,
                likes=None,
                views=None,
                community_note=None,
                author_name=media["record"]["author"]["displayName"],
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
                qtype="bsky"
            )
        return None

    async def _parse_external(self, media: Any) -> Link | None:
        if "app.bsky.embed.external" in media["$type"]:
            return Link(
                title=media["external"]["title"],
                description=media["external"]["description"],
                url=media["external"]["uri"]
            )
        return None

    async def _parse_facets(self, data: Any) -> list[Facet]:
        # List of elements to substitute for in the raw text message
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
