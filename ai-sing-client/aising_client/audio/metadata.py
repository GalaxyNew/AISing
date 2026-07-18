from pathlib import Path
from typing import Any

try:
    from mutagen import File as MutagenFile
except ImportError:  # pragma: no cover - only used when optional dependency is missing.
    MutagenFile = None


def audio_title_or_filename(path: Path) -> str:
    title = audio_title(path)
    return title or path.stem


def audio_title(path: Path) -> str:
    if MutagenFile is None:
        return ""
    try:
        audio = MutagenFile(path, easy=True)
    except Exception:
        return ""
    if not audio:
        return ""
    return clean_title(read_tag(audio, "title"))


def read_tag(audio: Any, name: str) -> Any:
    try:
        return audio.get(name)
    except AttributeError:
        return None


def clean_title(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = next((item for item in value if str(item).strip()), "")
    text = str(value).strip()
    return text
