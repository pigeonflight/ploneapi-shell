# Plone API Shell UI (SvelteKit)

This package contains the new desktop experience we are building on top of SvelteKit + Bun.  
It communicates with the Python backend via the `ploneapi-shell serve` command (`FastAPI` bridge).

## Requirements

- Bun ≥ 1.1 (installs dependencies and runs scripts)
- Python backend running locally: `ploneapi-shell serve`

## Developing

```bash
# in repo root, start the backend API
ploneapi-shell serve --reload

# in another terminal
cd ui
bun run dev -- --open
```

By default the UI expects the API at `http://127.0.0.1:8787`.  
Override via `VITE_API_BASE` (create a `.env` file in this folder).

### Desktop (Tauri) workflow

```bash
# run the native shell with live reload
bun run desktop:dev

# produce a signed .app / DMG under src-tauri/target
bun run desktop:build
```

The Tauri app automatically launches `ploneapi-shell serve`.  
Set `PLONEAPI_SHELL_CMD=/path/to/venv/bin/ploneapi-shell` if you need to point at a custom virtualenv binary.

## Building

```bash
bun run build
```

Preview the production build with:

```bash
bun run preview
```

Deployments can use the default adapter (static output). For a desktop distribution we will wrap the built assets with Tauri/Electron after the API surface is complete.
