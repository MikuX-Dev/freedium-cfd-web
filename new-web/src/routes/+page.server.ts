import { recentPosts, randomPosts, type RecentPost } from "@/services";
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

function toBlogPost(p: RecentPost, index: number): Omit<BlogPost, "id"> {
	const publishedMs = p.first_published_at ?? p.unlocked_at ?? Date.now();
	return {
		// Backend post_id is stable and URL-safe — pass it as the slug so
		// linking to /[slug] resolves cleanly through the existing render flow.
		slug: p.post_id,
		title: p.title,
		excerpt: p.subtitle,
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
	let feed: RecentPost[] = [];
	let randomFeed: RecentPost[] = [];
	let backendError: string | null = null;

	try {
		[feed, randomFeed] = await Promise.all([
			recentPosts(FEED_LIMIT),
			randomPosts(FEED_LIMIT),
		]);
	} catch (err) {
		// Backend offline or returned non-2xx — render the page with no posts
		// rather than failing the whole route. The hero still works because
		// it doesn't depend on this data.
		backendError = err instanceof Error ? err.message : "unknown error";
		console.warn("Failed to fetch recent posts:", backendError);
	}

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
		backendError,
	};
};
