"""Build an allowlisted source handoff ZIP, excluding credentials before reads."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT_FILES = {
    "README.md", "SPEC.md", "pyproject.toml", "uv.lock", "settings.json",
    "Dockerfile", "compose.yaml", ".dockerignore", ".env.example", ".gitignore",
    "start-paperpro.cmd",
}
FRONTEND_FILES = {"package.json", "package-lock.json", "index.html", "vite.config.js", "playwright.config.js"}
SOURCE_TREES = ("app", "scripts", "tests", "docs", "frontend/src", "frontend/public", "frontend/e2e", "frontend/tests")
SOURCE_SUFFIXES = {".py", ".md", ".json", ".js", ".jsx", ".mjs", ".css", ".svg", ".html", ".txt", ".yaml", ".yml"}
EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    "artifacts", "output", "dist", "build", "test-results", "playwright-report",
    "evaluation_private", "credentials", "secrets", ".ssh", ".aws", ".docker",
}


def _allowed_name(path: Path) -> bool:
    lower = path.name.lower()
    return not (
        (lower.startswith(".env") and lower != ".env.example")
        or lower == "settings.local.json"
        or lower in {"credentials.json", "credentials.txt", "secrets.json", "secrets.yaml", "secrets.yml",
                     "token.txt", "tokens.json", "auth.json", "pip.conf", ".npmrc"}
        or lower.endswith((".pem", ".key", ".p12", ".pfx", ".pyc", ".log"))
    )


def _ensure_no_links(root: Path, path: Path) -> None:
    for item in [path, *path.parents]:
        if item == root:
            break
        # Windows directory junctions are reparse points, not symbolic links.
        if item.is_symlink() or item.is_junction():
            raise ValueError(f"Refusing a source symlink/junction: {item.name}")


def _walk_source(directory: Path):
    for path in sorted(directory.iterdir()):
        if not _allowed_name(path) or path.name.lower() in EXCLUDED_DIRS:
            continue  # Never resolve, traverse or read excluded credential paths.
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"Refusing a source symlink: {path.name}")
        if path.is_dir():
            yield from _walk_source(path)
        elif path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES:
            yield path


def source_files(root: Path) -> list[Path]:
    paths = []
    for name in sorted(ROOT_FILES):
        path = root / name
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"Refusing a root symlink: {name}")
        if path.is_file():
            paths.append(path)
    for name in sorted(FRONTEND_FILES):
        path = root / "frontend" / name
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"Refusing a frontend symlink: {name}")
        if path.is_file():
            paths.append(path)
    for relative in SOURCE_TREES:
        folder = root / relative
        # Check each ancestor before iterating so a symlinked frontend/src
        # cannot silently package another project or the user's home folder.
        for parent in [folder, *folder.parents]:
            if parent == root:
                break
            if parent.is_symlink() or parent.is_junction():
                raise ValueError(f"Refusing a source directory symlink: {relative}")
        if folder.is_dir():
            paths.extend(_walk_source(folder))
    return sorted(set(paths), key=lambda path: path.relative_to(root).as_posix())


def _check_public_settings(root: Path) -> None:
    path = root / "settings.json"
    if path.is_symlink() or path.is_junction():
        raise ValueError("Public settings must not be a symlink")
    if not path.exists():
        return
    document = json.loads(path.read_text(encoding="utf-8-sig"))

    def check(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower() in {"api_key", "token", "password", "secret", "access_token", "client_secret", "private_key"} and child:
                    raise ValueError("Public settings contain credentials; clear them before packaging")
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    check(document)


def _write_public_source(archive: ZipFile, name: str, content: bytes | str) -> None:
    # writestr defaults to mode 0600, which Linux unzip preserves. The image's
    # unprivileged process must be able to read COPY'd public source files.
    entry = ZipInfo(name)
    entry.create_system = 3
    entry.external_attr = 0o100644 << 16
    entry.compress_type = ZIP_DEFLATED
    archive.writestr(entry, content)


def package(root: Path, destination: Path) -> dict:
    root = root.resolve()
    if destination.exists():
        raise FileExistsError("Archive already exists; choose another --output path")
    _check_public_settings(root)
    files = source_files(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest = []
    with ZipFile(destination, "x", ZIP_DEFLATED) as archive:
        for path in files:
            # Recheck before reading in case the source changed during packing.
            _ensure_no_links(root, path)
            content = path.read_bytes()
            name = path.relative_to(root).as_posix()
            _write_public_source(archive, name, content)
            manifest.append({"path": name, "sha256": sha256(content).hexdigest(), "bytes": len(content)})
        _write_public_source(archive, "DELIVERY_MANIFEST.json", json.dumps({"files": manifest}, ensure_ascii=False, indent=2))
    return {"archive": str(destination.resolve()), "files": len(files), "bytes": destination.stat().st_size,
            "sha256": sha256(destination.read_bytes()).hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("output/delivery/paperpro-linux-deployment.zip"))
    args = parser.parse_args()
    print(json.dumps(package(args.root, args.output), ensure_ascii=False, indent=2))
