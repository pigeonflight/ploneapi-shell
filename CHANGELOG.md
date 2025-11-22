# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.22] - 2025-01-XX

### Added
- **Ploa desktop alternative mention**: Added references to [Ploa](https://ploa.incrementic.com) - a desktop application designed for users who prefer point-and-click interfaces over command-line tools
  - Mentioned in README introduction and web interface section
  - Added info box in Streamlit web UI sidebar
  - Added link in web UI title area

### Changed
- **Improved Streamlit web UI**: Enhanced chat-like interface with better fixed input positioning
  - Command input now properly fixed at bottom of viewport
  - Improved JavaScript to maintain fixed positioning after Streamlit reruns
  - Better layout structure to prevent input from scrolling off screen

### Fixed
- **Streamlit command repetition**: Clearing the command input now happens safely before the widget is instantiated, preventing duplicate command execution in the web UI.

## [0.1.21] - 2025-01-XX

### Added
- **Prompt authentication indicator**: REPL prompt now shows the current login status (e.g., `plone (admin)>` or `plone (anonymous)>`)

### Changed
- **Automated build metadata cleanup**: `sdist`/`bdist_wheel` commands now strip unsupported metadata fields automatically, so manual post-build fixes are no longer needed.

## [0.1.20] - 2025-01-XX

### Added
- **Index-based block operations**: Block commands now support 1-based index notation (matching web interface behavior)
  - `delete-block 3` - Delete block at position 3 (1-based index)
  - `move-block 3 up` - Move block at position 3 up one position
  - `move-block-up 3` - Shortcut command to move block at position 3 up
  - Index-based operations work alongside existing block ID/partial ID support
  - When moving block at position 3 up, it becomes position 2, and old position 2 becomes position 3 (matching web UI behavior)

### Changed
- **Improved Streamlit web UI**: Results now display at the top in a running commentary style
  - Most recent command and result appear at the top
  - Command history shows chronologically with newest entries first
  - Command input field moved to bottom for better workflow
  - Each command/result pair clearly separated with dividers
  - More intuitive interface similar to chat/terminal applications

## [0.1.19] - 2025-01-XX

### Fixed
- **Login base URL normalization**: Fixed login failure when base URL doesn't include `/++api++/`
  - Login function now normalizes base URL before attempting authentication
  - Fixes issue where users couldn't log in after upgrading from versions <= 0.1.16
  - Base URLs are now automatically normalized and saved for future use
  - Works with both old config files and new installations

## [0.1.18] - 2025-01-XX

### Added
- **Object rename commands**: New commands for renaming Plone objects
  - `rename <new_title> [path]` - Rename item title (update the title field)
  - `set-id <new_id> [path]` - Change item id/shortname/objectname (update the id field)
  - Both commands support optional path argument to target specific items
  - Both commands require confirmation (respect `-y` flag)
  - Path autocompletion works for both commands
- **Move command**: New `mv` command to move items between folders
  - `mv <source> <dest>` - Move item to new location
  - `mv <source> <dest-folder/new-name>` - Move and rename in one operation
  - Uses Plone REST API's `@move` endpoint
  - Requires confirmation (respects `-y` flag)
  - Path autocompletion for both source and destination

### Changed
- **Improved error messages**: Better error handling for `set-id` command
  - Clear syntax explanation when item not found (404 errors)
  - Helpful hints and examples for correct usage
  - Distinguishes between path errors and other API errors

## [0.1.17] - 2025-01-XX

### Added
- **Auto-confirm mode**: New `-y`/`--yes` flag for REPL to automatically answer "yes" to all confirmation prompts
  - Use `ploneapi-shell repl -y` to enable auto-confirm mode
  - All confirmation prompts default to "yes" (Y/n instead of y/N)
  - Makes batch operations much faster when you know you want to confirm everything
- **Plone 6 block manipulation**: New commands for managing blocks in Plone 6 content items
  - `blocks [path]` - List all blocks in an item with their order, type, and preview
  - `show-block <id|partial> [path]` - Show full details of a specific block (supports partial block IDs)
  - `delete-block <id|partial> [path]` - Delete a block from an item (supports partial block IDs, with confirmation)
  - `move-block <id|partial> <up|down|to <pos>> [path]` - Move blocks up, down, or to a specific position
  - Examples: `move-block abc123 up`, `move-block abc up my-item`, `move-block abc123 to 0` (move to first position)
  - All block commands support partial block IDs (e.g., `abc` matches `abc123xyz` if unique)
  - All block commands respect the `-y` flag for automatic confirmation
  - Path autocompletion works for all block commands
- **Path autocompletion for block commands**: Tab completion now works for paths in block commands
  - Type `blocks test-video <tab>` to autocomplete to `blocks test-video-playback`
  - Works with deep paths like `blocks files/myfolder/test <tab>`
  - Suggests items from the current directory or the directory being typed

### Changed
- **Confirmation prompts default to "yes"**: All `typer.confirm()` calls in REPL now default to `True` (Y/n instead of y/N)
  - Pressing Enter now confirms instead of canceling
  - More convenient for users who typically want to proceed with operations
  - Use `-y` flag for completely automatic confirmation
- **Improved block command usability**: Block commands now support partial block IDs
  - If multiple blocks match a partial ID, all matches are shown
  - If only one block matches, it's used automatically
  - Makes working with long block IDs much easier

## [0.1.15] - 2025-11-19

### Added
- **Search by object type**: New `search` command to find items by their portal_type
  - `search Document` - Find all Document items
  - `search Folder --path /some/path` - Find Folders in a specific path
  - Works in both CLI and REPL modes
  - Results displayed using the same format as `ls` command
  - Supports pagination for large result sets

### Changed
- **Improved `ls` output format**: Type information now integrated into the Title column
  - Removed separate "Type" column for more compact display
  - Format: `Title (id) [Type]` where title is bold, ID is dim, and type is cyan in brackets
  - Makes better use of horizontal space while maintaining all information

### Fixed
- **Enhanced tag rename verification**: Improved verification logic in `merge-tags` command
  - Now verifies that updates actually succeed (matches REPL behavior)
  - Better error reporting when updates fail silently
  - Fetches current item tags directly for more reliable updates
  - Added small delay before verification to allow server processing
- **Improved search pagination**: `search_by_subject` now handles pagination properly
  - Can find more than 25 items when searching by tag
  - Better handling of large result sets

## [0.1.14] - 2025-11-19

### Fixed
- **Tag rename verification**: Added verification to `merge-tags` command to detect failed updates
  - Verifies that old tags are removed and new tags are added
  - Better error messages explaining why updates failed
  - Improved tag fetching for more reliable updates

## [0.1.13] - 2025-11-19

### Fixed
- **`ls` command now shows Title and ID columns**: The `ls` command was missing the Title column and didn't display object IDs. Now shows both Title and ID (object name) columns, making it much easier to identify and distinguish items. The ID is extracted from the `id` field or derived from the `@id` URL path.

### Changed
- **Combined Title and ID into single column**: The `ls` command now displays title (bold) and ID (dim) in a single "Title (ID)" column for better space utilization, using color to distinguish between the two.
- **Enhanced tab completion for deep paths**: Tab completion now works for nested paths like `cd files/mystuff/<Tab>`, automatically fetching items from the specified directory and suggesting completions. This makes navigating deep folder structures much faster.

## [0.1.12] - 2025-11-19

### Added
- `connect` command inside the REPL to switch the active site without exiting. Accepts bare hosts, adds `http(s)://` as needed (prefers `http://` for localhost/IPs), and appends `/++api++/` automatically.
- Base URL normalization helpers that verify connectivity before saving, clear old tokens when switching sites, and ensure the config always points at the API root.

### Changed
- Quick Start and command docs now cover the `connect` workflow and note the auto-scheme/`++api++` behavior.

## [0.1.11] - 2025-11-19

### Added
- Automatic token renewal via `@login-renew` when saved JWTs near expiry, so REPL/CLI sessions keep working without manual `login`.

### Changed
- Updated Quick Start and command docs to highlight the new background refresh behavior.

## [0.1.10] - 2025-11-19

### Added
- Added `login` and `logout` commands directly to the REPL so you can refresh or clear credentials without leaving the shell.

### Changed
- Updated README Quick Start and command docs to make REPL-based authentication the preferred onboarding path.

## [0.1.9] - 2025-11-19

### Improved
- Clarified REPL help text to distinguish `exit`/`quit` (leave shell) from `logout` (clear saved credentials)
- Updated README command list so `logout` is documented alongside `exit`/`quit`, reducing onboarding confusion

## [0.1.8] - 2025-01-XX

### Fixed
- **Fixed `rename-tag` command**: Tag renaming now works correctly
  - Improved tag replacement logic to properly remove old tag and add new tag
  - Added verification to ensure updates actually succeed
  - Better error reporting when updates fail
  - Fixed case-sensitive tag matching issues

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

