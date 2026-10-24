from pathlib import Path
import os
import subprocess
from zipfile import ZipFile

import pytest

from scripts.package_deployment import package


def test_archive_excludes_credentials_before_reading_and_contains_deployment_files(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / "app").mkdir()
    (project / "app/main.py").write_text("print('synthetic app')")
    (project / "app/.env.local").write_text("PRIVATE_TEST_KEY=secret")
    (project / ".env").write_text("PRIVATE_TEST_KEY=secret")
    (project / "settings.local.json").write_text('{"api_key":"secret"}')
    (project / "settings.json").write_text('{"deepseek":{"api_key":""}}')
    (project / ".env.example").write_text("PAPERPRO_DEEPSEEK_API_KEY=")
    (project / "Dockerfile").write_text("FROM synthetic")
    (project / "compose.yaml").write_text("name: paperpro")
    (project / "output").mkdir()
    (project / "output/private-resume.txt").write_text("must never be read")
    original_read = Path.read_bytes

    def guarded_read(path):
        assert path.name not in {".env", ".env.local", "settings.local.json", "private-resume.txt"}
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    destination = tmp_path / "handoff.zip"
    result = package(project, destination)
    assert result["files"] == 5
    with ZipFile(destination) as archive:
        assert set(archive.namelist()) == {
            "app/main.py", "settings.json", ".env.example", "Dockerfile", "compose.yaml", "DELIVERY_MANIFEST.json",
        }
        assert b"PRIVATE_TEST_KEY" not in b"".join(archive.read(name) for name in archive.namelist())
        # Linux unzip honors these bits; Windows/Python extraction ignores them.
        assert all(info.create_system == 3 and info.external_attr >> 16 == 0o100644
                   for info in archive.infolist())


def test_public_template_with_real_value_is_not_packaged(tmp_path):
    (tmp_path / "settings.json").write_text('{"deepseek":{"api_key":"test-private-value"}}')
    destination = tmp_path / "handoff.zip"
    with pytest.raises(ValueError, match="credentials"):
        package(tmp_path, destination)
    assert not destination.exists()


def test_packager_does_not_overwrite_an_existing_archive(tmp_path):
    destination = tmp_path / "handoff.zip"
    destination.write_bytes(b"existing user artifact")
    with pytest.raises(FileExistsError):
        package(tmp_path, destination)
    assert destination.read_bytes() == b"existing user artifact"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction regression")
def test_windows_directory_junction_cannot_include_another_directory(tmp_path):
    root = tmp_path / "project"
    (root / "app").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private-note.txt").write_text("must not enter the archive")
    link = root / "app" / "linked-directory"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], check=True, capture_output=True)
    try:
        assert link.is_junction() and not link.is_symlink()
        with pytest.raises(ValueError, match="symlink"):
            package(root, tmp_path / "handoff.zip")
    finally:
        link.rmdir()  # Remove only the test junction, never its target.
    assert (outside / "private-note.txt").read_text() == "must not enter the archive"
