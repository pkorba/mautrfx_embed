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
class Preview:
    text: str
    replies: int
    retweets: int
    likes: int
    views: int
    community_note: str
    author_name: str
    author_screen_name: str
    author_url: str
    tweet_date: int
    mosaic: Photo
    photos: list[Photo]
    videos: list[Video]
    quote_author_name: str
    quote_author_url: str
    quote_author_screen_name: str
    quote_text: str
    quote_url: str
