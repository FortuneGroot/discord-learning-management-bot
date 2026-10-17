from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest

from ffcu.services.youtube_upload import (
    YOUTUBE_READONLY_SCOPE,
    YOUTUBE_SCOPES,
    YOUTUBE_UPLOAD_SCOPE,
    YouTubeAuthError,
    YouTubeAuthService,
    YouTubeTokenStore,
    YouTubeUploadError,
    YouTubeUploadService,
)


def client_file(tmp_path):
    path = tmp_path / "client.json"
    path.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "client-id.apps.googleusercontent.com",
                    "client_secret": "private-client-secret",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def test_authorization_url_requests_only_required_video_access(tmp_path) -> None:
    auth = YouTubeAuthService(client_file(tmp_path), tmp_path / "token.json")
    url = auth.authorization_url("http://127.0.0.1:9999/", "state-value")
    query = parse_qs(urlparse(url).query)
    assert query["client_id"] == ["client-id.apps.googleusercontent.com"]
    assert set(query["scope"][0].split()) == set(YOUTUBE_SCOPES)
    assert YOUTUBE_UPLOAD_SCOPE in query["scope"][0]
    assert YOUTUBE_READONLY_SCOPE in query["scope"][0]
    assert query["access_type"] == ["offline"]
    assert query["state"] == ["state-value"]
    assert "private-client-secret" not in url


def test_token_store_round_trip_is_private_local_state(tmp_path) -> None:
    path = tmp_path / "youtube_token.json"
    store = YouTubeTokenStore(path)
    store.save({"access_token": "access", "refresh_token": "refresh", "expires_at": 123})
    assert store.load()["refresh_token"] == "refresh"
    assert path.parent == tmp_path


def test_missing_client_file_is_rejected(tmp_path) -> None:
    auth = YouTubeAuthService(tmp_path / "missing.json", tmp_path / "token.json")
    assert not auth.configured
    with pytest.raises(YouTubeAuthError, match="missing"):
        auth.authorization_url("http://127.0.0.1:9999/", "state")


def test_uploader_rejects_public_automation_and_missing_files(tmp_path) -> None:
    auth = YouTubeAuthService(client_file(tmp_path), tmp_path / "token.json")
    uploader = YouTubeUploadService(auth)
    with pytest.raises(YouTubeUploadError, match="private or unlisted"):
        uploader.upload(tmp_path / "video.mp4", title="Title", description="Description", privacy_status="public")
    with pytest.raises(YouTubeUploadError, match="not found"):
        uploader.upload(tmp_path / "video.mp4", title="Title", description="Description")
