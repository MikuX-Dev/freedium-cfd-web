/**
 * Common/shared type definitions
 */

import type { Component } from 'svelte';

/**
 * Button variant types
 */
export type ButtonVariant = 'default' | 'destructive' | 'outline' | 'secondary' | 'ghost' | 'link';

/**
 * Props for external link buttons (Ko-fi, Liberapay, Discord, etc.)
 */
export interface PayButtonProps {
	name: string;
	url: string;
	icon: Component;
	showLabel?: boolean;
}

/**
 * Props for the report problem component
 */
export interface ReportProblemProps {
	showBadge?: boolean;
	compact?: boolean;
}

/**
 * Generic API error response
 */
export interface ApiError {
	status: number;
	message: string;
	code?: string;
	details?: string;
}

/**
 * Navigation item for menus
 */
export interface NavItem {
	label: string;
	href: string;
	icon?: Component;
	external?: boolean;
}
