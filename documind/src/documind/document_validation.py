import io
import zipfile

MAX_DOCX_ARCHIVE_ENTRIES = 1000
MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024


def has_safe_docx_archive(
    content: bytes,
    max_uncompressed_bytes: int = MAX_DOCX_UNCOMPRESSED_BYTES,
) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            return (
                len(entries) <= MAX_DOCX_ARCHIVE_ENTRIES
                and sum(entry.file_size for entry in entries) <= max_uncompressed_bytes
                and any(entry.filename == "word/document.xml" for entry in entries)
            )
    except (OSError, zipfile.BadZipFile, ValueError):
        return False
