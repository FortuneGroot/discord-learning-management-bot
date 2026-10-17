from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from ffcu.services.youtube_upload import (
    YouTubeAuthError,
    YouTubeAuthService,
    YouTubeUploadError,
    YouTubeUploadService,
)
from scripts.render_lesson_video import ROOT, render_lesson


RECEIPTS_PATH = ROOT / "video_output" / "upload_receipts.json"
VIDEO_URLS_PATH = ROOT / "content" / "video_urls.yaml"
COURSE_PATH = ROOT / "content" / "university.yaml"
DEFAULT_CLIENT_SECRET = ROOT / "secrets" / "youtube_client_secret.json"
DEFAULT_TOKEN = ROOT / "secrets" / "youtube_token.json"
WATCHABLE_PRIVACY = {"unlisted", "public"}


def code_key(code: str) -> tuple[int, int]:
    major, minor = code.split(".")
    return int(major), int(minor)


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def save_json(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def save_yaml(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=140),
        encoding="utf-8",
    )
    temporary.replace(path)


def update_video_release_metadata(code: str, receipt: dict) -> None:
    mapping = load_yaml(VIDEO_URLS_PATH)
    videos = mapping.setdefault("videos", {})
    privacy = str(receipt.get("privacy_status", ""))
    videos[code] = {
        "video_id": str(receipt.get("video_id", "")),
        "url": str(receipt.get("url", "")),
        "privacy_status": privacy,
        "title": str(receipt.get("title", "")),
        "verified_at": str(receipt.get("verified_at", "")),
    }
    save_yaml(mapping, VIDEO_URLS_PATH)

    course = load_yaml(COURSE_PATH)
    for level in course.get("levels", []):
        for lesson in level.get("lessons", []):
            if str(lesson.get("code")) != code:
                continue
            lesson["video_provider"] = "youtube_unlisted"
            lesson["video_url"] = str(receipt.get("url", "")) if privacy in WATCHABLE_PRIVACY else ""
            save_yaml(course, COURSE_PATH)
            return
    raise YouTubeUploadError(f"Lesson {code} was not found in the curriculum.")


def video_description(code: str, title: str) -> str:
    return (
        f"Fortune & Finance University — Lesson {code}: {title}\n\n"
        "Official member class for the Fortune & Finance Crypto University. "
        "Watch the complete lesson before taking the randomized Discord quiz.\n\n"
        "Education only. Nothing in this lesson is financial advice or a promise of profit. "
        "Protect passwords, private keys, and recovery phrases. Manage risk before capital.\n\n"
        "https://www.fortuneandfinance.com/"
    )


def upload_title(code: str, title: str) -> str:
    return f"FFCU Lesson {code} — {title}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Authorize, render, upload, verify, and clean Fortune & Finance lesson videos."
    )
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--all", action="store_true", help="Produce every lesson in curriculum order.")
    choice.add_argument("--lesson", action="append", help="Produce one lesson code; repeat for multiple lessons.")
    choice.add_argument("--authorize", action="store_true", help="Authorize the YouTube uploader and save a local refresh token.")
    choice.add_argument("--sync-only", action="store_true", help="Recheck uploaded videos and sync their latest privacy status.")
    parser.add_argument("--render-only", action="store_true", help="Render locally without uploading to YouTube.")
    parser.add_argument("--force", action="store_true", help="Regenerate existing scene media and the local MP4.")
    parser.add_argument(
        "--replace-upload",
        action="store_true",
        help="Create a replacement YouTube upload even when a verified receipt exists.",
    )
    parser.add_argument(
        "--recover-recent",
        action="store_true",
        help="Before rendering, recover an exact-title recent upload that is missing a local receipt.",
    )
    parser.add_argument(
        "--cloud-only",
        action="store_true",
        help="After verified upload, remove the work cache and local MP4.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Print the Google authorization URL instead of opening the default browser.",
    )
    args = parser.parse_args()

    client_secret = Path(os.getenv("YOUTUBE_CLIENT_SECRET_FILE", str(DEFAULT_CLIENT_SECRET)))
    token_path = Path(os.getenv("YOUTUBE_TOKEN_FILE", str(DEFAULT_TOKEN)))
    auth = YouTubeAuthService(client_secret, token_path)
    if args.authorize:
        auth.authorize_interactive(open_browser=not args.no_browser)
        print(f"YouTube authorization saved securely to {token_path}")
        return
    if not args.render_only and not auth.configured:
        parser.error(f"YouTube client credential is missing: {client_secret}")

    uploader = None if args.render_only else YouTubeUploadService(auth)
    receipts = load_json(RECEIPTS_PATH)
    available = {
        path.stem: path for path in (ROOT / "video_production" / "lessons").glob("*.yaml")
    }
    if args.sync_only:
        requested = sorted(receipts, key=code_key)
    else:
        requested = sorted(available, key=code_key) if args.all else list(dict.fromkeys(args.lesson or []))
    unknown = sorted(set(requested) - set(available), key=code_key)
    if unknown:
        parser.error(f"Unknown lesson configs: {', '.join(unknown)}")

    for index, code in enumerate(requested, start=1):
        receipt = receipts.get(code, {})
        video_id = str(receipt.get("video_id", ""))
        if args.render_only and video_id and not args.force:
            print(
                f"[{index}/{len(requested)}] Lesson {code} already has a YouTube receipt; skipped local render",
                flush=True,
            )
            continue
        if uploader and not video_id and args.recover_recent and not args.replace_upload:
            config = load_yaml(available[code])
            title = str(config.get("title", f"Lesson {code}"))
            remote = uploader.find_recent_by_title(upload_title(code, title))
            if remote:
                video_id = str(remote["id"])
                receipt = {
                    "video_id": video_id,
                    "url": f"https://youtu.be/{video_id}",
                    "source": f"https://youtu.be/{video_id}",
                    "title": str(remote.get("snippet", {}).get("title", "")),
                    "requested_privacy": "unlisted",
                    "privacy_status": str(remote.get("status", {}).get("privacyStatus", "")),
                    "size": 0,
                    "sha256": "",
                    "verified_at": datetime.now(timezone.utc).isoformat(),
                    "recovered": True,
                }
                receipts[code] = receipt
                save_json(receipts, RECEIPTS_PATH)
                update_video_release_metadata(code, receipt)
                print(
                    f"[{index}/{len(requested)}] Recovered Lesson {code} from recent YouTube uploads; "
                    f"privacy={receipt['privacy_status']}",
                    flush=True,
                )
                continue
        if uploader and video_id and not args.replace_upload:
            try:
                remote = uploader.verify(video_id)
            except Exception as exc:
                if args.sync_only:
                    print(f"[{index}/{len(requested)}] Lesson {code} verification failed: {exc}", flush=True)
                    continue
                print(f"[{index}/{len(requested)}] Lesson {code} receipt failed verification; uploading again: {exc}", flush=True)
            else:
                receipt["title"] = str(remote.get("snippet", {}).get("title", receipt.get("title", "")))
                receipt["privacy_status"] = str(remote.get("status", {}).get("privacyStatus", ""))
                receipt["verified_at"] = datetime.now(timezone.utc).isoformat()
                receipts[code] = receipt
                save_json(receipts, RECEIPTS_PATH)
                update_video_release_metadata(code, receipt)
                print(
                    f"[{index}/{len(requested)}] Lesson {code} verified on YouTube; "
                    f"privacy={receipt['privacy_status']}",
                    flush=True,
                )
                continue
        if args.sync_only:
            print(f"[{index}/{len(requested)}] Lesson {code} has no YouTube receipt; skipped", flush=True)
            continue

        print(f"[{index}/{len(requested)}] Rendering Lesson {code}", flush=True)
        final_video = render_lesson(available[code], force=args.force)
        if uploader:
            config = load_yaml(available[code])
            title = str(config.get("title", f"Lesson {code}"))

            def report_progress(done: int, total: int) -> None:
                percent = round((done / max(1, total)) * 100)
                print(f"Lesson {code} YouTube upload: {percent}%", flush=True)

            try:
                result = uploader.upload(
                    final_video,
                    title=upload_title(code, title),
                    description=video_description(code, title),
                    privacy_status="unlisted",
                    progress=report_progress,
                )
            except (YouTubeAuthError, YouTubeUploadError) as exc:
                raise SystemExit(f"Lesson {code} YouTube upload failed: {exc}") from exc
            receipt = {
                "video_id": result.video_id,
                "url": result.url,
                "source": result.url,
                "title": result.title,
                "requested_privacy": result.requested_privacy,
                "privacy_status": result.actual_privacy,
                "size": result.size,
                "sha256": result.sha256,
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }
            receipts[code] = receipt
            save_json(receipts, RECEIPTS_PATH)
            update_video_release_metadata(code, receipt)
            print(
                f"Verified YouTube upload: {result.url} ({result.size} bytes, privacy={result.actual_privacy})",
                flush=True,
            )
            work = final_video.parent / "work"
            if work.is_dir():
                shutil.rmtree(work)
            if args.cloud_only and final_video.is_file():
                final_video.unlink()
            print(f"Cleanup complete for Lesson {code}; cloud_only={args.cloud_only}", flush=True)


if __name__ == "__main__":
    main()
