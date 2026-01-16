from typing import Any

from ..resources.datastructures import Post, Media, Facet, Poll, Choice
from ..resources.utils import Utilities


class Twitter:
    def __init__(self, utils: Utilities):
        self.utils = utils

    async def parse_preview(self, preview_raw: Any) -> Post:
        """
        Parse JSON data from FxTwitter API
        :param preview_raw: JSON data
        :return: Preview object
        """
        if not preview_raw["code"] == 200:
            raise ValueError("Bad response")

        preview_raw = preview_raw["tweet"]
        videos, photos = await self._parse_media(preview_raw)
        translation = preview_raw.get("translation")
        post = Post(
            # Remove non-functional links added at the end of some tweets with media attached
            text=preview_raw["raw_text"]["text"],
            url=None,
            markdown=None,
            replies=await self.utils.parse_interaction(preview_raw["replies"]),
            reposts=await self.utils.parse_interaction(preview_raw["retweets"]),
            likes=await self.utils.parse_interaction(preview_raw["likes"]),
            views=await self.utils.parse_interaction(preview_raw["views"]),
            community_note=await self._parse_community_note(preview_raw),
            author_name=preview_raw["author"]["name"],
            author_screen_name=preview_raw["author"]["screen_name"],
            author_url=preview_raw["author"]["url"],
            post_date=preview_raw["created_timestamp"],
            photos=photos,
            videos=videos,
            facets=await self._parse_facets(preview_raw),
            poll=await self._parse_poll(preview_raw),
            link=None,
            quote=await self.parse_quote(preview_raw),
            translation=translation["text"] if translation is not None else None,
            translation_lang=translation.get("source_lang_en") if translation is not None else None,
            qtype="twitter",
            name="✖️ X (Twitter)"
        )
        return post

    async def parse_quote(self, data: Any) -> Post | None:
        quote = data.get("quote")
        if not quote:
            return None
        q_videos, q_photos = await self._parse_media(quote)
        return Post(
                text=quote["raw_text"]["text"],
                url=quote["url"],
                markdown=None,
                replies=None,
                reposts=None,
                likes=None,
                views=None,
                community_note=None,
                author_name=quote["author"]["name"],
                author_url=quote["author"]["url"],
                author_screen_name=quote["author"]["screen_name"],
                post_date=None,
                photos=q_photos,
                videos=q_videos,
                facets=await self._parse_facets(quote),
                poll=await self._parse_poll(quote),
                link=None,
                quote=None,
                translation=None,
                translation_lang=None,
                qtype="twitter",
                name="✖️ X (Twitter)"
            )

    async def _parse_community_note(self, data: Any) -> str:
        # Community Note
        community_note = data.get("community_note")
        if community_note is not None:
            return community_note["text"]
        return ""

    async def _parse_media(self, data: Any) -> tuple[list, list]:
        # Multimedia
        media = data.get("media")
        photos: list[Media] = []
        videos: list[Media] = []
        if media is not None:
            for elem in media["all"]:
                if elem["type"] in ["video", "gif"]:
                    video = Media(
                        width=elem["width"],
                        height=elem["height"],
                        url=elem["url"],
                        thumbnail_url=elem["thumbnail_url"],
                        filetype="v"
                    )
                    videos.append(video)
                elif elem["type"] == "photo":
                    photo = Media(
                        width=elem["width"],
                        height=elem["height"],
                        url=elem["url"],
                        thumbnail_url=None,
                        filetype="p"
                    )
                    photos.append(photo)
        return videos, photos

    async def _parse_poll(self, data: Any) -> Poll:
        # Poll
        poll = None
        poll_raw = data.get("poll")
        if poll_raw is not None:
            choices: list[Choice] = []
            for option in poll_raw["choices"]:
                choice = Choice(
                    label=option["label"],
                    votes_count=option["count"],
                    percentage=option["percentage"],
                )
                choices.append(choice)
            poll = Poll(
                ends_at=poll_raw["ends_at"],
                status=poll_raw["time_left_en"],
                total_voters=poll_raw["total_votes"],
                choices=choices
            )
        return poll

    async def _parse_facets(self, data: Any) -> list[Facet]:
        # List of elements to substitute for in the raw text message
        facets: list[Facet] = []
        facets_raw = data["raw_text"].get("facets")
        if facets_raw is not None:
            for fac in facets_raw:
                facet = None
                b_start = fac["indices"][0]
                b_end = fac["indices"][1]
                if fac["type"] in "url":
                    facet = Facet(
                        text=fac["display"],
                        url=fac["replacement"],
                        byte_start=b_start,
                        byte_end=b_end,
                    )
                elif fac["type"] == "mention":
                    facet = Facet(
                        text="@" + fac["original"],
                        url="https://x.com/" + fac["original"],
                        byte_start=b_start,
                        byte_end=b_end,
                    )
                elif fac["type"] == "hashtag":
                    facet = Facet(
                        text="#" + fac["original"],
                        url="https://x.com/hashtag/" + fac["original"],
                        byte_start=b_start,
                        byte_end=b_end,
                    )
                # Ignore 'media' type because API returns wrong indices in them
                if facet:
                    facets.append(facet)
            facets.sort(key=lambda f: f.byte_start)
        return facets
