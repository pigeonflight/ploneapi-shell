# PyPI Distribution Guide

This document outlines the process for distributing `ploneapi-shell` to PyPI.

## Prerequisites

1. **PyPI Account**: Ensure you have a PyPI account and API token
2. **Build Tools**: Install build and twine:
   ```bash
   pip install build twine
   ```

## Distribution Files

The following files are used for PyPI distribution:

- `pyproject.toml` - Main package configuration (dependencies, metadata, entry points)
- `setup.py` - Minimal setuptools setup (delegates to pyproject.toml)
- `MANIFEST.in` - Includes LICENSE and README.md in the distribution
- `fix_metadata.py` - Script to remove problematic metadata fields that PyPI rejects
- `LICENSE` - MIT License file (included via MANIFEST.in)
- `README.md` - Project documentation (included via MANIFEST.in)

## Building and Publishing

### Step 1: Build Distribution Packages

The `fix_metadata.py` script handles both building and fixing metadata issues:

```bash
# Build wheel + sdist and fix metadata automatically
python fix_metadata.py
```

This will:
- Run `python -m build` to create wheel and source distribution
- Remove problematic `license-file` and `license-expression` fields that PyPI rejects
- Output fixed packages to `dist/`

### Step 2: Verify Packages

Before uploading, verify the packages:

```bash
twine check dist/*
```

This checks for common issues and validates the package metadata.

### Step 3: Upload to PyPI

**Test PyPI (for testing):**
```bash
twine upload --repository testpypi dist/*
```

**Production PyPI:**
```bash
twine upload dist/*
```

You'll be prompted for your PyPI credentials (username and password/token).

## Version Management

Update the version in `pyproject.toml`:
```toml
version = "0.1.8"
```

Follow semantic versioning (MAJOR.MINOR.PATCH).

## Dependencies

All runtime dependencies are listed in `pyproject.toml` under `[project.dependencies]`:
- httpx>=0.27.0
- typer>=0.12.3
- rich>=13.7.1
- prompt-toolkit>=3.0.48
- streamlit>=1.28.0
- thefuzz>=0.19.0

## Entry Point

The CLI command is defined in `pyproject.toml`:
```toml
[project.scripts]
ploneapi-shell = "ploneapi_shell.cli:APP"
```

This makes `ploneapi-shell` available as a command after installation.

## Notes

- The `fix_metadata.py` script is necessary because setuptools adds metadata fields that PyPI rejects
- Always run `twine check` before uploading to catch issues early
- Test on Test PyPI first before publishing to production PyPI

