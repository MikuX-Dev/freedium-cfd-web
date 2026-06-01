import { recentPosts, randomPosts, articleCount, type RecentPost } from "@/services";
import type { BlogPost } from "$lib/types";
import type { PageServerLoad } from "./$types";

/** How many real posts to surface from the backend feed. */
const FEED_LIMIT = 20;

/** Editorial cards interleaved with the live feed. Their slot positions are
 * fixed so the layout stays balanced regardless of how many real posts the
 * backend has returned. */
const EDITORIAL_CARDS: { position: number; post: Omit<BlogPost, "id"> }[] = [
	{
		position: 2,
		post: {
			cardType: "quote",
			quoteText:
				"Information wants to be free. Knowledge wants to be shared. Everything else is just plumbing.",
			title: "",
			excerpt: "",
			readingTime: "0",
			publishedAt: "",
			creator: "Editor",
			slug: "",
		},
	},
	{
		position: 5,
		post: {
			cardType: "stat",
			statValue: "94%",
			statLabel: "of paywalls bypassed cleanly",
			statDesc:
				"Across the top 200 publications. Failures are usually due to the article not being public yet — not the wall itself.",
			title: "",
			excerpt: "",
			readingTime: "0",
			publishedAt: "",
			creator: "",
			slug: "",
		},
	},
];

/** Build a cover-image URL routed through our own /img proxy+cache
 * instead of hitting Medium's CDN directly. The browser loads from our
 * domain (Traefik → backend → Mongo image_cache → WARP on miss), so it
 * never contacts Medium. Width must be in the backend's allowlist
 * (700/800/1400/2000/4000). Featured cards get a larger width. */
function mediumImageUrl(imageId: string, width: number): string {
	return `/img/${width}/${imageId}`;
}

function toBlogPost(p: RecentPost, index: number): Omit<BlogPost, "id"> {
	const publishedMs = p.first_published_at ?? p.unlocked_at ?? Date.now();
	return {
		// Backend post_id is stable and URL-safe — pass it as the slug so
		// linking to /[slug] resolves cleanly through the existing render flow.
		slug: p.post_id,
		title: p.title,
		excerpt: p.subtitle,
		// Cover image from the backend's preview_image_id. Empty id → no
		// imageUrl, so BlogCard falls back to its placeholder.
		imageUrl: p.preview_image_id
			? mediumImageUrl(p.preview_image_id, index === 0 ? 1400 : 800)
			: undefined,
		readingTime: String(p.reading_time || 1),
		publishedAt: new Date(publishedMs).toISOString(),
		creator: p.creator_name,
		collection: p.collection_name
			? { name: p.collection_name, avatarId: p.creator_avatar_id ?? "" }
			: null,
		// First real post becomes the wide featured card; rest are standard.
		cardType: index === 0 ? "featured" : "standard",
		size: index === 0 ? "wide" : undefined,
	};
}

function interleave(
	feedPosts: Omit<BlogPost, "id">[],
	editorial: typeof EDITORIAL_CARDS,
): Omit<BlogPost, "id">[] {
	if (feedPosts.length === 0) return [];
	const out: Omit<BlogPost, "id">[] = [...feedPosts];
	// Insert editorial cards from highest position to lowest so earlier
	// inserts don't shift the indexes of later ones.
	const sorted = [...editorial].sort((a, b) => b.position - a.position);
	for (const { position, post } of sorted) {
		const insertAt = Math.min(position, out.length);
		out.splice(insertAt, 0, post);
	}
	return out;
}

export const load: PageServerLoad = async () => {
	// Real "articles unlocked" count for the banner. Eager + resilient: the
	// backend count is a fast estimated Mongo count; null on failure → the
	// banner just hides the stat rather than showing a fake number.
	const unlockedCount = await articleCount().catch(() => null);

	const streamed = Promise.all([
		recentPosts(FEED_LIMIT).catch(() => [] as RecentPost[]),
		randomPosts(FEED_LIMIT).catch(() => [] as RecentPost[]),
	]).then(([feed, randomFeed]) => {
		const feedAsBlogPosts = feed.map((p, i) => toBlogPost(p, i));
		const merged = interleave(feedAsBlogPosts, EDITORIAL_CARDS);
		const items: BlogPost[] = merged.map((post, id) => ({ ...post, id }));

		const randomAsBlogPosts = randomFeed.map((p, i) => toBlogPost(p, i));
		const randomMerged = interleave(randomAsBlogPosts, EDITORIAL_CARDS);
		const randomItems: BlogPost[] = randomMerged.map((post, id) => ({ ...post, id }));

		return {
			items,
			randomItems,
			isFeedEmpty: feed.length === 0,
			backendError: null as string | null,
		};
	}).catch((err) => {
		console.warn("Failed to fetch posts:", err);
		return {
			items: [] as BlogPost[],
			randomItems: [] as BlogPost[],
			isFeedEmpty: true,
			backendError: (err as Error)?.message ?? "unknown",
		};
	});

	return { streamed, unlockedCount };
};
