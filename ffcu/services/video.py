from dataclasses import dataclass
from urllib.parse import urlparse

from ffcu.config import Settings


class VideoAccessError(ValueError):
    pass


@dataclass(slots=True)
class VideoAccessService:
    settings: Settings

    def playback_url(
        self,
        video_source: str,
        duration_minutes: int,
    ) -> str:
        source = video_source.strip()
        if not source:
            return ""
        parsed = urlparse(source)
        if parsed.scheme != "https":
            raise VideoAccessError("Class videos must use an HTTPS YouTube URL.")
        host = (parsed.hostname or "").lower()
        if host not in {"youtu.be", "youtube.com", "www.youtube.com", "www.youtube-nocookie.com"}:
            raise VideoAccessError("Class videos must use an approved YouTube host.")
        return source
