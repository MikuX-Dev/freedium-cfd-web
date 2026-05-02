"""Curated seed data for the recent-posts feed.

Loaded into RecentPostsService on application startup so a freshly
booted instance has something to show on the home page. As real users
unlock articles, those records bump the seed entries out of the
ring buffer naturally — no special handling needed.

Each entry mirrors the PostMetadata fields the renderer would emit.
post_id values here are real Medium post IDs (the suffix on canonical
medium.com URLs); medium_url points to the public canonical page.
"""

from __future__ import annotations

from freedium_library.services.medium.renderer import PostMetadata


def _ms(year: int, month: int, day: int) -> int:
    """Return a unix-ms timestamp for a UTC date — convenient for seed data."""
    import datetime

    return int(
        datetime.datetime(year, month, day, tzinfo=datetime.timezone.utc).timestamp() * 1000
    )


def get_seed_posts() -> list[PostMetadata]:
    """Return the curated list of seed PostMetadata entries.

    Order matters: the LAST entry in this list will appear FIRST on the
    feed (because the service prepends, so the most recently recorded
    sits at the head). The featured slot on the home page renders the
    head of the feed, so put the most editorially compelling entry last.
    """
    return [
        PostMetadata(
            post_id="56b1d8d1c87f",
            title="A Brief History of CSS Until 2023",
            subtitle="Where it came from, why it looks the way it does, and what's next.",
            preview_image_id="",
            creator_name="Manuel Matuzović",
            creator_id="",
            creator_avatar_id=None,
            collection_name="Frontend Weekly",
            reading_time=11,
            first_published_at=_ms(2023, 9, 18),
            updated_at=None,
            is_locked=False,
            medium_url="https://medium.com/@matuzo/a-brief-history-of-css-until-2023-56b1d8d1c87f",
            tags=["css", "web development", "frontend"],
        ),
        PostMetadata(
            post_id="2cb9b7e2d13c",
            title="Why I quit my Big Tech job to build a tiny startup",
            subtitle="Three years in: what I traded away, what I kept, and what I would not do again.",
            preview_image_id="",
            creator_name="Steph Smith",
            creator_id="",
            creator_avatar_id=None,
            collection_name="Better Programming",
            reading_time=8,
            first_published_at=_ms(2024, 2, 6),
            updated_at=None,
            is_locked=True,
            medium_url="https://medium.com/better-programming/why-i-quit-2cb9b7e2d13c",
            tags=["startups", "career", "programming"],
        ),
        PostMetadata(
            post_id="9e8c2f6b3a4d",
            title="The architecture of habit",
            subtitle="Habits aren't built — they're accreted, layer by layer, from things you almost didn't bother with.",
            preview_image_id="",
            creator_name="Sarah Wilson",
            creator_id="",
            creator_avatar_id=None,
            collection_name="Psychology Today",
            reading_time=9,
            first_published_at=_ms(2023, 11, 22),
            updated_at=None,
            is_locked=False,
            medium_url="https://medium.com/psychology-today/architecture-of-habit-9e8c2f6b3a4d",
            tags=["psychology", "self improvement", "habits"],
        ),
        PostMetadata(
            post_id="4f7a1b9c5e2d",
            title="Cybersecurity essentials for small businesses",
            subtitle="Seven cheap, boring fixes that prevent 80% of breaches — and the one expensive one that handles the rest.",
            preview_image_id="",
            creator_name="Michael Brown",
            creator_id="",
            creator_avatar_id=None,
            collection_name="Business Security",
            reading_time=8,
            first_published_at=_ms(2024, 1, 15),
            updated_at=None,
            is_locked=True,
            medium_url="https://medium.com/business-security/cybersecurity-essentials-4f7a1b9c5e2d",
            tags=["security", "small business", "cybersecurity"],
        ),
        PostMetadata(
            post_id="3b8e4d2f1a5c",
            title="Mastering the art of time management",
            subtitle="Forget the apps. The best time-management system is a notebook, a pencil, and an honest conversation.",
            preview_image_id="",
            creator_name="Emily Johnson",
            creator_id="",
            creator_avatar_id=None,
            collection_name="Personal Development",
            reading_time=6,
            first_published_at=_ms(2023, 10, 4),
            updated_at=None,
            is_locked=False,
            medium_url="https://medium.com/personal-development/time-management-3b8e4d2f1a5c",
            tags=["productivity", "self improvement"],
        ),
        PostMetadata(
            post_id="7c5e9d3a2b8f",
            title="Sustainable tech: small bets, large outcomes",
            subtitle="A walk through eight startups that aren't trying to save the planet — just to make one slow, dull, important thing 4% more efficient.",
            preview_image_id="",
            creator_name="David Lee",
            creator_id="",
            creator_avatar_id=None,
            collection_name="Green Technology",
            reading_time=11,
            first_published_at=_ms(2024, 3, 11),
            updated_at=None,
            is_locked=True,
            medium_url="https://medium.com/green-technology/sustainable-tech-7c5e9d3a2b8f",
            tags=["sustainability", "climate tech", "startups"],
        ),
        PostMetadata(
            post_id="2a6f8c1e4d9b",
            title="The rise of no-code is a story about audience",
            subtitle="No-code platforms aren't replacing engineers — they're inventing a new kind of builder, and the demographics are surprising.",
            preview_image_id="",
            creator_name="Alex Rodriguez",
            creator_id="",
            creator_avatar_id=None,
            collection_name="Software",
            reading_time=7,
            first_published_at=_ms(2024, 4, 2),
            updated_at=None,
            is_locked=False,
            medium_url="https://medium.com/software/no-code-audience-2a6f8c1e4d9b",
            tags=["no code", "software", "industry"],
        ),
        PostMetadata(
            post_id="8d3b5a7e9c1f",
            title="Mindfulness in the digital age",
            subtitle="Find balance and reduce stress in an increasingly connected world — without quitting anything you love.",
            preview_image_id="",
            creator_name="Lisa Chen",
            creator_id="",
            creator_avatar_id=None,
            collection_name="Digital Wellness",
            reading_time=4,
            first_published_at=_ms(2024, 4, 19),
            updated_at=None,
            is_locked=True,
            medium_url="https://medium.com/digital-wellness/mindfulness-8d3b5a7e9c1f",
            tags=["mindfulness", "wellness", "tech"],
        ),
        PostMetadata(
            post_id="5f2c4a6b8e1d",
            title="The future of AI in healthcare is already here — quietly",
            subtitle="Diagnostic models trained on 6M anonymized scans are now outperforming radiologists in narrow domains.",
            preview_image_id="",
            creator_name="John Smith",
            creator_id="",
            creator_avatar_id=None,
            collection_name="Tech in Medicine",
            reading_time=18,
            first_published_at=_ms(2024, 4, 25),
            updated_at=None,
            is_locked=True,
            medium_url="https://medium.com/tech-in-medicine/ai-healthcare-quietly-5f2c4a6b8e1d",
            tags=["ai", "healthcare", "machine learning"],
        ),
        PostMetadata(
            post_id="1e7b9d4a3c5f",
            title="Ten quiet habits of genuinely productive remote workers",
            subtitle="After interviewing 40 distributed engineers across six time zones, a pattern emerged — and it has nothing to do with calendars or coffee.",
            preview_image_id="",
            creator_name="Jane Doe",
            creator_id="",
            creator_avatar_id=None,
            collection_name="Productivity",
            reading_time=12,
            first_published_at=_ms(2024, 4, 30),
            updated_at=None,
            is_locked=True,
            medium_url="https://medium.com/productivity/quiet-habits-remote-1e7b9d4a3c5f",
            tags=["productivity", "remote work", "engineering"],
        ),
    ]
