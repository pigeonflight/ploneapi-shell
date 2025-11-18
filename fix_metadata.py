#!/usr/bin/env python3
"""Build artifacts and strip metadata fields that PyPI rejects."""
from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

REMOVED_LICENSE_FIELDS = ("Dynamic: license-file", "License-File:")


def fix_wheel(wheel_path: str) -> None:
    """Remove problematic license-file fields from wheel METADATA."""
    temp_dir = tempfile.mkdtemp()
    try:
        with zipfile.ZipFile(wheel_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)

        for root, _dirs, files in os.walk(temp_dir):
            if 'METADATA' in files:
                metadata_path = os.path.join(root, 'METADATA')
                with open(metadata_path, 'r', encoding='utf-8') as handle:
                    lines = handle.readlines()
                fixed_lines = [
                    line for line in lines if not line.startswith(REMOVED_LICENSE_FIELDS)
                ]
                with open(metadata_path, 'w', encoding='utf-8') as handle:
                    handle.writelines(fixed_lines)
                break

        os.remove(wheel_path)
        with zipfile.ZipFile(wheel_path, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
            for root, _dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arc_name = os.path.relpath(file_path, temp_dir)
                    zip_ref.write(file_path, arc_name)

        print(f'Fixed {wheel_path}')
    finally:
        shutil.rmtree(temp_dir)


def fix_sdist(sdist_path: str) -> None:
    """Remove problematic license-file fields from sdist PKG-INFO."""
    temp_dir = tempfile.mkdtemp()
    try:
        with tarfile.open(sdist_path, 'r:gz') as tar_ref:
            tar_ref.extractall(temp_dir)

        pkg_info_path = None
        for root, _dirs, files in os.walk(temp_dir):
            if 'PKG-INFO' in files:
                pkg_info_path = os.path.join(root, 'PKG-INFO')
                break

        if pkg_info_path and os.path.exists(pkg_info_path):
            with open(pkg_info_path, 'r', encoding='utf-8') as handle:
                lines = handle.readlines()
            fixed_lines = [
                line for line in lines if not line.startswith(REMOVED_LICENSE_FIELDS)
            ]
            with open(pkg_info_path, 'w', encoding='utf-8') as handle:
                handle.writelines(fixed_lines)

        os.remove(sdist_path)
        package_dir = None
        for item in os.listdir(temp_dir):
            item_path = os.path.join(temp_dir, item)
            if os.path.isdir(item_path) and item.startswith('ploneapi_shell-'):
                package_dir = item
                break

        if not package_dir:
            raise RuntimeError('Unable to locate extracted package directory')

        with tarfile.open(sdist_path, 'w:gz') as tar_ref:
            tar_ref.add(os.path.join(temp_dir, package_dir), arcname=package_dir)

        print(f'Fixed {sdist_path}')
    finally:
        shutil.rmtree(temp_dir)


def run_build(extra_args: list[str]) -> None:
    """Invoke `python -m build` with optional arguments."""
    cmd = [sys.executable, '-m', 'build', *extra_args]
    print('Running', ' '.join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Run `python -m build` and strip metadata fields PyPI rejects.',
        epilog='Pass extra args to the build command after `--`, e.g. '
               '`python fix_metadata.py -- --sdist`.',
    )
    parser.add_argument(
        '--skip-build',
        action='store_true',
        help='Only fix artifacts under dist/ (do not run `python -m build`).',
    )
    parser.add_argument(
        'build_args',
        nargs=argparse.REMAINDER,
        help='Arguments forwarded to `python -m build` (use `--` to separate).',
    )
    args = parser.parse_args()

    build_args = list(args.build_args)
    if build_args and build_args[0] == '--':
        build_args = build_args[1:]

    if args.skip_build and build_args:
        parser.error('Cannot supply build args when --skip-build is set.')

    if not args.skip_build:
        run_build(build_args)
    elif not os.path.isdir('dist'):
        parser.error('No dist/ directory found. Run without --skip-build first.')

    wheels = glob.glob('dist/*.whl')
    sdists = glob.glob('dist/*.tar.gz')

    if not wheels and not sdists:
        parser.error('No distribution files found in dist/.')

    for wheel in wheels:
        fix_wheel(wheel)
    for sdist in sdists:
        fix_sdist(sdist)

    print('All distributions fixed!')


if __name__ == '__main__':
    main()
