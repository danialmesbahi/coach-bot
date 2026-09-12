from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

SAFE_UPLOAD_TYPES = {
    ".jpg": ("image/jpeg", "image"), ".jpeg": ("image/jpeg", "image"),
    ".png": ("image/png", "image"), ".webp": ("image/webp", "image"),
    ".gif": ("image/gif", "animation"), ".mp4": ("video/mp4", "video"),
    ".mp3": ("audio/mpeg", "audio"), ".m4a": ("audio/mp4", "audio"),
    ".ogg": ("audio/ogg", "voice"), ".wav": ("audio/wav", "audio"),
    ".pdf": ("application/pdf", "document"),
}
# Keep the allow-list explicit: these formats are downloaded, never executed in-page.
SAFE_UPLOAD_TYPES.update({
    ".doc": ("application/msword", "document"),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "document"),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "document"),
    ".zip": ("application/zip", "document"), ".txt": ("text/plain", "document"),
})


def _inspect_upload(filename: str, payload: bytes) -> tuple[str, str] | None:
    """Validate the extension and the actual bytes before Telegram or a browser sees them."""
    suffix = Path(filename).suffix.lower()
    declared = SAFE_UPLOAD_TYPES.get(suffix)
    if not declared or not payload:
        return None
    mime, kind = declared
    valid = {
        ".jpg": payload.startswith(b"\xff\xd8\xff"), ".jpeg": payload.startswith(b"\xff\xd8\xff"),
        ".png": payload.startswith(b"\x89PNG\r\n\x1a\n"),
        ".webp": payload.startswith(b"RIFF") and payload[8:12] == b"WEBP",
        ".gif": payload.startswith((b"GIF87a", b"GIF89a")),
        ".mp4": len(payload) > 11 and payload[4:8] == b"ftyp",
        ".m4a": len(payload) > 11 and payload[4:8] == b"ftyp",
        ".mp3": payload.startswith(b"ID3") or (len(payload) > 1 and payload[0] == 0xFF and payload[1] & 0xE0 == 0xE0),
        ".ogg": payload.startswith(b"OggS"),
        ".wav": payload.startswith(b"RIFF") and payload[8:12] == b"WAVE",
        ".pdf": payload.startswith(b"%PDF-"),
        ".doc": payload.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),
        ".zip": payload.startswith(b"PK\x03\x04"),
    }.get(suffix)
    if suffix in {".docx", ".xlsx"}:
        try:
            with ZipFile(BytesIO(payload)) as archive:
                names = set(archive.namelist())
                valid = len(names) <= 1000 and "[Content_Types].xml" in names and (
                    "word/document.xml" in names if suffix == ".docx" else "xl/workbook.xml" in names
                )
        except (BadZipFile, OSError):
            valid = False
    elif suffix == ".txt":
        try:
            payload.decode("utf-8")
            valid = b"\x00" not in payload
        except UnicodeDecodeError:
            valid = False
    return (mime, kind) if valid else None


def _sniff_download(filename: str, payload: bytes, fallback_type: str) -> tuple[str, str]:
    inspected = _inspect_upload(filename, payload)
    if inspected:
        return inspected
    # Old Telegram rows have no filename. Reuse the trusted message kind with a synthetic extension.
    extension = {
        "image/jpeg":".jpg", "video/mp4":".mp4", "audio/ogg":".ogg", "audio/mpeg":".mp3",
    }.get(fallback_type)
    return (_inspect_upload(f"media{extension}", payload) if extension else None) or ("application/octet-stream", "document")


class BoundedBuffer(BytesIO):
    """Reject oversized streams even when upstream metadata is missing or false."""
    def __init__(self, limit: int):
        super().__init__()
        self.limit = limit

    def write(self, data):
        if self.tell() + len(data) > self.limit:
            raise ValueError("media exceeds byte limit")
        return super().write(data)
