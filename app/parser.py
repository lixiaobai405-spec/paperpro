from __future__ import annotations

from functools import lru_cache
from io import BytesIO
import logging
import os
from pathlib import Path
import re
import tempfile
from zipfile import BadZipFile, ZipFile

import pymupdf
from docx import Document
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import Education, Entry, Resume


MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_PDF_PAGES = 25
MAX_IMAGE_PIXELS = 22_000_000

SECTION_LABELS = {
    "summary": [
        "个人简介", "个人介绍", "个人优势", "自我评价", "职业概述", "个人概况",
        "profile", "summary", "professional summary", "professional profile",
        "about me", "objective", "career objective",
    ],
    "skills": [
        "技能", "技能专长", "专业技能", "核心技能", "技术技能", "技术栈",
        "skills", "technical skills", "core skills", "core competencies", "technologies",
    ],
    "experience": [
        "工作经历", "工作经验", "实习经历", "实习经验", "职业经历",
        "work experience", "professional experience", "employment history",
        "experience", "internships", "internship experience",
    ],
    "education": [
        "教育背景", "教育经历", "学历", "教育情况",
        "education", "academic background", "educational background",
    ],
    "projects": [
        "项目经历", "项目经验", "相关项目", "个人项目",
        "projects", "project experience", "selected projects", "project work",
    ],
    "additional": [
        "其他经历", "其他信息", "补充信息", "奖励荣誉", "获奖情况", "证书", "资格证书",
        "荣誉", "语言能力", "其他", "additional information", "certifications",
        "certificates", "awards", "honors", "languages", "other", "activities",
    ],
}
EMAIL = re.compile(r"[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}")
CN_PHONE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
INTL_PHONE = re.compile(r"(?<!\w)\+?\d[\d()\s-]{7,}\d")
WEB = re.compile(r"(?:https?://|www\.|github\.com/|linkedin\.com/)\S+", re.I)
DATE = re.compile(r"(?:19|20)\d{2}(?:[./-](?:0?[1-9]|1[012]))?")
BULLET = re.compile(r"^\s*(?:[-*•●▪◦·]\s+|[（(]?\d{1,2}[)）]\s*|\d{1,2}\.\s+|\d{1,2}、\s*)")
TITLE = re.compile(r"^(?:求职意向|应聘岗位|目标岗位|期望职位|目标职位|position sought|target role)\s*[:：]\s*(.+)$", re.I)
LOCATION = re.compile(r"^(?:所在地|所在城市|居住地|location|city)\s*[:：]\s*(.+)$", re.I)
LABEL_PREFIX = re.compile(r"^\s*(?:[■□●•*#]+\s*|[一二三四五六七八九]+[、.]\s*)")


def _norm(value: str) -> str:
    # OCR may separate the domain and top-level suffix (e.g. example. invalid).
    # Only repair an email-shaped token, never arbitrary periods in prose.
    if "@" in value:
        value = re.sub(
            r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.)\s+([A-Za-z]{2,})\b",
            r"\1\2", value,
        )
    return re.sub(r"[\t \u00a0]+", " ", value).strip()


def _section(line: str) -> str | None:
    label = LABEL_PREFIX.sub("", _norm(line))
    label = label.strip(" :：·—_-|【】[]")
    # OCR commonly merges a short multi-word section label such as
    # "Work Experience" into "WorkExperience". Exact whitelist only.
    compact = re.sub(r"\s+", "", label).casefold()
    for group, candidates in SECTION_LABELS.items():
        if label.casefold() in candidates or compact in {
            re.sub(r"\s+", "", candidate).casefold() for candidate in candidates
        }:
            return group
    return None


def _uniq(lines: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in lines if item))


def _entry_group(lines: list[str]) -> list[Entry]:
    items: list[Entry] = []
    current: Entry | None = None
    for line in lines:
        clean = BULLET.sub("", line).strip()
        if not clean:
            continue
        start_entry = (
            current is None
            or (not BULLET.match(line) and bool(DATE.search(clean))
                and bool(current.bullets or DATE.search(current.heading)))
        )
        if start_entry:
            current = Entry(heading=clean)
            items.append(current)
        elif current is not None:
            current.bullets.append(clean)
    return items


def _education_group(lines: list[str]) -> list[Education]:
    entries: list[Education] = []
    for line in lines:
        clean = BULLET.sub("", line).strip()
        if not clean:
            continue
        if not entries or (
            (DATE.search(clean) or re.search(r"大学|学院|university|college", clean, re.I))
            and not BULLET.match(line)
        ):
            entries.append(Education(heading=clean))
        else:
            entries[-1].details.append(clean)
    return entries


def parse_resume(text: str) -> Resume:
    lines = [_norm(line) for line in text.replace("\r\n", "\n").replace("\r", "\n").splitlines()]
    lines = [line for line in lines if line]
    result = Resume()
    if not lines:
        return result

    parts: dict[str, list[str]] = {key: [] for key in [*SECTION_LABELS, "header"]}
    active = "header"
    for line in lines:
        new_section = _section(line)
        if new_section:
            active = new_section
            continue
        parts[active].append(line)

    header = parts["header"]
    # Preserve all text that cannot safely be classified.
    for index, line in enumerate(header):
        if index == 0 and len(line) <= 70 and not EMAIL.search(line) and not CN_PHONE.search(line):
            result.name = re.split(r"[\s|丨｜·•]", line, maxsplit=1)[0] if re.search(r"[\u4e00-\u9fff]", line) else line.split(" | ")[0]
            if len(result.name) > 45:
                result.name = line[:45]
            if result.name != line and len(line) > len(result.name):
                remainder = line[len(result.name):].strip(" |丨｜·•")
                if remainder:
                    result.additional.append(remainder)
            continue
        title = TITLE.match(line)
        loc = LOCATION.match(line)
        if title:
            result.title = title.group(1)
            continue
        if loc:
            result.location = loc.group(1)
            continue
        email = EMAIL.search(line)
        phone = CN_PHONE.search(line) or INTL_PHONE.search(line)
        if email:
            if not result.email:
                result.email = email.group()
            elif result.email != email.group():
                result.additional.append(email.group())
        if phone:
            if not result.phone:
                result.phone = phone.group().strip()
            elif result.phone != phone.group().strip():
                result.additional.append(phone.group().strip())
        links = WEB.findall(line)
        result.links.extend(links)
        remainder = line
        if email:
            remainder = remainder.replace(email.group(), "")
        if phone:
            remainder = remainder.replace(phone.group(), "")
        for link in links:
            remainder = remainder.replace(link, "")
        remainder = remainder.strip(" :：|丨｜·•,，;；/")
        if remainder:
            if not result.title and (len(remainder) < 48 and re.search(r"工程师|经理|设计师|开发|analyst|engineer|manager|designer", remainder, re.I)):
                result.title = remainder
            else:
                result.additional.append(remainder)

    result.summary = "\n".join(parts["summary"])
    for line in parts["skills"]:
        # Treat common separators as skill delimiters without losing the original words.
        for item in re.split(r"[，,、;；|丨•·]|\s{2,}", line):
            clean = BULLET.sub("", item).strip()
            if clean:
                result.skills.append(clean)
    result.skills = _uniq(result.skills)
    result.experience = _entry_group(parts["experience"])
    result.projects = _entry_group(parts["projects"])
    result.education = _education_group(parts["education"])
    result.additional.extend(BULLET.sub("", line).strip() for line in parts["additional"])
    result.additional = _uniq(result.additional)
    result.links = _uniq(result.links)
    return result


@lru_cache(maxsize=1)
def _ocr_engine():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR()


def _ocr_image(image: Image.Image) -> str:
    import numpy as np
    image = ImageOps.exif_transpose(image)
    if image.width * image.height > MAX_IMAGE_PIXELS:
        raise ValueError("图片分辨率过高，最多支持 2200 万像素")
    rgb = image.convert("RGB")
    try:
        results, _ = _ocr_engine()(np.asarray(rgb))
        lines = [str(item[1]).strip() for item in (results or []) if len(item) >= 2]
        if lines:
            return "\n".join(lines)
    except Exception:
        pass
    try:
        import pytesseract
        path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.name == "nt" and Path(path).exists():
            pytesseract.pytesseract.tesseract_cmd = path
        return pytesseract.image_to_string(rgb, lang="eng").strip()
    except Exception as exc:
        raise ValueError(f"OCR 识别失败：{exc}") from exc


def _docx_text(data: bytes) -> tuple[str, list[str], bool]:
    doc = Document(BytesIO(data))

    def walk(container) -> list[str]:
        lines: list[str] = []
        for item in container.iter_inner_content():
            if hasattr(item, "rows"):
                for row in item.rows:
                    # Recurse: cell.text omits tables nested inside a table cell.
                    cells = [" / ".join(walk(cell)) for cell in row.cells]
                    value = " | ".join(cell for cell in cells if cell)
                    if value:
                        lines.append(value)
            else:
                if item.text.strip():
                    lines.append(item.text.strip())
                # python-docx skips floating and inline Word text boxes.
                for para in item._p.xpath(".//w:txbxContent//w:p"):
                    # CT_P.text follows the Word run model and preserves w:br,
                    # w:cr and w:tab. Concatenating w:t silently merges numbers.
                    if para.text.strip():
                        lines.append(para.text.strip())
        return lines

    body = walk(doc)
    headers: list[str] = []
    footers: list[str] = []
    parts = [doc.part]
    for section in doc.sections:
        headers.extend(walk(section.header))
        footers.extend(walk(section.footer))
        parts.extend([section.header.part, section.footer.part])
    headers = list(dict.fromkeys(headers))
    footers = list(dict.fromkeys(footers))
    # Preserve the first body line (usually the name) before header contacts.
    ordered = (body[:1] + headers + body[1:] + footers) if body else (headers + footers)

    images: list[str] = []
    warnings: list[str] = []
    seen = set()
    image_parts = []
    for part in parts:
        for related in part.related_parts.values():
            if not related.content_type.startswith("image/"):
                continue
            if related.partname in seen:
                continue
            seen.add(related.partname)
            image_parts.append(related)
    if len(image_parts) > 12:
        raise ValueError("DOCX 内嵌图片过多，最多支持 12 张")
    for part in image_parts:
        if len(part.blob) > 8 * 1024 * 1024:
            raise ValueError("DOCX 内嵌图片过大，无法安全识别")
        try:
            picture = Image.open(BytesIO(part.blob))
            words = _ocr_image(picture).strip()
        except (OSError, ValueError) as error:
            warnings.append(f"Word 图片可能存在遗漏，请人工核对：{type(error).__name__}")
            continue
        if words:
            images.append(words)
        else:
            warnings.append("Word 内嵌图片未识别到文字，请核对图片内容")
    if images:
        # OCR text is unclassified evidence, not an automatic employer claim.
        ordered.extend(["其他信息", *images])
        warnings.append("Word 内嵌图片已通过 OCR 提取到其他信息，请对照原件核实")
    return "\n".join(ordered), warnings, bool(image_parts)


def _doc_text(data: bytes) -> str:
    if os.name != "nt":
        raise ValueError("旧版 .doc 需要 Windows 上的 Microsoft Word。请另存为 .docx。")
    import pythoncom
    import win32com.client
    with tempfile.TemporaryDirectory(prefix="paperpro-doc-") as tmp:
        source = Path(tmp) / "input.doc"
        source.write_bytes(data)
        pythoncom.CoInitialize()
        word = None
        doc = None
        try:
            word = win32com.client.DispatchEx("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0
            word.AutomationSecurity = 3
            doc = word.Documents.Open(str(source), ReadOnly=True, AddToRecentFiles=False, ConfirmConversions=False)
            return doc.Content.Text.replace("\r", "\n").strip()
        except Exception as exc:
            raise ValueError(f"读取 .doc 失败，请尝试在 Word 中另存为 .docx：{exc}") from exc
        finally:
            try:
                if doc is not None:
                    try:
                        doc.Close(SaveChanges=False)
                    except Exception as error:
                        logging.warning("Legacy Word document cleanup failed: %s", type(error).__name__)
                if word is not None:
                    try:
                        word.Quit()
                    except Exception as error:
                        logging.warning("Legacy Word application cleanup failed: %s", type(error).__name__)
            finally:
                pythoncom.CoUninitialize()


def extract_file(filename: str, data: bytes) -> tuple[str, list[str], str]:
    if not data:
        raise ValueError("文件为空")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("文件超过 12 MB 限制")
    extension = Path(filename).suffix.lower()
    warnings: list[str] = []
    if extension == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise ValueError("文件内容不是有效的 PDF")
        try:
            pdf = pymupdf.open(stream=data, filetype="pdf")
            if pdf.is_encrypted:
                raise ValueError("加密 PDF 无法读取，请先解锁文件")
            if pdf.page_count > MAX_PDF_PAGES:
                raise ValueError("PDF 最多支持 25 页")
            text: list[str] = []
            scanned = False
            for page in pdf:
                native = page.get_text("text", sort=True).strip()
                if native:
                    text.append(native)
                # Mixed pages often contain a selectable heading and a scanned
                # image with the actual experience. OCR substantial image regions.
                sizable_image = False
                for meta in page.get_images(full=True):
                    for rect in page.get_image_rects(meta[0]):
                        if rect.get_area() >= page.rect.get_area() * 0.06:
                            sizable_image = True
                            break
                    if sizable_image:
                        break
                if len(re.sub(r"\s", "", native)) < 12 or sizable_image:
                    if page.rect.width * page.rect.height * 4 > MAX_IMAGE_PIXELS:
                        raise ValueError("PDF 页面尺寸过大，无法安全地进行 OCR")
                    scanned = True
                    raster = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
                    image = Image.open(BytesIO(raster.tobytes("png")))
                    recognized = _ocr_image(image).strip()
                    known = {re.sub(r"\s+", "", line).lower()
                             for line in native.splitlines() if line.strip()}
                    unique_lines = [
                        line.strip() for line in recognized.splitlines()
                        if line.strip() and re.sub(r"\s+", "", line).lower() not in known
                    ]
                    if unique_lines:
                        text.append("\n".join(unique_lines))
            if scanned:
                warnings.append("部分或全部 PDF 页面经过 OCR 识别，请检查文字是否有误")
            content = "\n".join(text).strip()
            method = "pdf+ocr" if scanned else "pdf-text"
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"PDF 无法解析：{exc}") from exc
    elif extension == ".docx":
        if not data.startswith(b"PK"):
            raise ValueError("文件内容不是有效的 DOCX")
        try:
            with ZipFile(BytesIO(data)) as compressed:
                records = compressed.infolist()
                if len(records) > 1000 or sum(record.file_size for record in records) > 48 * 1024 * 1024:
                    raise ValueError("DOCX 解压内容超过安全限制，请先精简或压缩图片")
            content, docx_warnings, has_image = _docx_text(data)
            warnings.extend(docx_warnings)
        except Exception as exc:
            raise ValueError(f"DOCX 无法解析：{exc}") from exc
        method = "docx+ocr" if has_image else "docx"
    elif extension == ".doc":
        if not data.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
            raise ValueError("文件内容不是有效的旧版 DOC")
        content = _doc_text(data)
        method = "word-doc"
    elif extension in {".png", ".jpg", ".jpeg"}:
        try:
            image = Image.open(BytesIO(data))
            expected = {"PNG"} if extension == ".png" else {"JPEG"}
            if image.format not in expected:
                raise ValueError("图片格式与文件后缀不一致")
            content = _ocr_image(image)
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError(f"图片无法读取：{exc}") from exc
        method = "image-ocr"
        warnings.append("扫描图片经过 OCR 识别，请逐项核对姓名、数字和日期")
    else:
        raise TypeError("仅支持 PDF、DOCX、DOC、PNG、JPG、JPEG 文件")

    if not content or len(re.sub(r"\s", "", content)) < 3:
        raise ValueError("未识别到有效文字，请使用清晰扫描件或可复制文字的文档")
    return content, warnings, method
