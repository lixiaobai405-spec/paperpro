"""Bounded, local LibreOffice conversions; never log document text or secrets."""
from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import threading
from zipfile import BadZipFile, ZipFile

import pymupdf

from .pdf_runtime import serialized_pdf


MAX_SOURCE_BYTES = 12 * 1024 * 1024
MAX_OUTPUT_BYTES = 48 * 1024 * 1024
MAX_DOCX_EXPANDED_BYTES = 48 * 1024 * 1024
CONVERSION_TIMEOUT_SECONDS = 45
QUEUE_TIMEOUT_SECONDS = 5
_conversion_slots = threading.BoundedSemaphore(2)

# LibreOffice officecfg Common.xcs and Writer.xcs: macros/active content off,
# no trusted locations, external link updates = 2 (Never). Headless alone does
# not disable macros. A fresh profile also prevents unrelated LO session reuse.
_PROFILE = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry">
 <item oor:path="/org.openoffice.Office.Common/Security/Scripting">
  <prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop>
  <prop oor:name="DisableActiveContent" oor:op="fuse"><value>true</value></prop>
  <prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>
  <prop oor:name="SecureURL" oor:op="fuse"><value/></prop>
  <prop oor:name="BlockUntrustedRefererLinks" oor:op="fuse"><value>true</value></prop>
 </item>
 <item oor:path="/org.openoffice.Office.Writer/Content/Update">
  <prop oor:name="Link" oor:op="fuse"><value>2</value></prop>
  <prop oor:name="Field" oor:op="fuse"><value>false</value></prop>
  <prop oor:name="Chart" oor:op="fuse"><value>false</value></prop>
 </item>
</oor:items>
"""


class ConversionError(ValueError):
    """A conversion failed without exposing document contents or OS details."""


class ConverterUnavailable(ConversionError):
    """LibreOffice is not installed in the current environment."""


def find_libreoffice() -> str | None:
    return shutil.which("libreoffice") or shutil.which("soffice")


def validate_docx(data: bytes) -> None:
    """Apply the same archive gate to uploaded and converted DOCX documents."""
    if not data.startswith(b"PK"):
        raise ConversionError("文件内容不是有效的 DOCX")
    try:
        with ZipFile(BytesIO(data)) as archive:
            records = archive.infolist()
            if (
                len(records) > 1000
                or sum(item.file_size for item in records) > MAX_DOCX_EXPANDED_BYTES
                or any(item.flag_bits & 1 for item in records)
            ):
                raise ConversionError("DOCX 解压内容超过安全限制或已加密，请先精简或另存文档")
            if not {"[Content_Types].xml", "word/document.xml"}.issubset(archive.namelist()):
                raise ConversionError("DOCX 缺少必要的 Word 文档内容")
    except (BadZipFile, OSError) as exc:
        raise ConversionError("DOCX 压缩结构无效") from exc


def _terminate_process(process: subprocess.Popen) -> None:
    try:
        if os.name == "posix":
            # Each conversion was started in its own session. Kill soffice.bin
            # and any children as well as the launcher, never other LO jobs.
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass
    process.wait()


def _run_conversion(command: list[str], environment: dict[str, str]) -> None:
    options = {"start_new_session": True} if os.name == "posix" else {
        "creationflags": subprocess.CREATE_NO_WINDOW,
    }
    try:
        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, shell=False, env=environment, **options,
        )
        try:
            returncode = process.wait(timeout=CONVERSION_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            _terminate_process(process)
            raise ConversionError("文档转换超时，请精简文档后重试") from exc
        if returncode != 0:
            raise ConversionError("LibreOffice 文档转换失败，请检查文档是否损坏或加密")
    except OSError as exc:
        raise ConversionError("无法启动文档转换程序，请检查 LibreOffice 安装") from exc


@serialized_pdf
def _validate_pdf(data: bytes) -> None:
    if not data.startswith(b"%PDF-"):
        raise ConversionError("转换程序未生成有效的 PDF")
    try:
        with pymupdf.open(stream=data, filetype="pdf") as document:
            if document.is_encrypted or not 1 <= document.page_count <= 256:
                raise ConversionError("转换生成的 PDF 已加密、为空或页数过多")
    except (RuntimeError, ValueError) as exc:
        raise ConversionError("转换程序未生成可读取的 PDF") from exc


def convert_document(data: bytes, source_format: str, target_format: str) -> bytes:
    if (source_format, target_format) not in {("doc", "docx"), ("docx", "pdf")}:
        raise ConversionError("不支持的文档转换格式")
    if not data or len(data) > MAX_SOURCE_BYTES:
        raise ConversionError("待转换文档大小无效，最多支持 12 MB")
    executable = find_libreoffice()
    if not executable:
        raise ConverterUnavailable("未安装 LibreOffice，无法转换此文档；请安装或将 DOC 另存为 DOCX")
    if not _conversion_slots.acquire(timeout=QUEUE_TIMEOUT_SECONDS):
        raise ConversionError("文档转换繁忙，请稍后重试")
    try:
        with tempfile.TemporaryDirectory(prefix="paperpro-office-") as folder:
            root = Path(folder)
            profile = root / "profile"
            profile_user = profile / "user"
            profile_user.mkdir(parents=True)
            (profile_user / "registrymodifications.xcu").write_text(_PROFILE, encoding="utf-8")
            output = root / "output"
            output.mkdir()
            source = root / ("input." + source_format)
            source.write_bytes(data)
            output_filter = "docx:Office Open XML Text" if target_format == "docx" else "pdf:writer_pdf_Export"
            command = [
                executable, "-env:UserInstallation=" + profile.resolve().as_uri(),
                "--headless", "--nologo", "--nodefault", "--norestore",
                "--convert-to", output_filter, "--outdir", str(output), str(source),
            ]
            # The office process does not need provider keys, proxy credentials,
            # or the caller's home/configuration directories.
            environment = {name: os.environ[name] for name in (
                "PATH", "LANG", "LC_ALL", "SYSTEMROOT", "WINDIR",
            ) if name in os.environ}
            environment.update({
                "HOME": str(root), "TMPDIR": str(root), "TMP": str(root),
                "TEMP": str(root), "XDG_CACHE_HOME": str(root / "cache"),
                "XDG_CONFIG_HOME": str(root / "config"), "SAL_USE_VCLPLUGIN": "svp",
            })
            _run_conversion(command, environment)
            destination = output / ("input." + target_format)
            if not destination.is_file() or destination.is_symlink():
                raise ConversionError("文档转换程序未生成预期文件")
            if not 0 < destination.stat().st_size <= MAX_OUTPUT_BYTES:
                raise ConversionError("转换结果大小无效或超过安全限制")
            result = destination.read_bytes()
            if target_format == "docx":
                validate_docx(result)
            else:
                _validate_pdf(result)
            return result
    finally:
        _conversion_slots.release()
