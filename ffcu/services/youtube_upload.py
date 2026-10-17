from __future__ import annotations

import hashlib
import json
import secrets
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
YOUTUBE_SCOPES = (YOUTUBE_UPLOAD_SCOPE, YOUTUBE_READONLY_SCOPE)
AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
YOUTUBE_UPLOAD_API = "https://www.googleapis.com/upload/youtube/v3/videos"


class YouTubeAuthError(RuntimeError):
    pass


class YouTubeUploadError(RuntimeError):
    pass


def _json_request(
    request: Request,
    *,
    timeout: int = 60,
    accepted_statuses: tuple[int, ...] = (200,),
) -> tuple[int, dict, dict[str, str]]:
    try:
        with urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            payload = response.read()
            headers = {key.lower(): value for key, value in response.headers.items()}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise YouTubeUploadError(f"YouTube returned HTTP {exc.code}: {detail[:1000]}") from exc
    except URLError as exc:
        raise YouTubeUploadError(f"YouTube network request failed: {exc.reason}") from exc
    if status not in accepted_statuses:
        raise YouTubeUploadError(f"Unexpected YouTube HTTP status {status}.")
    data = json.loads(payload.decode("utf-8")) if payload else {}
    return status, data, headers


@dataclass(slots=True)
class YouTubeTokenStore:
    path: Path

    def load(self) -> dict:
        if not self.path.is_file():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise YouTubeAuthError(f"Could not read the saved YouTube token: {exc}") from exc
        return value if isinstance(value, dict) else {}

    def save(self, value: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)


@dataclass(slots=True)
class YouTubeAuthService:
    client_secret_path: Path
    token_path: Path

    @property
    def configured(self) -> bool:
        return self.client_secret_path.is_file()

    def _client(self) -> dict:
        if not self.client_secret_path.is_file():
            raise YouTubeAuthError(
                f"YouTube client credential is missing: {self.client_secret_path}"
            )
        try:
            payload = json.loads(self.client_secret_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise YouTubeAuthError(f"Could not read the YouTube client credential: {exc}") from exc
        client = payload.get("installed") or payload.get("web")
        if not isinstance(client, dict) or not client.get("client_id") or not client.get("client_secret"):
            raise YouTubeAuthError("The YouTube client credential is not a valid OAuth client JSON file.")
        return client

    @staticmethod
    def _post_token(token_uri: str, parameters: dict[str, str]) -> dict:
        request = Request(
            token_uri,
            data=urlencode(parameters).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise YouTubeAuthError(f"Google OAuth returned HTTP {exc.code}: {detail[:1000]}") from exc
        except (URLError, json.JSONDecodeError) as exc:
            raise YouTubeAuthError(f"Google OAuth request failed: {exc}") from exc
        if not payload.get("access_token"):
            raise YouTubeAuthError("Google OAuth did not return an access token.")
        return payload

    def _save_token(self, response: dict, *, existing: dict | None = None) -> dict:
        existing = existing or {}
        token = {
            "access_token": response["access_token"],
            "refresh_token": response.get("refresh_token") or existing.get("refresh_token", ""),
            "token_type": response.get("token_type", "Bearer"),
            "scope": response.get("scope", " ".join(YOUTUBE_SCOPES)),
            "expires_at": int(time.time()) + int(response.get("expires_in", 3600)),
        }
        YouTubeTokenStore(self.token_path).save(token)
        return token

    def refresh(self, token: dict | None = None) -> dict:
        token = token or YouTubeTokenStore(self.token_path).load()
        refresh_token = str(token.get("refresh_token", ""))
        if not refresh_token:
            raise YouTubeAuthError("No saved YouTube refresh token exists; authorize the uploader first.")
        client = self._client()
        response = self._post_token(
            str(client.get("token_uri", "https://oauth2.googleapis.com/token")),
            {
                "client_id": str(client["client_id"]),
                "client_secret": str(client["client_secret"]),
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return self._save_token(response, existing=token)

    def access_token(self) -> str:
        token = YouTubeTokenStore(self.token_path).load()
        if token.get("access_token") and int(token.get("expires_at", 0)) > int(time.time()) + 90:
            return str(token["access_token"])
        return str(self.refresh(token)["access_token"])

    def authorization_url(self, redirect_uri: str, state: str) -> str:
        client = self._client()
        return AUTHORIZATION_ENDPOINT + "?" + urlencode(
            {
                "client_id": str(client["client_id"]),
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": " ".join(YOUTUBE_SCOPES),
                "access_type": "offline",
                "include_granted_scopes": "true",
                "prompt": "consent",
                "state": state,
            }
        )

    def authorize_interactive(
        self,
        *,
        open_browser: bool = True,
        timeout_seconds: int = 900,
        announce: Callable[[str], None] = print,
    ) -> dict:
        client = self._client()
        state = secrets.token_urlsafe(24)
        result: dict[str, str] = {}

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
                query = parse_qs(urlparse(self.path).query)
                if self.path.startswith("/favicon"):
                    self.send_response(204)
                    self.end_headers()
                    return
                if query.get("state", [""])[0] != state:
                    result["error"] = "OAuth state did not match."
                    status = 400
                    message = "Authorization could not be verified. Return to Codex and try again."
                elif query.get("error"):
                    result["error"] = query["error"][0]
                    status = 400
                    message = "Authorization was not granted. Return to Codex for help."
                else:
                    result["code"] = query.get("code", [""])[0]
                    status = 200
                    message = "Fortune & Finance YouTube authorization is complete. You may close this tab."
                body = f"<html><body><h2>{message}</h2></body></html>".encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        server = HTTPServer(("127.0.0.1", 0), CallbackHandler)
        server.timeout = 1
        redirect_uri = f"http://127.0.0.1:{server.server_port}/"
        url = self.authorization_url(redirect_uri, state)
        announce(f"AUTHORIZATION_URL={url}")
        if open_browser:
            webbrowser.open(url)
        deadline = time.monotonic() + timeout_seconds
        try:
            while not result and time.monotonic() < deadline:
                server.handle_request()
        finally:
            server.server_close()
        if result.get("error"):
            raise YouTubeAuthError(result["error"])
        code = result.get("code", "")
        if not code:
            raise YouTubeAuthError("Timed out waiting for Google authorization.")
        response = self._post_token(
            str(client.get("token_uri", "https://oauth2.googleapis.com/token")),
            {
                "code": code,
                "client_id": str(client["client_id"]),
                "client_secret": str(client["client_secret"]),
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        return self._save_token(response)


@dataclass(slots=True)
class YouTubeUploadResult:
    video_id: str
    url: str
    title: str
    requested_privacy: str
    actual_privacy: str
    size: int
    sha256: str


@dataclass(slots=True)
class YouTubeUploadService:
    auth: YouTubeAuthService
    chunk_size: int = 8 * 1024 * 1024

    def _authorized_json(self, url: str) -> dict:
        request = Request(url, headers={"Authorization": f"Bearer {self.auth.access_token()}"})
        _, payload, _ = _json_request(request)
        return payload

    def verify(self, video_id: str) -> dict:
        if not video_id:
            raise YouTubeUploadError("A YouTube video ID is required for verification.")
        query = urlencode({"part": "snippet,status", "id": video_id})
        payload = self._authorized_json(f"{YOUTUBE_API}/videos?{query}")
        items = payload.get("items", [])
        if len(items) != 1:
            raise YouTubeUploadError(f"YouTube video {video_id!r} was not found on the authorized channel.")
        return items[0]

    def recent_uploads(self, *, maximum: int = 50) -> list[dict]:
        query = urlencode(
            {
                "part": "snippet",
                "forMine": "true",
                "type": "video",
                "order": "date",
                "maxResults": str(max(1, min(50, maximum))),
            }
        )
        payload = self._authorized_json(f"{YOUTUBE_API}/search?{query}")
        return [item for item in payload.get("items", []) if item.get("id", {}).get("videoId")]

    def find_recent_by_title(self, title: str) -> dict | None:
        for item in self.recent_uploads():
            if str(item.get("snippet", {}).get("title", "")) == title:
                return self.verify(str(item["id"]["videoId"]))
        return None

    def upload(
        self,
        video_path: Path,
        *,
        title: str,
        description: str,
        privacy_status: str = "unlisted",
        progress: Callable[[int, int], None] | None = None,
    ) -> YouTubeUploadResult:
        if privacy_status not in {"private", "unlisted"}:
            raise YouTubeUploadError("Automated University uploads must be private or unlisted.")
        if not video_path.is_file():
            raise YouTubeUploadError(f"Video file not found: {video_path}")
        size = video_path.stat().st_size
        digest = hashlib.sha256()
        with video_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        body = json.dumps(
            {
                "snippet": {
                    "title": title[:100],
                    "description": description[:5000],
                    "categoryId": "27",
                    "defaultLanguage": "en",
                },
                "status": {
                    "privacyStatus": privacy_status,
                    "selfDeclaredMadeForKids": False,
                    "embeddable": True,
                },
            }
        ).encode("utf-8")
        query = urlencode(
            {"uploadType": "resumable", "part": "snippet,status", "notifySubscribers": "false"}
        )
        initiate = Request(
            f"{YOUTUBE_UPLOAD_API}?{query}",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.auth.access_token()}",
                "Content-Type": "application/json; charset=UTF-8",
                "Content-Length": str(len(body)),
                "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(size),
            },
        )
        try:
            with urlopen(initiate, timeout=60) as response:
                upload_url = response.headers.get("Location", "")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise YouTubeUploadError(f"Could not start YouTube upload (HTTP {exc.code}): {detail[:1000]}") from exc
        except URLError as exc:
            raise YouTubeUploadError(f"Could not start YouTube upload: {exc.reason}") from exc
        if not upload_url:
            raise YouTubeUploadError("YouTube did not return a resumable upload URL.")

        response_payload: dict = {}
        offset = 0
        with video_path.open("rb") as handle:
            while offset < size:
                handle.seek(offset)
                chunk = handle.read(min(self.chunk_size, size - offset))
                last = offset + len(chunk) - 1
                upload_request = Request(
                    upload_url,
                    data=chunk,
                    method="PUT",
                    headers={
                        "Authorization": f"Bearer {self.auth.access_token()}",
                        "Content-Type": "video/mp4",
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {offset}-{last}/{size}",
                    },
                )
                try:
                    with urlopen(upload_request, timeout=300) as response:
                        payload = response.read()
                        response_payload = json.loads(payload.decode("utf-8")) if payload else {}
                        offset = last + 1
                except HTTPError as exc:
                    if exc.code != 308:
                        detail = exc.read().decode("utf-8", errors="replace")
                        raise YouTubeUploadError(
                            f"YouTube upload failed at byte {offset} (HTTP {exc.code}): {detail[:1000]}"
                        ) from exc
                    received = exc.headers.get("Range", "")
                    if received.startswith("bytes=0-"):
                        offset = int(received.split("-")[-1]) + 1
                    else:
                        offset = last + 1
                except URLError as exc:
                    raise YouTubeUploadError(f"YouTube upload network failure at byte {offset}: {exc.reason}") from exc
                if progress:
                    progress(min(offset, size), size)

        video_id = str(response_payload.get("id", ""))
        if not video_id:
            raise YouTubeUploadError("YouTube completed the upload but did not return a video ID.")
        # A successful final response from the resumable session confirms that
        # YouTube accepted and created the remote video. A separate videos.list
        # call is intentionally deferred to receipt rechecks and release audits.
        actual_privacy = str(response_payload.get("status", {}).get("privacyStatus", ""))
        return YouTubeUploadResult(
            video_id=video_id,
            url=f"https://youtu.be/{video_id}",
            title=str(response_payload.get("snippet", {}).get("title", title)),
            requested_privacy=privacy_status,
            actual_privacy=actual_privacy,
            size=size,
            sha256=digest.hexdigest(),
        )
