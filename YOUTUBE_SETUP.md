# YouTube Video Production and Upload

Fortune & Finance University stores class videos on the business YouTube account as **Unlisted**. Students receive the watch button only after the Discord bot confirms the paid Student role.

## Security model

- Unlisted videos do not appear in YouTube search, recommendations, or the public Videos tab.
- The Discord bot keeps the normal watch flow inside paid membership.
- Unlisted links are not DRM. A student can copy a link. If strict per-viewer protection is later required, migrate to a paid authenticated video host.
- Never place `secrets/youtube_client_secret.json` or `secrets/youtube_token.json` in Discord, source control, the handoff ZIP, or the bot server.

## One-time authorization

The Google Cloud project needs YouTube Data API v3, a Desktop OAuth client, the business Google account as a test user, and these two scopes:

```text
https://www.googleapis.com/auth/youtube.upload
https://www.googleapis.com/auth/youtube.readonly
```

Place the downloaded desktop client file at `secrets/youtube_client_secret.json`, then run:

```bat
.venv\Scripts\python.exe scripts\produce_all_videos.py --authorize
```

Google may show an unverified-app warning because this is a private testing app. Only the invited Fortune & Finance account should authorize it. The final `127.0.0.1` page is the local success callback; the terminal confirms when the token is saved.

## Produce all lessons with low disk use

```bat
.venv\Scripts\python.exe scripts\produce_all_videos.py --all --cloud-only
```

For every lesson, the command renders the AI-voice class, uploads it as Unlisted, records a receipt, verifies the remote video, updates `content/video_urls.yaml`, and removes the local MP4 after confirmation. Restarting the same command safely skips verified receipts.

Useful recovery commands:

```bat
.venv\Scripts\python.exe scripts\produce_all_videos.py --sync-only
.venv\Scripts\python.exe scripts\produce_all_videos.py --lesson 0.1 --recover-recent
```

`--sync-only` rechecks every receipt and refreshes privacy status. `--recover-recent` locates an exact-title upload created before its receipt was saved, preventing a duplicate.

## Final release

After every lesson video verifies as Unlisted:

```bat
.venv\Scripts\python.exe scripts\produce_all_videos.py --sync-only
.venv\Scripts\python.exe scripts\validate_content.py
seed_course.bat
.venv\Scripts\python.exe -m pytest -q
```

The production deployment also runs a private release audit and handoff packager that are not part of this public demo.
