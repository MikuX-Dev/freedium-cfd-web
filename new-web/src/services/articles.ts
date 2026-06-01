import apiFetch from "@/api";

export interface RecentPost {
	post_id: string;
	title: string;
	subtitle: string;
	creator_name: string;
	creator_avatar_id: string | null;
	collection_name: string | null;
	reading_time: number;
	first_published_at: number | null;
	preview_image_id: string;
	medium_url: string;
	tags: string[];
	unlocked_at: number;
}

interface RecentPostsResponse {
	posts: RecentPost[];
}

export async function recentPosts(limit = 20): Promise<RecentPost[]> {
	const response = await apiFetch<RecentPostsResponse>("/articles/recent", {
		method: "GET",
		query: { limit },
	});

	return response?.posts ?? [];
}

export async function randomPosts(limit = 20): Promise<RecentPost[]> {
	const response = await apiFetch<RecentPostsResponse>("/articles/random", {
		method: "GET",
		query: { limit },
	});

	return response?.posts ?? [];
}

/** All-time count of distinct articles Freedium has unlocked (L1 cache size). */
export async function articleCount(): Promise<number> {
	const response = await apiFetch<{ count: number }>("/articles/count", { method: "GET" });
	return response?.count ?? 0;
}
