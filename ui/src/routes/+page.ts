import type { PageLoad } from './$types';
import { fetchConfig, fetchItems, checkHealth } from '$lib/api';

export const load: PageLoad = async ({ fetch, url }) => {
	const path = url.searchParams.get('path') ?? '';

	let configError: string | null = null;
	let itemsError: string | null = null;
	let backendError: string | null = null;

	// First check if backend is running
	const healthResult = await Promise.allSettled([
		checkHealth(fetch).catch(() => null)
	]);

	const healthOk = healthResult[0].status === 'fulfilled' && healthResult[0].value === true;
	
	if (!healthOk) {
		backendError = 'Backend server is not running. Please ensure ploneapi-shell is installed and in your PATH.';
		return {
			path,
			config: null,
			items: [],
			configError: backendError,
			itemsError: null
		};
	}

	const [configResult, itemsResult] = await Promise.allSettled([
		fetchConfig(fetch),
		fetchItems(fetch, path || undefined)
	]);

	let config = null;
	if (configResult.status === 'fulfilled') {
		config = configResult.value;
	} else {
		configError = configResult.reason instanceof Error ? configResult.reason.message : 'Failed to load config';
	}

	let items: Awaited<ReturnType<typeof fetchItems>> = [];
	if (itemsResult.status === 'fulfilled') {
		items = itemsResult.value;
	} else {
		itemsError = itemsResult.reason instanceof Error ? itemsResult.reason.message : 'Failed to load items';
	}

	return {
		path,
		config,
		items,
		configError,
		itemsError
	};
};

