# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Web UI**: Streamlit-based web interface (`ploneapi-shell web`) with command interface
  - Same commands as REPL but with visual tables and JSON viewers
  - Sidebar with configuration and authentication
  - Plone logo support
- Interactive REPL shell with filesystem-like navigation (`ls`, `cd`, `pwd`)
- Metadata-rich `ls` command showing title, type, review state, and modification date
- **Improved tab completion**: Shows item names (e.g., "images") instead of full URLs
- **Full URL support**: `cd` command now accepts both relative paths and full URLs
  - `cd images` and `cd https://demo.plone.org/images` both work
- **Default behavior**: Running `ploneapi-shell` with no arguments launches the REPL
- Command history persistence
- `get`, `items`, `raw`, and `components` commands for API exploration
- Authentication support via `login` and `logout` commands
- Configurable base URL with automatic persistence
- Support for custom headers and query parameters
- Default base URL set to demo.plone.org for quick testing

### Planned
- `rename`, `cp`, `mv` commands for content management
- `transitions` command to list available workflow transitions
- `transition` command to execute workflow transitions
- `bulk-transition` command for bulk workflow operations
- Tag/keyword management commands (list, merge, rename, remove)

## [0.1.0] - 2025-01-XX

### Added
- Initial release
- Basic CLI commands: `get`, `items`, `components`
- Authentication via token-based login
- Interactive REPL shell
- Rich terminal output with tables and formatting
- Configuration file management

