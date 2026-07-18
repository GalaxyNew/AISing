from __future__ import annotations

import re
from dataclasses import dataclass


LRC_PATTERN = re.compile(r"\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?](.*)")


@dataclass(frozen=True)
class LyricLine:
    time_seconds: float | None
    text: str


def parse_lyrics(content: str) -> list[LyricLine]:
    lines: list[LyricLine] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = LRC_PATTERN.match(line)
        if match:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            fraction = match.group(3) or "0"
            milliseconds = int(fraction.ljust(3, "0")[:3])
            text = match.group(4).strip()
            lines.append(LyricLine(minutes * 60 + seconds + milliseconds / 1000.0, text))
        else:
            lines.append(LyricLine(None, line))
    return lines
