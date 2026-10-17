import pytest

from ffcu.config import Settings
from ffcu.services.video import VideoAccessError, VideoAccessService


def test_unlisted_youtube_short_url_is_supported() -> None:
    service = VideoAccessService(Settings())
    assert service.playback_url("https://youtu.be/abc123", 8) == "https://youtu.be/abc123"


def test_empty_video_is_unavailable() -> None:
    assert VideoAccessService(Settings()).playback_url("", 8) == ""


def test_non_youtube_https_host_is_rejected() -> None:
    service = VideoAccessService(Settings())
    with pytest.raises(VideoAccessError, match="approved YouTube host"):
        service.playback_url("https://video.example/lesson.mp4", 8)


def test_invalid_video_scheme_is_rejected() -> None:
    service = VideoAccessService(Settings())
    with pytest.raises(VideoAccessError, match="HTTPS YouTube"):
        service.playback_url("http://insecure.example/video.mp4", 8)
