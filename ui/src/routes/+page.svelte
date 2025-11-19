<script lang="ts">
	import type { ItemMetadata, ServerConfig } from '$lib/api';
	import { invalidateAll } from '$app/navigation';
	import { login, logout } from '$lib/api';

	type PageData = {
		path: string;
		config: ServerConfig | null;
		items: ItemMetadata[];
		configError: string | null;
		itemsError: string | null;
	};

	export let data: PageData;

	let requestedPath = data.path;
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

<main class="page">
	<header>
		<h1>Plone API Shell</h1>
	</header>

	{#if data.configError}
		{#if data.configError.includes('Backend server is not running')}
			<section class="panel error-panel">
				<h2>Backend Not Available</h2>
				<p class="error">{data.configError}</p>
				<p class="muted">
					The Python backend server couldn't be started. Make sure:
				</p>
				<ul class="muted">
					<li><code>ploneapi-shell</code> is installed (run <code>pip install ploneapi-shell</code>)</li>
					<li>The command is in your PATH</li>
					<li>Or set <code>PLONEAPI_SHELL_CMD</code> environment variable to the full path</li>
				</ul>
			</section>
		{:else}
			<section class="panel login-panel">
				<h2>Connect to Plone Site</h2>
				<form on:submit|preventDefault={handleLogin} class="login-form">
				<label>
					Site URL (API endpoint)
					<input
						type="url"
						bind:value={siteUrl}
						placeholder="https://yoursite.com/++api++/"
						required
						aria-label="Plone API base URL"
					/>
				</label>
				<label>
					Username
					<input
						type="text"
						bind:value={username}
						placeholder="admin"
						required
						aria-label="Plone username"
					/>
				</label>
				<label>
					Password
					<input
						type="password"
						bind:value={password}
						placeholder="••••••••"
						required
						aria-label="Plone password"
					/>
				</label>
				{#if loginError}
					<p class="error">{loginError}</p>
				{/if}
				<button type="submit" disabled={loggingIn}>
					{loggingIn ? 'Connecting...' : 'Connect'}
				</button>
			</form>
		</section>
		{/if}
	{:else if !data.config}
		<section class="panel login-panel">
			<h2>Connect to Plone Site</h2>
			<form on:submit|preventDefault={handleLogin} class="login-form">
				<label>
					Site URL (API endpoint)
					<input
						type="url"
						bind:value={siteUrl}
						placeholder="https://yoursite.com/++api++/"
						required
						aria-label="Plone API base URL"
					/>
				</label>
				<label>
					Username
					<input
						type="text"
						bind:value={username}
						placeholder="admin"
						required
						aria-label="Plone username"
					/>
				</label>
				<label>
					Password
					<input
						type="password"
						bind:value={password}
						placeholder="••••••••"
						required
						aria-label="Plone password"
					/>
				</label>
				{#if loginError}
					<p class="error">{loginError}</p>
				{/if}
				<button type="submit" disabled={loggingIn}>
					{loggingIn ? 'Connecting...' : 'Connect'}
				</button>
			</form>
		</section>
	{:else}
		<section class="panel">
			<h2>Current Configuration</h2>
			<p><strong>Base URL:</strong> {data.config.base_url}</p>
			<button type="button" on:click={handleLogout} class="logout-btn">Disconnect</button>
		</section>
	{/if}

	{#if data.config && !data.configError}
		<section class="panel">
			<form method="get" class="path-form">
				<label>
					Path
					<input
						type="text"
						name="path"
						placeholder="/"
						bind:value={requestedPath}
						aria-label="Path to fetch"
					/>
				</label>
				<button type="submit">Fetch Items</button>
			</form>
		</section>

		<section class="panel">
			<h2>Items</h2>
			{#if data.itemsError}
				<p class="error">{data.itemsError}</p>
			{:else if data.items.length === 0}
				<p class="muted">No items found at this path.</p>
			{:else}
				<div class="table-wrapper">
					<table>
						<thead>
							<tr>
								<th>Title</th>
								<th>Type</th>
								<th>State</th>
								<th>Modified</th>
							</tr>
						</thead>
						<tbody>
							{#each data.items as item}
								<tr>
									<td>
										<div class="item-title">
											<strong>{item.title ?? item.id ?? '(untitled)'}</strong>
											{#if item.description}
												<p class="muted">{item.description}</p>
											{/if}
										</div>
									</td>
									<td>{item.type ?? '—'}</td>
									<td>{item.review_state ?? '—'}</td>
									<td>{item.modified ? new Date(item.modified).toLocaleString() : '—'}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</section>
	{/if}
</main>

<style>
	:global(body) {
		font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
		background: #0f172a;
		margin: 0;
		color: #e2e8f0;
	}

	main.page {
		max-width: 960px;
		margin: 2rem auto;
		padding: 0 1.5rem 3rem;
	}

	header {
		margin-bottom: 1.5rem;
	}

	.panel {
		background: rgba(15, 23, 42, 0.75);
		border: 1px solid rgba(148, 163, 184, 0.2);
		border-radius: 12px;
		padding: 1.25rem;
		margin-bottom: 1.5rem;
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
		backdrop-filter: blur(12px);
	}

	.path-form {
		display: flex;
		gap: 1rem;
		align-items: flex-end;
		flex-wrap: wrap;
	}

	label {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		flex: 1;
		font-weight: 500;
	}

	input {
		padding: 0.65rem 0.75rem;
		border-radius: 8px;
		border: 1px solid rgba(148, 163, 184, 0.4);
		background: rgba(15, 23, 42, 0.8);
		color: inherit;
	}

	button {
		padding: 0.65rem 1rem;
		border-radius: 8px;
		border: none;
		background: #06b6d4;
		color: #0f172a;
		font-weight: 600;
		cursor: pointer;
		transition: transform 0.15s ease, box-shadow 0.15s ease;
	}

	button:hover {
		transform: translateY(-1px);
		box-shadow: 0 10px 25px rgba(6, 182, 212, 0.25);
	}

	.table-wrapper {
		overflow-x: auto;
	}

	table {
		width: 100%;
		border-collapse: collapse;
	}

	th,
	td {
		text-align: left;
		padding: 0.75rem;
		white-space: nowrap;
	}

	th {
		font-size: 0.85rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: #94a3b8;
		border-bottom: 1px solid rgba(148, 163, 184, 0.2);
	}

	tbody tr {
		border-bottom: 1px solid rgba(148, 163, 184, 0.15);
	}

	.item-title p {
		margin: 0.15rem 0 0;
		font-size: 0.85rem;
	}

	.error {
		color: #fb7185;
		margin: 0;
	}

	.muted {
		color: #94a3b8;
	}

	.login-panel {
		max-width: 500px;
		margin: 2rem auto;
	}

	.login-form {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.login-form label {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.logout-btn {
		margin-top: 1rem;
		background: #ef4444;
	}

	.logout-btn:hover {
		box-shadow: 0 10px 25px rgba(239, 68, 68, 0.25);
	}

	.error-panel {
		max-width: 600px;
		margin: 2rem auto;
	}

	.error-panel ul {
		margin: 1rem 0;
		padding-left: 1.5rem;
	}

	.error-panel code {
		background: rgba(148, 163, 184, 0.2);
		padding: 0.2rem 0.4rem;
		border-radius: 4px;
		font-size: 0.9em;
	}
</style>
