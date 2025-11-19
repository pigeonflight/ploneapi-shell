<script lang="ts">
	import type { ItemMetadata, ServerConfig, Tag, SimilarTag, TagOperationResult, CommandResult } from '$lib/api';
	import { invalidateAll } from '$app/navigation';
	import { login, logout, fetchTags, findSimilarTags, mergeTags, renameTag, removeTag, executeCommand } from '$lib/api';
	import { Folder, Tag as TagIcon, Terminal, Edit, GitMerge, Trash2, Search, Lightbulb } from 'lucide-svelte';

	type PageData = {
		path: string;
		config: ServerConfig | null;
		items: ItemMetadata[];
		configError: string | null;
		itemsError: string | null;
	};

	export let data: PageData;

	let siteUrl = '';
	let username = '';
	let password = '';
	let loginError = '';
	let loggingIn = false;

	async function handleLogin() {
		loggingIn = true;
		loginError = '';
		try {
			await login(siteUrl, username, password);
			await invalidateAll();
		} catch (err) {
			loginError = err instanceof Error ? err.message : 'Login failed';
		} finally {
			loggingIn = false;
		}
	}

	async function handleLogout() {
		try {
			await logout();
			await invalidateAll();
		} catch (err) {
			console.error('Logout failed:', err);
		}
	}
</script>

<div style="padding: 2rem; background: white; min-height: 100vh;">
	<h1>Plone API Shell</h1>
	
	{#if data?.configError}
		<div style="padding: 1rem; background: #fee; border: 1px solid #fcc; margin: 1rem 0;">
			<h2>Error</h2>
			<p>{data.configError}</p>
		</div>
	{:else if !data?.config}
		<div style="padding: 2rem; border: 1px solid #ccc; margin: 1rem 0;">
			<h2>Connect to Plone Site</h2>
			<form on:submit|preventDefault={handleLogin}>
				<div style="margin: 1rem 0;">
					<label>Site URL</label>
					<input type="url" bind:value={siteUrl} placeholder="https://yoursite.com" required style="width: 100%; padding: 0.5rem; margin-top: 0.25rem;" />
				</div>
				<div style="margin: 1rem 0;">
					<label>Username</label>
					<input type="text" bind:value={username} required style="width: 100%; padding: 0.5rem; margin-top: 0.25rem;" />
				</div>
				<div style="margin: 1rem 0;">
					<label>Password</label>
					<input type="password" bind:value={password} required style="width: 100%; padding: 0.5rem; margin-top: 0.25rem;" />
				</div>
				{#if loginError}
					<p style="color: red; margin: 1rem 0;">{loginError}</p>
				{/if}
				<button type="submit" disabled={loggingIn} style="padding: 0.75rem 1.5rem; background: #0283BE; color: white; border: none; border-radius: 4px; cursor: pointer;">
					{loggingIn ? 'Connecting...' : 'Connect'}
				</button>
			</form>
		</div>
	{:else}
		<div style="padding: 1rem; background: #efe; border: 1px solid #cfc; margin: 1rem 0;">
			<p><strong>Connected to:</strong> {data.config.base_url}</p>
			<button on:click={handleLogout} style="padding: 0.5rem 1rem; background: #666; color: white; border: none; border-radius: 4px; cursor: pointer; margin-top: 0.5rem;">
				Logout
			</button>
		</div>
	{/if}
</div>

<style>
	:global(body) {
		margin: 0;
		padding: 0;
		font-family: system-ui, sans-serif;
	}
</style>
