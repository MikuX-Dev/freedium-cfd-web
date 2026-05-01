export type BlogPostSize = 'small' | 'medium' | 'large' | 'wide' | 'tall';

export type CardType = 'standard' | 'featured' | 'quote' | 'stat';

export interface BlogCollection {
  name: string;
  avatarId: string;
}

export interface BlogPost {
  id: number;
  title: string;
  excerpt: string;
  imageUrl?: string;
  bottomImageUrl?: string | null;
  size?: BlogPostSize | null;
  readingTime: string;
  publishedAt: string;
  collection?: BlogCollection | null;
  creator: string;
  slug: string;
  cardType?: CardType;
  quoteText?: string;
  statValue?: string;
  statLabel?: string;
  statDesc?: string;
}

export interface SearchPost {
  id: string;
  title: string;
  date: Date;
  excerpt: string;
  imageUrl: string;
}
