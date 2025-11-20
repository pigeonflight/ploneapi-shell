from __future__ import annotations

import tarfile
import tempfile
import zipfile
from pathlib import Path

from setuptools import setup
from setuptools.command.sdist import sdist as _sdist

try:
    from wheel.bdist_wheel import bdist_wheel as _bdist_wheel
except ImportError:  # pragma: no cover
    _bdist_wheel = None


UNWANTED_PREFIXES = (
    "License-Expression:",
    "License-File:",
    "Dynamic: license-file",
)


def _strip_metadata(text: str) -> str:
    """Remove unwanted metadata lines."""
    return "\n".join(
        line for line in text.splitlines()
        if not any(line.startswith(prefix) for prefix in UNWANTED_PREFIXES)
    )


def _clean_wheel(path: Path) -> None:
    """Rewrite wheel METADATA without unwanted fields."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".whl") as tmp:
        tmp_path = Path(tmp.name)

    with zipfile.ZipFile(path, "r") as zin, zipfile.ZipFile(
        tmp_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.endswith("/METADATA"):
                data = _strip_metadata(data.decode("utf-8")).encode("utf-8")
            zout.writestr(item, data)

    tmp_path.replace(path)


def _clean_sdist(path: Path, project_dir_name: str) -> None:
    """Rewrite PKG-INFO files inside the source distribution archive."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        with tarfile.open(path, "r:gz") as tar:
            tar.extractall(tmpdir_path)

        for pkg_info in tmpdir_path.rglob("PKG-INFO"):
            pkg_info.write_text(_strip_metadata(pkg_info.read_text()))

        with tarfile.open(path, "w:gz") as tar:
            tar.add(tmpdir_path / project_dir_name, arcname=project_dir_name)


class CleanWheelCommand(_bdist_wheel):  # type: ignore[misc]
    """Custom wheel command that cleans metadata after build."""

    def run(self) -> None:
        super().run()
        if not self.dist_dir:
            return
        dist_dir = Path(self.dist_dir)
        safe_name = self.distribution.get_name().replace("-", "_")
        version = self.distribution.get_version()
        pattern = f"{safe_name}-{version}-*.whl"
        for wheel_path in dist_dir.glob(pattern):
            _clean_wheel(wheel_path)


class CleanSdistCommand(_sdist):
    """Custom sdist command that cleans metadata after build."""

    def run(self) -> None:
        super().run()
        if not self.dist_dir:
            return
        dist_dir = Path(self.dist_dir)
        safe_name = self.distribution.get_name().replace("-", "_")
        version = self.distribution.get_version()
        filename = dist_dir / f"{safe_name}-{version}.tar.gz"
        if filename.exists():
            project_dir_name = f"{safe_name}-{version}"
            _clean_sdist(filename, project_dir_name)


cmdclass = {"sdist": CleanSdistCommand}
if _bdist_wheel is not None:
    cmdclass["bdist_wheel"] = CleanWheelCommand

setup(cmdclass=cmdclass)

