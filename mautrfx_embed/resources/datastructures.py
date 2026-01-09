from dataclasses import dataclass


@dataclass
class Photo:
    width: int
    height: int
    url: str


@dataclass
class Video:
    width: int
    height: int
    url: str
    thumbnail_url: str


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
class Quote:
    quote_url: str
    quote_text: str
    quote_author_name: str
    quote_author_url: str
    quote_author_screen_name: str
    photos: list[Photo]
    videos: list[Video]
    link: Link
    poll: Poll


@dataclass
class Preview:
    text: str
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
    photos: list[Photo]
    videos: list[Video]
    facets: list[Facet]
    poll: Poll
    link: Link
    quote: Quote
    quote_markdown: str
