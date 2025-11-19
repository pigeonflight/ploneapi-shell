<script lang="ts">
	import type { ItemMetadata, ServerConfig } from '$lib/api';

	type PageData = {
		path: string;
		config: ServerConfig | null;
		items: ItemMetadata[];
		configError: string | null;
		itemsError: string | null;
	};

	export let data: PageData;

	let requestedPath = data.path;
</script>

<main class="page">
	<header>
		<h1>Plone API Shell UI</h1>
		<p>A faster desktop experience powered by SvelteKit + FastAPI.</p>
	</header>

	<section class="panel">
		<h2>Current Configuration</h2>
		{#if data.configError}
			<p class="error">{data.configError}</p>
		{:else if data.config}
			<p><strong>Base URL:</strong> {data.config.base_url}</p>
		{:else}
			<p class="muted">No configuration found yet. Run <code>ploneapi-shell login</code> first.</p>
		{/if}
	</section>

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
</style>
