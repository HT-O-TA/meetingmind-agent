import io
import zipfile

import pytest

from app.services.input_admission import FileAdmissionError, InputAdmissionPolicy


def _ooxml(*names: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        for name in names:
            archive.writestr(name, "<root />")
    return output.getvalue()


def test_text_document_requires_matching_extension_mime_and_content():
    extension = InputAdmissionPolicy.validate_document(
        filename="meeting.txt",
        content_type="text/plain; charset=utf-8",
        content="会议决定周五发布。".encode(),
        allowed_extensions=["txt", "pdf"],
        maximum_size=1024,
    )
    assert extension == "txt"


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("photo.png", "image/png"),
        ("meeting.txt", "image/png"),
        ("clip.mp4", "video/mp4"),
        ("sensor.bin", "application/octet-stream"),
    ],
)
def test_images_video_sensor_and_disguised_mime_are_rejected(filename, content_type):
    with pytest.raises(FileAdmissionError):
        InputAdmissionPolicy.validate_document_metadata(
            filename,
            content_type,
            ["txt", "pdf", "docx", "md", "csv", "xlsx", "xlsm"],
        )


def test_document_signature_must_match_extension():
    with pytest.raises(FileAdmissionError, match="不是有效的 PDF"):
        InputAdmissionPolicy.validate_document(
            filename="fake.pdf",
            content_type="application/pdf",
            content=b"not a pdf",
            allowed_extensions=["pdf"],
            maximum_size=1024,
        )

    content = _ooxml("word/document.xml")
    assert InputAdmissionPolicy.validate_document(
        filename="meeting.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        content=content,
        allowed_extensions=["docx"],
        maximum_size=4096,
    ) == "docx"


def test_empty_and_oversized_documents_are_rejected():
    with pytest.raises(FileAdmissionError, match="不能为空"):
        InputAdmissionPolicy.validate_size(0, 10, label="文档")
    with pytest.raises(FileAdmissionError, match="超过大小限制"):
        InputAdmissionPolicy.validate_size(11, 10, label="文档")


def test_wav_rejects_generic_binary_mime_and_accepts_audio_mime():
    InputAdmissionPolicy.validate_wav_metadata(
        "meeting.wav", "audio/wav", ["wav"]
    )
    with pytest.raises(FileAdmissionError, match="Content-Type"):
        InputAdmissionPolicy.validate_wav_metadata(
            "meeting.wav", "application/octet-stream", ["wav"]
        )
