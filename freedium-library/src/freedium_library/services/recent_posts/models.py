from __future__ import annotations

from pydantic import BaseModel, Field


class RecentPost(BaseModel):
    """A post that was recently rendered through Freedium.

    Surfaced on the home-page feed so visitors see what the community
    has been unlocking. Fields mirror the subset of PostMetadata that
    a feed card needs.
    """

    post_id: str
    title: str
    subtitle: str = ""
    creator_name: str = ""
    creator_avatar_id: str | None = None
    collection_name: str | None = None
    reading_time: int = 0
    first_published_at: int | None = None
    preview_image_id: str = ""
    medium_url: str = ""
    tags: list[str] = Field(default_factory=list)
    unlocked_at: int = 0
    """Unix-ms timestamp of when this post was unlocked through Freedium."""


class RecentPostsResponse(BaseModel):
    """Response body for GET /articles/recent."""

    posts: list[RecentPost]
