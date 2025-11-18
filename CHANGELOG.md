# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.7] - 2025-01-XX

### Added
- **Tag autocompletion in REPL**: Tab completion now works for tag names in tag management commands
  - Autocomplete tag names for `merge-tags`, `rename-tag`, `remove-tag`, and `similar-tags` commands
  - Tags are cached per path/base URL for performance
  - Makes tag management much faster and easier in the interactive shell
  - Note: First autocomplete may be slow as it fetches all tags; subsequent completions are cached
- **Multiple tag merging**: `merge-tags` command now supports merging multiple source tags into one target tag
  - Example: `merge-tags swimming diving water-polo water-sports` merges all three tags into "water-sports"
  - Shows summary of items found for each source tag
  - Deduplicates items that have multiple source tags
- **Enhanced `similar-tags` documentation**: Comprehensive examples showing all usage patterns
  - CLI and REPL examples for all threshold syntax options (positional, `-t`, `--threshold`)
  - Examples for finding all similar pairs vs. finding similar tags for a specific tag
  - Guidance on finding misspellings: misspelled tags typically have 98%+ similarity scores

### Improved
- Enhanced documentation with examples of tag autocompletion and multiple tag merging
- Clearer error messages for tag management commands using `<source_tag>` and `<target_tag>` terminology
- More explicit examples for `similar-tags` command showing all syntax variations
- Added guidance on using high thresholds (98%+) to find misspelled tags

## [0.1.6] - 2025-01-XX

### Added
- **Tag Management Documentation**: Comprehensive README section covering all tag management features
  - Detailed examples for `tags`, `similar-tags`, `merge-tags`, `rename-tag`, and `remove-tag` commands
  - Usage examples for both CLI and REPL modes
  - Explanation of Plone's Subject field and tag indexing

## [0.1.5] - 2025-01-XX

### Added
- **Configurable similarity threshold**: `similar-tags` command now supports `-t`/`--threshold` flags in REPL
  - Use `similar-tags -t 80` or `similar-tags mytag --threshold 80` to set custom threshold
  - Threshold validation (0-100) with helpful warnings for invalid values
- **Enhanced tag discovery**: Improved Subject field detection for Plone's standard tagging system
  - Prioritizes checking the `Subject` field (Plone's standard field name)
  - Checks multiple field locations and formats
  - Better handling of different REST API response formats
- **Performance improvements**: Strategic caching for recursive tag browsing
  - Caches fetched items to avoid re-fetching during recursive browsing
  - Warning message when falling back to recursive browsing (indicates slower performance on large sites)
- **Enhanced debug output**: Improved debugging for tag collection
  - Shows whether Subject field is found in API responses
  - Displays item structure and field locations for troubleshooting
  - Better diagnostic information when tags aren't found

### Fixed
- Improved tag collection reliability by checking Subject field in multiple locations
- Better error handling and validation for threshold values

## [0.1.4] - 2025-11-18

### Added
- **Similar tags command**: New `similar-tags` command to find tags similar to a given tag using fuzzy matching
  - Uses thefuzz library for intelligent tag similarity detection
  - Configurable similarity threshold (default: 70%)
  - Shows tag name, frequency, and similarity score
  - Available in both CLI and REPL: `ploneapi-shell similar-tags <tag> [--threshold 70]`
- **Improved tags command**: Now uses search endpoint instead of browsing, finding tags across all items
  - Handles pagination to collect tags from large sites
  - More reliable tag discovery across the entire site or specific paths

### Fixed
- Fixed `tags` command returning "No tags found" when tags exist elsewhere in the site

## [0.1.3] - 2025-11-18

### Fixed
- **Critical**: Fixed URL resolution bug where base URLs without trailing slashes caused login endpoint to resolve incorrectly
  - `@login` endpoint now correctly resolves to `base/++api++/@login` instead of `base/@login`
  - Fixes 404 errors when logging in with base URLs like `https://site.com/++api++` (without trailing slash)

## [0.1.2] - 2025-11-18

### Fixed
- Fixed handling of Typer Option objects being passed to API functions
  - Added type checks in all API functions to ensure `base` parameter is always a string
  - Prevents "expected str or httpx.URL got class <typer.models.OptionInfo>" errors
  - Functions now gracefully fall back to default base URL if invalid type is passed

## [0.1.1] - 2025-11-18

### Fixed
- Fixed syntax errors in `merge-tags` and `remove-tag` commands (missing exception handlers)
- Fixed package metadata issues for PyPI upload compatibility

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

