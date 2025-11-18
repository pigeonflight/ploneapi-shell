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

Launch the interactive REPL for easier navigation:

```bash
ploneapi-shell repl
```

Inside the shell, use filesystem-like commands:
- `ls` - List items with metadata
- `cd <path>` - Navigate to content
- `pwd` - Show current path
- `get [path]` - Fetch content
- `help` - Show commands
- `exit` - Exit shell

![Interactive Shell - ls command](screenshots/ls%20command.png)

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
Launch interactive shell with tab completion and filesystem-like navigation.

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

## Author

David Bain ([@pigeonflight](https://x.com/pigeonflight) on X)
