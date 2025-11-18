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

### 1. Configuration

First, configure the tool for your Plone site. Most Plone 6.x sites expose their API at `siteroot/++api++`.

**For public sites (no authentication):**
```bash
# Login will save the base URL (even without credentials, it sets up your config)
ploneapi-shell login --base https://yoursite.com/++api++/
# When prompted, just press Enter for username/password (or use --username "" --password "")
```

**For authenticated sites:**
```bash
# Login and save credentials + base URL
ploneapi-shell login --base https://yoursite.com/++api++/
# Enter your Plone username and password when prompted
```

After login, the base URL is saved and you can omit `--base` from subsequent commands.

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
- `ls` - List items with metadata (title, type, state, modified date)
- `cd <path>` - Navigate to content (supports relative paths and full URLs)
  - `cd images` - Navigate to images folder
  - `cd https://demo.plone.org/images` - Navigate using full URL
- `pwd` - Show current path
- `get [path]` - Fetch and display content
- `items [path]` - List items array
- `raw [path]` - Show raw JSON
- `components` - List available API components
- `tags [path]` - List all tags with frequency
- `similar-tags [tag] [threshold]` - Find similar tags (use `-t` or `--threshold` for custom threshold)
- `merge-tags <old> <new>` - Merge two tags
- `rename-tag <old> <new>` - Rename a tag
- `remove-tag <tag>` - Remove a tag from all items
- `help` - Show all commands
- `exit` - Exit shell

**Tab completion**: Press Tab to autocomplete commands and item names (shows clean names like "images" instead of full URLs).

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

```bash
# Find tags similar to a specific tag (default threshold: 70%)
ploneapi-shell similar-tags "swimming"

# Use a custom threshold (0-100)
ploneapi-shell similar-tags "swimming" --threshold 80

# Find all similar tag pairs across the site
ploneapi-shell similar-tags --threshold 75

# In REPL, use short flags
ploneapi-shell repl
> similar-tags -t 80
> similar-tags mytag --threshold 85
```

The similarity score uses fuzzy string matching (0-100%), showing tags that might be duplicates or variations.

#### Merge Tags

Merge one tag into another across all items:

```bash
# Merge "swimming" into "swim" on all items
ploneapi-shell merge-tags swimming swim

# In REPL
> merge-tags old-tag new-tag
```

This finds all items with the old tag and replaces it with the new tag (or adds the new tag if the item doesn't already have it).

#### Rename Tags

Rename a tag across all items (same as merge, but more intuitive name):

```bash
ploneapi-shell rename-tag old-name new-name
```

#### Remove Tags

Remove a tag from all items:

```bash
ploneapi-shell remove-tag unwanted-tag
```

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

### `login`
Authenticate with a Plone site and save the token. Prompts for username/password.

### `logout`
Remove saved credentials.

### `repl`
Launch interactive shell with tab completion and filesystem-like navigation. This is the default when no command is provided.

### `web`
Launch web-based interface using Streamlit. Opens at `http://localhost:8501` by default.
- `--port, -p` - Port to run on (default: 8501)
- `--host, -h` - Host to bind to (default: localhost)

### `tags [PATH]`
List all tags (subjects) with their frequency across the site or a specific path.
- `--path` - Limit search to items in this path
- `--base` - Override the API base URL
- `--no-auth` - Skip saved auth headers
- `--debug` - Show debug information about tag collection

### `similar-tags [TAG]`
Find tags similar to the given tag using fuzzy matching. If no tag is provided, finds all pairs of similar tags.
- `--threshold, -t` - Minimum similarity score (0-100, default: 70)
- `--path` - Limit search to items in this path
- `--base` - Override the API base URL
- `--no-auth` - Skip saved auth headers

Examples:
```bash
# Find tags similar to "swimming"
ploneapi-shell similar-tags swimming

# Use custom threshold
ploneapi-shell similar-tags swimming --threshold 80

# Find all similar tag pairs
ploneapi-shell similar-tags --threshold 75
```

### `merge-tags <OLD_TAG> <NEW_TAG>`
Merge one tag into another across all items. Finds all items with the old tag and replaces it with the new tag.

### `rename-tag <OLD_TAG> <NEW_TAG>`
Rename a tag across all items (alias for `merge-tags`).

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
