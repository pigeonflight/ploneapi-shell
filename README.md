# Plone API Shell

Interactive command-line shell and CLI tool for exploring Plone REST API sites.

Most modern **Plone 6.x** sites expose their REST API at `siteroot/++api++`. This tool provides an interactive shell with filesystem-like navigation (`ls`, `cd`, `pwd`) plus direct API commands for exploring Plone content.

## Installation

```bash
pip install ploneapi-shell
```

Or from source:

```bash
git clone <repo-url>
cd ploneapi-shell
pip install -r requirements.txt
pip install -e .
```

## Quick Start

### 1. Configure (preferred: log in from the REPL)

Launch the REPL pointed at your site and use the built-in `login` command to save both the base URL and your token in one place.

```bash
# Start the REPL with your API base (default command already launches the REPL)
ploneapi-shell --base https://yoursite.com/++api++/

# Inside the prompt:
plone> login                # prompts for username/password
plone> login editor secret  # optional inline credentials
plone> logout               # remove the saved token when you are done
plone> connect demo.plone.org        # change to another site without leaving the shell
plone> connect localhost:3000        # auto-uses http:// and appends /++api++/
```

- **Public sites**: still run `login` so the base URL is saved; just press Enter when prompted for credentials (or pass empty strings).
- **Authenticated sites**: enter your Plone username/password when prompted; the token is stored under `~/.config/ploneapi_shell`.
- **Background refresh**: once authenticated, the shell automatically renews your token in the background via `@login-renew` before it expires. You only need to re-run `login` if renewal fails (e.g., your password changed).
- **Switching sites**: use `connect <site>` inside the REPL to change bases. It accepts bare hosts (adds `https://` automatically, or `http://` for `localhost`/IP addresses) and appends `/++api++/` if you leave it out.

Prefer the REPL for auth because it mirrors what you do during day-to-day exploration and makes it obvious when your session expires. The standalone CLI command `ploneapi-shell login ...` remains available for scripting or CI workflows where the REPL isn’t convenient.

After logging in once, you can omit `--base` for future sessions; the saved config will be reused automatically.

### 2. Basic Usage

```bash
# Explore the API root (uses saved base URL)
ploneapi-shell get

# List available components
ploneapi-shell components

# Browse content items
ploneapi-shell items /news

# Get specific content
ploneapi-shell get /news/some-article

# View raw JSON
ploneapi-shell get /news --raw
```

### 3. Interactive Shell

Launch the interactive REPL (default when no command is given):

```bash
ploneapi-shell
# or explicitly:
ploneapi-shell repl
```

Inside the shell, use filesystem-like commands:
- `connect <site>` - Switch the active base URL (auto adds scheme/`++api++`; clears stored token so you can log into the new site)
- `login [username] [password]` - Authenticate and save a token (prompts if you omit credentials; inline args are optional)
- `ls` - List items with metadata (title/ID combined, type, state, modified date). Shows both the human-readable title (bold) and the object ID/name (dim) in a single column, making it easy to distinguish items with similar titles (e.g., "Member" vs "member" vs "Members").
- `cd <path>` - Navigate to content (supports relative paths, deep paths, and full URLs)
  - `cd images` - Navigate to images folder
  - `cd files/mystuff/here` - Navigate to deep nested paths (tab completion works at each level)
  - `cd https://demo.plone.org/images` - Navigate using full URL
- `pwd` - Show current path
- `get [path]` - Fetch and display content
- `items [path]` - List items array
- `raw [path]` - Show raw JSON
- `components` - List available API components
- `search <type> [--path <path>]` - Search for items by object type (portal_type)
  - `search Document` - Find all Document items
  - `search Folder --path /some/path` - Find Folders in a specific path
- `tags [path]` - List all tags with frequency
- `similar-tags [tag] [threshold]` - Find similar tags
  - `similar-tags swimming` - Find tags similar to "swimming" (default threshold: 70%)
  - `similar-tags swimming 80` - Preferred pattern: supply the tag and then the threshold (`80` here) without extra flags
  - `similar-tags swimming -t 85` - Use `-t` flag for threshold
  - `similar-tags -t 75` - Find all similar pairs with threshold 75
- `merge-tags <old> <new>` - Merge two tags
- `rename-tag <old> <new>` - Rename a tag
- `remove-tag <tag>` - Remove a tag from all items
- `help` - Show all commands
- `serve` - Start the local HTTP API for the desktop UI
- `logout` - Remove saved credentials (same as the CLI `logout` command)
- `exit` / `quit` - Leave the interactive shell (does not remove saved credentials)

**Tab completion**: Press Tab to autocomplete:
- Commands (e.g., type `mer<Tab>` to complete `merge-tags`)
- Item names for navigation commands like `cd`, `get`, `items` (shows clean names like "images" instead of full URLs)
- Deep paths: Type `cd files/mystuff/<Tab>` to autocomplete items in nested directories
- Tag names for tag management commands like `merge-tags`, `rename-tag`, `remove-tag`, `similar-tags`

**Note**: Tag autocompletion may be slow on the first use as it fetches all tags from the site. Subsequent completions are cached and much faster.

![Interactive Shell - ls command](screenshots/ls%20command.png)

### 4. Web Interface

Launch a web-based interface with the same command functionality:

```bash
ploneapi-shell web
```

This opens a Streamlit web interface at `http://localhost:8501` with:
- Command input box (same commands as REPL)
- Visual tables for `ls` and `items` output
- JSON viewer for `raw` command
- Sidebar with configuration and authentication
- Command history

The web interface provides the same functionality as the REPL but with a browser-based UI, making it easier to view and interact with Plone content.

### 4b. Desktop UI (SvelteKit)

We're actively building a modern desktop interface using SvelteKit + FastAPI.

1. Start the backend bridge:
   ```bash
   ploneapi-shell serve --host 127.0.0.1 --port 8787
   ```
2. Run the SvelteKit app:
   ```bash
   cd ui
   bun run dev --open
   ```

The Svelte UI talks to the `serve` API (`/api/get`, `/api/items`, etc.), giving you a fast desktop-like experience that will replace the Streamlit prototype over time.

For a native macOS build we embed the Svelte assets inside a Tauri shell:

```bash
cd ui
# run the desktop app in dev mode (spawns bun dev + tauri)
bun run desktop:dev

# produce a signed .app / DMG under ui/src-tauri/target
bun run desktop:build
```

The Tauri app automatically launches `ploneapi-shell serve` on startup. If your CLI lives in a virtualenv, point the app to it with `PLONEAPI_SHELL_CMD=/path/to/venv/bin/ploneapi-shell` before running the desktop binaries.

**Available REST endpoints**

- `GET /api/health` – quick status check for the bridge
- `GET /api/config` – returns the currently saved base URL
- `GET /api/get?path=/news` – fetches JSON for any path (supports `raw=true`)
- `GET /api/items?path=/news` – lists folderish content with metadata
- `GET /api/tags?path=/news` – aggregated Subject counts
- `GET /api/similar-tags?tag=swimming&threshold=80`
- `POST /api/tags/merge` – merge multiple tags into one (accepts `dry_run`)
- `POST /api/tags/rename` – rename a tag (same payload as merge but single tag)
- `POST /api/tags/remove` – remove a tag from every item

### 5. Tag Management

Plone uses the **Subject** field for tagging content. This tool provides powerful commands for discovering, analyzing, and managing tags across your Plone site.

#### List All Tags

Get a comprehensive list of all tags with their frequency:

```bash
# List all tags in the entire site
ploneapi-shell tags

# List tags in a specific path
ploneapi-shell tags /news

# Enable debug mode to see diagnostic information
ploneapi-shell tags --debug
```

The command uses Plone's search endpoint for efficient tag discovery across large sites. If the search endpoint doesn't return tags, it falls back to recursive browsing (with a warning, as this is slower on large sites).

#### Find Similar Tags

Use fuzzy matching to find tags with similar names, useful for cleaning up duplicate or misspelled tags:

**CLI Examples (positional threshold is recommended):**
```bash
# Find tags similar to a specific tag (default threshold: 70%)
ploneapi-shell similar-tags "swimming"

# Preferred: provide the threshold right after the tag (no flags needed)
ploneapi-shell similar-tags "swimming" 80

# Use a custom threshold with --threshold flag
ploneapi-shell similar-tags "swimming" --threshold 80

# Use short -t flag for threshold
ploneapi-shell similar-tags "swimming" -t 85

# Find all similar tag pairs across the site (no query tag)
ploneapi-shell similar-tags --threshold 75

# Find all similar pairs with default threshold (70%)
ploneapi-shell similar-tags
```

**REPL Examples:**
```bash
ploneapi-shell repl
# Find similar tags with default threshold
> similar-tags swimming

# Preferred: provide the threshold right after the tag
> similar-tags swimming 80

# Use threshold as first argument (finds all pairs with that threshold)
> similar-tags 80

# Use -t flag for threshold
> similar-tags swimming -t 80

# Use --threshold flag
> similar-tags swimming --threshold 85

# Find all similar pairs with custom threshold
> similar-tags -t 75

# Tab completion for tag names
> similar-tags sw<Tab>  # Autocompletes tag names starting with "sw"
```

**Understanding the output:**
- When you provide a tag: Shows tags similar to that tag with similarity scores
- When you don't provide a tag: Shows all pairs of similar tags above the threshold
- Similarity scores range from 0-100% (higher = more similar)

The similarity score uses fuzzy string matching (0-100%), showing tags that might be duplicates or variations.

**Finding misspellings:** Misspelled tags typically have very high similarity scores (98% or higher). To find potential misspellings, use a high threshold:
```bash
# Find likely misspellings (98%+ similarity)
ploneapi-shell similar-tags --threshold 98

# Find misspellings of a specific tag
ploneapi-shell similar-tags "swimming" --threshold 98
```

**Tip**: In the REPL, use Tab to autocomplete tag names when providing a query tag. The first autocomplete may be slow as it fetches all tags; subsequent completions are cached.

#### Merge Tags

Merge one or more tags into a target tag across all items. The target tag can be an existing tag or a new tag:

```bash
# Merge one tag into another
ploneapi-shell merge-tags swimming swim

# Merge multiple tags into one (consolidate tags)
ploneapi-shell merge-tags swimming diving water-polo water-sports

# Merge into an existing tag (both tags will be merged)
ploneapi-shell merge-tags "swimming" "water-sports"

# In REPL (with tab completion for tags)
> merge-tags sw<Tab>  # Autocompletes tag names starting with "sw"
> merge-tags swimming diving water-sports
```

This finds all items with any of the source tags and replaces them with the target tag (or adds the target tag if the item doesn't already have it). The target tag can be an existing tag (to consolidate tags) or a new tag name.

**Tip**: In the REPL, use Tab to autocomplete tag names when typing tag management commands. Note that the first autocomplete may be slow as it fetches all tags from the site; subsequent completions are cached and faster.

#### Rename Tags

Rename a tag across all items. The new name can be an existing tag (which will merge them) or a new tag:

```bash
# Rename to a new tag name
ploneapi-shell rename-tag old-name new-name

# Rename to an existing tag (merges them)
ploneapi-shell rename-tag "swimming" "water-sports"

# In REPL (with tab completion)
> rename-tag <Tab>  # Shows all available tags
> rename-tag swimming water-sports
```

**Tip**: In the REPL, use Tab to autocomplete tag names. The first autocomplete may be slow as it fetches all tags; subsequent completions are cached.

#### Remove Tags

Remove a tag from all items:

```bash
ploneapi-shell remove-tag unwanted-tag

# In REPL (with tab completion)
> remove-tag <Tab>  # Shows all available tags
> remove-tag unwanted-tag
```

**Tip**: In the REPL, use Tab to autocomplete tag names. The first autocomplete may be slow as it fetches all tags; subsequent completions are cached.

**Note**: Tag management commands require authentication. Make sure you're logged in with appropriate permissions.

### Advanced: Using Different Sites

To work with multiple sites or override the saved base URL:

```bash
# Use a different site for one command
ploneapi-shell get --base https://othersite.com/++api++/

# Skip saved auth for a specific request
ploneapi-shell get /public --no-auth

# Logout (removes saved credentials)
ploneapi-shell logout
```

## Examples

### Exploring a Public Site

```bash
# Get site root
ploneapi-shell get --base https://yoursite.com/++api++/

# List news items
ploneapi-shell items /news --base https://yoursite.com/++api++/

# Get specific content
ploneapi-shell get /news/some-article --base https://yoursite.com/++api++/

# View raw JSON
ploneapi-shell get /news --raw --base https://yoursite.com/++api++/
```

### Working with Authenticated Sites

```bash
# Login once
ploneapi-shell login --base https://yoursite.com/++api++/
# Enter username and password when prompted

# Now browse authenticated content
ploneapi-shell get /members-only
ploneapi-shell items /private-folder

# Use interactive shell for easier navigation
ploneapi-shell repl
# > ls
# > cd private-folder
# > get
```

### Custom Headers and Parameters

```bash
# Add custom headers
ploneapi-shell get /content --header "Accept:application/json" --header "X-Custom:value"

# Add query parameters
ploneapi-shell get /search --param "q:swimming" --param "limit:10"
```

## Configuration
# Upgrade

To upgrade to the latest release of `ploneapi-shell`, reinstall it with your package manager of choice:

```bash
# pip users
pip install --upgrade ploneapi-shell

# pipx users
pipx upgrade ploneapi-shell

# If installed in a virtualenv/system Python
python -m pip install -U ploneapi-shell
```

Confirm your version after upgrading:

```bash
ploneapi-shell --version
```


Credentials and base URL are stored in `~/.config/ploneapi_shell/config.json` (or override with `PLONEAPI_SHELL_CONFIG` environment variable).

The config file stores:
- `base` - Default API base URL
- `auth` - Authentication token (from `login` command)

## Publishing to PyPI

The default setuptools metadata currently adds fields (`license-file`, `license-expression`) that PyPI rejects. Run the helper script so the build artifacts are fixed automatically:

```bash
# Build wheel + sdist and scrub the metadata
python fix_metadata.py

# Only rebuild the sdist, if needed
python fix_metadata.py -- --sdist

# Skip building (only clean existing artifacts)
python fix_metadata.py --skip-build
```

After running the script, upload as usual:

```bash
twine check dist/*
twine upload dist/*
```

## Commands

### `get [PATH]`
Fetch any API path. Shows summary by default, use `--raw` for full JSON.

### `items [PATH]`
List the `items` array from a container endpoint in a formatted table.

### `components`
List all available `@components` endpoints from the API root.

### `search <TYPE> [--path <PATH>]`
Search for items by object type (portal_type). Useful for finding all items of a specific type across the site.

**Examples:**
```bash
# Find all Document items
ploneapi-shell search Document

# Find all Folders in a specific path
ploneapi-shell search Folder --path /news

# In REPL
plone> search Document
plone> search Folder --path /news
```

The results are displayed in the same format as the `ls` command, showing title, ID, type, state, and modification date.

### `login`
Authenticate with a Plone site and save the token. Prompts for username/password. The same command is available inside the REPL, so you can refresh credentials without leaving the shell. Tokens auto-renew in the background via `@login-renew`; manual `login` is only needed when renewal fails or you switch accounts.

### `logout`
Remove saved credentials. Also available directly inside the REPL.

### `connect <SITE>`
Change the currently active base URL inside the REPL. Accepts bare hosts (adds `https://` automatically, or `http://` for `localhost`/IP addresses) and appends `/++api++/` if you omit it. Switching sites clears the saved token so you can log in afresh.

### `repl`
Launch interactive shell with tab completion and filesystem-like navigation. This is the default when no command is provided.

### `web`
Launch web-based interface using Streamlit. Opens at `http://localhost:8501` by default.
- `--port, -p` - Port to run on (default: 8501)
- `--host, -h` - Host to bind to (default: localhost)

### `serve`
Start the lightweight FastAPI bridge that powers the new SvelteKit-based desktop UI.  
The server listens on `http://127.0.0.1:8787` by default and exposes REST endpoints that mirror the interactive commands (`/api/get`, `/api/items`, etc.).

- `--host, -h` - Host interface (default: 127.0.0.1)
- `--port, -p` - Port to listen on (default: 8787)
- `--reload` - Enable auto-reload while developing the UI
- `--allow-origin` - Additional CORS origin allowed to call the API (repeatable)

### `tags [PATH]`
List all tags (subjects) with their frequency across the site or a specific path.
- `--path` - Limit search to items in this path
- `--base` - Override the API base URL
- `--no-auth` - Skip saved auth headers
- `--debug` - Show debug information about tag collection

### `similar-tags [TAG] [THRESHOLD]`
Find tags similar to the given tag using fuzzy matching. If no tag is provided, finds all pairs of similar tags.

**Arguments:**
- `TAG` (optional) - Tag to find similar matches for. If omitted, finds all similar tag pairs.
- `THRESHOLD` (optional) - Minimum similarity score (0-100, default: 70). Recommended input is the positional syntax right after the tag (e.g., `similar-tags swimming 80`). Other supported forms:
  - Positional argument: `similar-tags swimming 80` or `similar-tags 80` (for all pairs)
  - Flag: `--threshold 80` or `-t 80`

**Options:**
- `--threshold, -t` - Minimum similarity score (0-100, default: 70)
- `--path` - Limit search to items in this path
- `--base` - Override the API base URL
- `--no-auth` - Skip saved auth headers

**CLI Examples:**
```bash
# Find tags similar to "swimming" (default threshold: 70%)
ploneapi-shell similar-tags swimming

# Find similar tags with custom threshold (positional)
ploneapi-shell similar-tags swimming 80

# Find similar tags with custom threshold (flag)
ploneapi-shell similar-tags swimming --threshold 80
ploneapi-shell similar-tags swimming -t 85

# Find all similar tag pairs (no query tag)
ploneapi-shell similar-tags --threshold 75
ploneapi-shell similar-tags -t 80
```

**REPL Examples:**
```bash
> similar-tags swimming          # Default threshold (70%)
> similar-tags swimming 80        # Positional threshold
> similar-tags swimming -t 85     # Flag threshold
> similar-tags -t 75              # All pairs with threshold 75
> similar-tags 80                 # All pairs with threshold 80 (positional)
> similar-tags -t 98              # Find likely misspellings (98%+ similarity)
> similar-tags swimming -t 98     # Find misspellings of "swimming"
```

**Finding misspellings:** Misspelled tags typically have very high similarity scores (98% or higher). Use a high threshold to find potential misspellings:
```bash
# Find all likely misspellings across the site
ploneapi-shell similar-tags --threshold 98

# Find misspellings of a specific tag
ploneapi-shell similar-tags "swimming" --threshold 98
```

### `merge-tags <SOURCE_TAG>... <TARGET_TAG>`
Merge one or more tags into a target tag across all items. Finds all items with any of the source tags and replaces them with the target tag. The target tag can be an existing tag (to consolidate tags) or a new tag name.

Examples:
```bash
# Merge one tag
ploneapi-shell merge-tags swimming swim

# Merge multiple tags
ploneapi-shell merge-tags swimming diving water-polo water-sports
```

**REPL Tip**: Use Tab to autocomplete tag names when typing source tags.

### `rename-tag <OLD_NAME> <NEW_NAME>`
Rename a tag across all items. The new name can be an existing tag (which will merge them) or a new tag name.

### `remove-tag <TAG>`
Remove a tag from all items that have it.

## API Endpoints

Plone REST API typically exposes:

- `@login` - Authentication endpoint
- `@types` - Available content types
- `@navigation` - Site navigation structure
- `@breadcrumbs` - Breadcrumb navigation
- `@workflow` - Workflow information
- `@actions` - Available actions

Most content items are accessible at their URL path under `++api++`, and containers expose an `items` array with child content.

## License

MIT License - see [LICENSE](LICENSE) file for details.

Copyright (c) 2025 David Bain

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

This tool is built on top of the **Plone REST API** (`plone.restapi`), which provides the foundation for all API interactions. We are grateful to the Plone REST API team and the broader Plone community for their incredible work.

### Plone REST API

The Plone REST API was originally authored by **Timo Stollenwerk** and has been developed and maintained by the Plone community with significant contributions from:

**Key Contributors:**
- Timo Stollenwerk (original author)
- Thomas Buchberger
- Lukas Graf
- Víctor Fernández de Alba
- Paul Roeland
- Mikel Larreategi
- Eric Brehault
- Andreas Zeidler
- Carsten Senger
- Tom Gross
- Roel Bruggink
- Yann Fouillat (Gagaro)
- Sune Brøndum Wøller
- Philippe Gross
- Andrea Cecchi
- Luca Bellenghi
- Giacomo Monari
- Alin Voinea
- Rodrigo Ferreira de Souza

**Organizations:**
- kitconcept GmbH (Germany)
- 4teamwork (Switzerland)
- CodeSyntax (Spain)

And many other contributors from the global Plone community.

### Plone

Plone itself was initiated in 1999 by **Alexander Limi**, **Alan Runyan**, and **Vidar Andersen**, and has been developed and maintained by a dedicated global community of developers, designers, and advocates.

For more information about the Plone community and contributors, visit:
- [Plone Foundation](https://plone.org/foundation)
- [Plone REST API Documentation](https://plonerestapi.readthedocs.io/)
- [Plone GitHub Organization](https://github.com/plone)

## Author

David Bain ([@pigeonflight](https://x.com/pigeonflight) on X)
