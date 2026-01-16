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
class Post:
    text: str
    url: str
    markdown: str
    replies: str
    reposts: str
    likes: str
    views: str
    community_note: str
    author_name: str
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


twitter_domains = [
    "x.com",
    "twitter.com",
    "fixupx.com",
    "xfixup.com",
    "fxtwitter.com",
    "twittpr.com",
    "fixvx.com",
    "vxtwitter.com",
    "fixvtwitter.com"
    "stupidpenisx.com",
    "girlcockx.com",
    "nitter.net",
    "xcancel.com",
    "nitter.poast.org",
    "nitter.privacyredirect.com",
    "lightbrd.com",
    "nitter.space",
    "nitter.tierkoetter.com",
    "nuku.trabun.org",
    "nitter.catsarch.com"
]

bsky_domains = [
    "bsky.app/profile",
    "fxbsky.app/profile",
    "skyview.social/?url=https://bsky.app/profile/",
    "skyview.social/?url=bsky.app/profile/"
]

instagram_domains = [
    "www.instagram.com/reel",
    "instagram.com/reel",
    "www.kkinstagram.com/reel",
    "kkinstagram.com/reel",
    "www.uuinstagram.com/reel",
    "uuinstagram.com/reel"
]
