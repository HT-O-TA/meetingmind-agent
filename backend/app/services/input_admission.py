"""文本、文档与 WAV 的严格输入准入策略。"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Iterable, Optional


DOCUMENT_MIME_TYPES: dict[str, set[str]] = {
    "txt": {"text/plain"},
    "md": {"text/markdown", "text/plain"},
    "pdf": {"application/pdf"},
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    },
    "csv": {"text/csv", "application/csv", "text/plain"},
    "xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    },
    "xlsm": {
        "application/vnd.ms-excel.sheet.macroenabled.12",
    },
}

WAV_MIME_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/vnd.wave",
}


class FileAdmissionError(ValueError):
    """文件名、声明类型或实际内容不满足正式入口契约。"""

    def __init__(self, message: str, status_code: int = 415) -> None:
        super().__init__(message)
        self.status_code = status_code


def _content_type(value: Optional[str]) -> str:
    return str(value or "").split(";", 1)[0].strip().lower()


def _extension(filename: str) -> str:
    return Path(filename or "").suffix.lower().lstrip(".")


def _allowed_extensions(values: Iterable[str]) -> set[str]:
    return {str(value).strip().lower().lstrip(".") for value in values if str(value).strip()}


class InputAdmissionPolicy:
    """只允许项目实际支持且能验证内容结构的输入。"""

    @staticmethod
    def validate_size(size: int, maximum: int, *, label: str) -> None:
        if size <= 0:
            raise FileAdmissionError(f"{label}不能为空", 422)
        if size > maximum:
            raise FileAdmissionError(f"{label}超过大小限制", 413)

    @classmethod
    def validate_document_metadata(
        cls,
        filename: str,
        content_type: Optional[str],
        allowed_extensions: Iterable[str],
    ) -> str:
        extension = _extension(filename)
        configured = _allowed_extensions(allowed_extensions)
        if extension not in configured or extension not in DOCUMENT_MIME_TYPES:
            supported = sorted(configured.intersection(DOCUMENT_MIME_TYPES))
            raise FileAdmissionError(
                f"不支持的文档扩展名: {extension or 'missing'}；允许: {', '.join(supported)}"
            )
        normalized_type = _content_type(content_type)
        if normalized_type not in DOCUMENT_MIME_TYPES[extension]:
            raise FileAdmissionError(
                f"文档 Content-Type 与扩展名不匹配: {normalized_type or 'missing'} / .{extension}"
            )
        return extension

    @staticmethod
    def validate_document_content(extension: str, content: bytes) -> None:
        if extension == "pdf":
            if not content.startswith(b"%PDF-"):
                raise FileAdmissionError("文件内容不是有效的 PDF", 422)
            return

        if extension in {"docx", "xlsx", "xlsm"}:
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    names = set(archive.namelist())
            except (zipfile.BadZipFile, OSError) as exc:
                raise FileAdmissionError("Office 文档不是有效的 OOXML ZIP", 422) from exc
            if "[Content_Types].xml" not in names:
                raise FileAdmissionError("Office 文档缺少 [Content_Types].xml", 422)
            required = "word/document.xml" if extension == "docx" else "xl/workbook.xml"
            if required not in names:
                raise FileAdmissionError(f"Office 文档内容与 .{extension} 扩展名不匹配", 422)
            return

        if extension in {"txt", "md", "csv"}:
            if b"\x00" in content:
                raise FileAdmissionError("文本类文档包含二进制 NUL 字节", 422)
            for encoding in ("utf-8-sig", "utf-8", "gb18030"):
                try:
                    content.decode(encoding)
                    return
                except UnicodeDecodeError:
                    continue
            raise FileAdmissionError("文本类文档无法按受支持编码解码", 422)

        raise FileAdmissionError(f"没有为 .{extension} 实现内容校验", 415)

    @classmethod
    def validate_document(
        cls,
        *,
        filename: str,
        content_type: Optional[str],
        content: bytes,
        allowed_extensions: Iterable[str],
        maximum_size: int,
    ) -> str:
        extension = cls.validate_document_metadata(
            filename, content_type, allowed_extensions
        )
        cls.validate_size(len(content), maximum_size, label="文档")
        cls.validate_document_content(extension, content)
        return extension

    @classmethod
    def validate_wav_metadata(
        cls,
        filename: str,
        content_type: Optional[str],
        allowed_extensions: Iterable[str],
    ) -> None:
        extension = _extension(filename)
        configured = _allowed_extensions(allowed_extensions)
        if extension != "wav" or extension not in configured:
            raise FileAdmissionError("正式 ASR 入口只接受 .wav", 415)
        normalized_type = _content_type(content_type)
        if normalized_type not in WAV_MIME_TYPES:
            raise FileAdmissionError(
                f"WAV Content-Type 不受支持: {normalized_type or 'missing'}", 415
            )


input_admission_policy = InputAdmissionPolicy()


__all__ = [
    "DOCUMENT_MIME_TYPES",
    "WAV_MIME_TYPES",
    "FileAdmissionError",
    "InputAdmissionPolicy",
    "input_admission_policy",
]
