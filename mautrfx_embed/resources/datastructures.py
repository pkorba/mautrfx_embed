from dataclasses import dataclass
from typing import Self


@dataclass
class Media:
    width: int
    height: int
    url: str
    thumbnail_url: str
    filetype: str


@dataclass
class Facet:
    text: str
    url: str
    byte_start: int
    byte_end: int


@dataclass
class Link:
    title: str
    description: str
    url: str


@dataclass
class Choice:
    label: str
    votes_count: int
    percentage: float


@dataclass
class Poll:
    ends_at: int
    status: str
    total_voters: int
    choices: list[Choice]


@dataclass
class BlogPost:
    text: str
    url: str
    text_md: str
    replies: str
    reposts: str
    likes: str
    views: str
    quotes: str
    community_note: str
    author_name: str
    author_name_md: str
    author_screen_name: str
    author_url: str
    post_date: int
    photos: list[Media]
    videos: list[Media]
    facets: list[Facet]
    poll: Poll
    link: Link
    quote: Self
    translation: str
    translation_lang: str
    qtype: str
    name: str
    sensitive: bool
    spoiler_text: str


@dataclass
class ForumPost:
    text: str
    text_md: str
    flair: str
    sub: str
    sub_url: str
    title: str
    score: str
    upvote_ratio: int
    upvotes: str
    downvotes: str
    post_date: int
    nsfw: bool
    spoiler: bool
    author: str
    author_url: str
    url: str
    comments: int
    photos: list[Media]
    videos: list[Media]
    qtype: str
    name: str
    is_link: bool
    is_comment: bool
