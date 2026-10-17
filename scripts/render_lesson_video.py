from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import edge_tts
import imageio_ffmpeg
import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
WIDTH = 1920
HEIGHT = 1080
FPS = 24

NAVY = "#06152E"
NAVY_2 = "#0D2547"
GOLD = "#C3923F"
GOLD_LIGHT = "#E1C07B"
IVORY = "#F7F1E5"
PAPER = "#FFFDF8"
INK = "#10233E"
MUTED = "#607087"
WHITE = "#FFFFFF"


@dataclass
class SceneMedia:
    scene_id: str
    title: str
    narration: str
    frame_path: Path
    audio_path: Path
    clip_path: Path
    voice_duration: float
    clip_duration: float


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def font_path(*candidates: str) -> Path | None:
    directories = [
        Path("C:/Windows/Fonts"),
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/usr/share/fonts/truetype/liberation2"),
    ]
    for directory in directories:
        for candidate in candidates:
            path = directory / candidate
            if path.exists():
                return path
    return None


SERIF_REGULAR = font_path("georgia.ttf", "DejaVuSerif.ttf", "LiberationSerif-Regular.ttf")
SERIF_BOLD = font_path("georgiab.ttf", "DejaVuSerif-Bold.ttf", "LiberationSerif-Bold.ttf")
SANS_REGULAR = font_path("segoeui.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf")
SANS_BOLD = font_path("segoeuib.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf")


def get_font(path: Path | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if path:
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def draw_vertical_gradient(image: Image.Image, top: str, bottom: str) -> None:
    top_rgb = tuple(int(top[i : i + 2], 16) for i in (1, 3, 5))
    bottom_rgb = tuple(int(bottom[i : i + 2], 16) for i in (1, 3, 5))
    draw = ImageDraw.Draw(image)
    for y in range(HEIGHT):
        ratio = y / max(HEIGHT - 1, 1)
        color = tuple(round(a + (b - a) * ratio) for a, b in zip(top_rgb, bottom_rgb))
        draw.line((0, y, WIDTH, y), fill=color)


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> float:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        trial = " ".join(current + [word])
        if current and text_width(draw, trial, font) > max_width:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
    max_width: int,
    spacing: int = 12,
) -> int:
    x, y = xy
    lines = wrap_text(draw, text, font, max_width)
    line_height = draw.textbbox((0, 0), "Ag", font=font)[3] + spacing
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height
    return y


def rounded_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    fill: str = PAPER,
    outline: str = "#D9C59E",
    width: int = 3,
    radius: int = 30,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def load_logo() -> Image.Image:
    path = ROOT / "assets" / "fortune_finance_logo.jpg"
    logo = Image.open(path).convert("RGB")
    logo.thumbnail((760, 760), Image.Resampling.LANCZOS)
    return logo


def paste_logo(image: Image.Image, logo: Image.Image, box: tuple[int, int, int, int]) -> None:
    x1, y1, x2, y2 = box
    size = min(x2 - x1, y2 - y1)
    resized = logo.copy()
    resized.thumbnail((size, size), Image.Resampling.LANCZOS)
    plate = Image.new("RGB", (size + 16, size + 16), GOLD)
    plate.paste(resized, (8, 8))
    image.paste(plate, (x1, y1))


def draw_base(scene: dict, lesson: dict, logo: Image.Image) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), IVORY)
    draw_vertical_gradient(image, "#FFFDF8", "#F2E9D8")
    draw = ImageDraw.Draw(image)

    for x in range(70, WIDTH - 70, 80):
        draw.line((x, 0, x + 420, HEIGHT), fill="#EEE3D1", width=1)
    draw.rectangle((0, 0, WIDTH, 22), fill=NAVY)
    draw.rectangle((0, 22, WIDTH, 30), fill=GOLD)
    draw.rectangle((0, HEIGHT - 18, WIDTH, HEIGHT), fill=NAVY)

    paste_logo(image, logo, (72, 58, 190, 176))
    draw.text((220, 72), "FORTUNE & FINANCE", font=get_font(SERIF_BOLD, 34), fill=NAVY)
    draw.text((222, 118), "UNIVERSITY", font=get_font(SANS_BOLD, 20), fill=GOLD)
    draw.text((1545, 80), f"LESSON {lesson['lesson_code']}", font=get_font(SANS_BOLD, 24), fill=NAVY)
    draw.text((1545, 118), lesson["level"].upper(), font=get_font(SANS_REGULAR, 18), fill=MUTED)
    draw.line((70, 202, WIDTH - 70, 202), fill=GOLD, width=3)

    eyebrow = scene.get("eyebrow", "").upper()
    draw.text((96, 242), eyebrow, font=get_font(SANS_BOLD, 24), fill=GOLD)
    y = draw_wrapped(
        draw,
        (92, 286),
        scene["headline"],
        get_font(SERIF_BOLD, 70),
        NAVY,
        1540,
        spacing=8,
    )
    draw_wrapped(
        draw,
        (96, y + 14),
        scene.get("subhead", ""),
        get_font(SANS_REGULAR, 31),
        MUTED,
        1540,
        spacing=8,
    )
    draw.text(
        (96, HEIGHT - 70),
        "Education first · Risk management always",
        font=get_font(SANS_REGULAR, 21),
        fill=MUTED,
    )
    draw.text(
        (WIDTH - 470, HEIGHT - 70),
        "fortuneandfinance.com",
        font=get_font(SANS_BOLD, 21),
        fill=NAVY,
    )
    return image, draw


def visual_content(scene: dict) -> dict:
    content = scene.get("visual_content") or {}
    return content if isinstance(content, dict) else {}


def draw_title_visual(image: Image.Image, draw: ImageDraw.ImageDraw, logo: Image.Image, scene: dict, closing: bool = False) -> None:
    x1, y1, x2, y2 = (720, 495, 1200, 975)
    paste_logo(image, logo, (x1, y1, x2, y2))
    draw.rounded_rectangle((565, 855, 1355, 935), radius=40, fill=NAVY, outline=GOLD, width=3)
    default = "CONTINUE TO THE QUIZ" if closing else "START THE LESSON"
    label = str(visual_content(scene).get("badge", default)).upper()
    font = get_font(SANS_BOLD, 28)
    width = text_width(draw, label, font)
    draw.text(((WIDTH - width) / 2, 879), label, font=font, fill=GOLD_LIGHT)


def draw_definition(draw: ImageDraw.ImageDraw, scene: dict) -> None:
    centers = [(585, 750), (960, 700), (1335, 750)]
    default = [["IDEA ONE", "First key point"], ["IDEA TWO", "Second key point"], ["IDEA THREE", "Third key point"]]
    labels = visual_content(scene).get("items", default)
    for (cx, cy), (title, body) in zip(centers, labels):
        title = str(title).upper()
        draw.ellipse((cx - 185, cy - 165, cx + 185, cy + 165), fill="#FDF8ED", outline=GOLD, width=6)
        title_font = get_font(SANS_BOLD, 25 if len(title) <= 10 else 21)
        width = text_width(draw, title, title_font)
        draw.text((cx - width / 2, cy - 48), title, font=title_font, fill=NAVY)
        for index, line in enumerate(str(body).splitlines()):
            body_font = get_font(SANS_REGULAR, 21)
            line_width = text_width(draw, line, body_font)
            draw.text((cx - line_width / 2, cy + index * 30), line, font=body_font, fill=MUTED)


def draw_comparison(draw: ImageDraw.ImageDraw, scene: dict) -> None:
    default = [
        {"title": "OPTION A", "bullets": ["First characteristic", "Second characteristic", "Third characteristic"]},
        {"title": "OPTION B", "bullets": ["First characteristic", "Second characteristic", "Third characteristic"]},
    ]
    cards = visual_content(scene).get("cards", default)
    for box, card in zip([(180, 555, 890, 925), (1030, 555, 1740, 925)], cards):
        rounded_card(draw, box, fill=PAPER, outline=GOLD, width=4)
        draw.rectangle((box[0], box[1], box[2], box[1] + 82), fill=NAVY)
        draw.text((box[0] + 34, box[1] + 25), str(card["title"]).upper(), font=get_font(SANS_BOLD, 25), fill=GOLD_LIGHT)
        y = box[1] + 130
        for bullet in card.get("bullets", [])[:3]:
            draw.ellipse((box[0] + 42, y + 8, box[0] + 58, y + 24), fill=GOLD)
            draw.text((box[0] + 78, y), str(bullet), font=get_font(SANS_REGULAR, 25), fill=INK)
            y += 78


def draw_ledger(draw: ImageDraw.ImageDraw, scene: dict) -> None:
    content = visual_content(scene)
    y = 690
    for index in range(5):
        x = 190 + index * 320
        rounded_card(draw, (x, y - 105, x + 245, y + 105), fill=NAVY, outline=GOLD, width=5, radius=24)
        draw.text((x + 28, y - 66), f"STEP {index + 1}", font=get_font(SANS_BOLD, 24), fill=GOLD_LIGHT)
        draw.text((x + 28, y - 17), str(content.get("line_one", "input")), font=get_font(SANS_REGULAR, 21), fill=WHITE)
        draw.text((x + 28, y + 23), str(content.get("line_two", "result")), font=get_font(SANS_REGULAR, 21), fill="#C8D5E5")
        if index < 4:
            draw.line((x + 245, y, x + 320, y), fill=GOLD, width=8)
            draw.polygon([(x + 310, y - 12), (x + 330, y), (x + 310, y + 12)], fill=GOLD)
    draw.text((260, 860), str(content.get("caption", "Each step builds on the one before it")), font=get_font(SERIF_REGULAR, 32), fill=NAVY)


def draw_balance(draw: ImageDraw.ImageDraw, scene: dict) -> None:
    default = [["BENEFIT", "Why it helps"], ["COST", "What to watch"]]
    sides = visual_content(scene).get("sides", default)
    draw.line((960, 600, 960, 885), fill=NAVY, width=14)
    draw.line((650, 635, 1270, 635), fill=GOLD, width=14)
    draw.ellipse((910, 585, 1010, 685), fill=NAVY, outline=GOLD, width=5)
    for cx, (label, body) in zip((650, 1270), sides):
        label = str(label).upper()
        draw.line((cx, 635, cx - 125, 810), fill=NAVY, width=5)
        draw.line((cx, 635, cx + 125, 810), fill=NAVY, width=5)
        draw.arc((cx - 170, 745, cx + 170, 925), 0, 180, fill=GOLD, width=10)
        font = get_font(SANS_BOLD, 27)
        width = text_width(draw, label, font)
        draw.text((cx - width / 2, 775), label, font=font, fill=NAVY)
        body_font = get_font(SANS_REGULAR, 21)
        body_width = text_width(draw, str(body), body_font)
        draw.text((cx - body_width / 2, 825), str(body), font=body_font, fill=MUTED)
    draw.polygon([(900, 920), (1020, 920), (1080, 965), (840, 965)], fill=NAVY)


def draw_volatility(draw: ImageDraw.ImageDraw, scene: dict) -> None:
    content = visual_content(scene)
    rounded_card(draw, (190, 545, 1730, 925), fill=PAPER, outline=GOLD, width=4)
    for y in range(615, 890, 70):
        draw.line((260, y, 1650, y), fill="#E4DDCF", width=2)
    for x in range(280, 1650, 150):
        draw.line((x, 590, x, 890), fill="#EEE7DA", width=2)
    points = [(280, 815), (400, 720), (520, 760), (650, 610), (780, 670), (910, 585), (1040, 790), (1180, 735), (1320, 865), (1460, 690), (1620, 755)]
    draw.line(points, fill=NAVY, width=12, joint="curve")
    for x, y in points:
        draw.ellipse((x - 12, y - 12, x + 12, y + 12), fill=GOLD, outline=NAVY, width=3)
    draw.text((255, 874), str(content.get("caption", "Values change over time")), font=get_font(SANS_BOLD, 26), fill=NAVY)
    draw.rounded_rectangle((1270, 585, 1645, 650), radius=30, fill=NAVY)
    draw.text((1315, 601), str(content.get("badge", "KEY POINT")).upper(), font=get_font(SANS_BOLD, 23), fill=GOLD_LIGHT)


def draw_lock(draw: ImageDraw.ImageDraw, cx: int, cy: int) -> None:
    draw.arc((cx - 90, cy - 150, cx + 90, cy + 45), 180, 360, fill=GOLD, width=24)
    draw.rounded_rectangle((cx - 145, cy - 55, cx + 145, cy + 185), radius=30, fill=NAVY, outline=GOLD, width=6)
    draw.ellipse((cx - 28, cy + 30, cx + 28, cy + 86), fill=GOLD_LIGHT)
    draw.rectangle((cx - 13, cy + 72, cx + 13, cy + 132), fill=GOLD_LIGHT)


def draw_custody(draw: ImageDraw.ImageDraw, scene: dict) -> None:
    draw_lock(draw, 960, 710)
    default = [
        {"title": "DO", "bullets": ["Safe practice one", "Safe practice two", "Safe practice three"]},
        {"title": "AVOID", "bullets": ["Risky habit one", "Risky habit two", "Risky habit three"]},
    ]
    items = visual_content(scene).get("cards", default)
    for box, item in zip([(180, 590, 650, 905), (1270, 590, 1740, 905)], items):
        rounded_card(draw, box, fill=PAPER, outline=GOLD, width=4)
        draw.text((box[0] + 35, box[1] + 35), str(item["title"]).upper(), font=get_font(SANS_BOLD, 27), fill=NAVY)
        y = box[1] + 105
        for bullet in item.get("bullets", [])[:3]:
            draw.text((box[0] + 38, y), "•", font=get_font(SANS_BOLD, 26), fill=GOLD)
            draw.text((box[0] + 72, y), str(bullet), font=get_font(SANS_REGULAR, 23), fill=INK)
            y += 65


def draw_framework(draw: ImageDraw.ImageDraw, scene: dict) -> None:
    default = [["STEP ONE", "First action"], ["STEP TWO", "Second action"], ["STEP THREE", "Third action"], ["STEP FOUR", "Fourth action"]]
    steps = visual_content(scene).get("steps", default)
    for index, (title, body) in enumerate(steps[:4]):
        number = str(index + 1)
        title = str(title).upper()
        x = 125 + index * 440
        rounded_card(draw, (x, 585, x + 370, 900), fill=PAPER, outline=GOLD, width=4)
        draw.ellipse((x + 128, 620, x + 242, 734), fill=NAVY, outline=GOLD, width=5)
        number_font = get_font(SERIF_BOLD, 48)
        number_width = text_width(draw, number, number_font)
        draw.text((x + 185 - number_width / 2, 640), number, font=number_font, fill=GOLD_LIGHT)
        title_font = get_font(SANS_BOLD, 26)
        title_width = text_width(draw, title, title_font)
        draw.text((x + 185 - title_width / 2, 765), title, font=title_font, fill=NAVY)
        body_font = get_font(SANS_REGULAR, 21)
        body_width = text_width(draw, str(body), body_font)
        draw.text((x + 185 - body_width / 2, 820), str(body), font=body_font, fill=MUTED)


def draw_recap(draw: ImageDraw.ImageDraw, scene: dict, lesson: dict) -> None:
    default = [item["headline"] for item in lesson.get("scenes", []) if item.get("visual") not in {"title", "closing", "recap"}]
    labels = visual_content(scene).get("points", default)[:6]
    for index, label in enumerate(labels):
        col = index % 3
        row = index // 3
        x = 150 + col * 560
        y = 560 + row * 175
        rounded_card(draw, (x, y, x + 500, y + 135), fill=PAPER, outline=GOLD, width=3)
        draw.text((x + 28, y + 32), f"{index + 1:02d}", font=get_font(SERIF_BOLD, 43), fill=GOLD)
        draw.text((x + 112, y + 49), str(label).upper(), font=get_font(SANS_BOLD, 23), fill=NAVY)


def render_scene_frame(scene: dict, lesson: dict, logo: Image.Image, output_path: Path) -> None:
    image, draw = draw_base(scene, lesson, logo)
    visual = scene.get("visual", "")
    if visual == "closing":
        draw_title_visual(image, draw, logo, scene, closing=True)
    elif visual == "recap":
        draw_recap(draw, scene, lesson)
    elif visual in VISUALS:
        VISUALS[visual](draw, scene)
    else:
        draw_title_visual(image, draw, logo, scene)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, quality=96)


VISUALS = {
    "definition": draw_definition,
    "comparison": draw_comparison,
    "ledger": draw_ledger,
    "balance": draw_balance,
    "volatility": draw_volatility,
    "custody": draw_custody,
    "framework": draw_framework,
}


async def neural_speech(text: str, output_path: Path, voice: dict) -> None:
    communicate = edge_tts.Communicate(
        text=text,
        voice=voice["name"],
        rate=voice.get("rate", "+0%"),
        pitch=voice.get("pitch", "+0Hz"),
    )
    await communicate.save(str(output_path))


def windows_speech(text: str, output_path: Path) -> None:
    text_path = output_path.with_suffix(".txt")
    wav_path = output_path.with_suffix(".wav")
    text_path.write_text(text, encoding="utf-8")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.SelectVoice('Microsoft Mark'); $s.Rate = -1; "
        f"$t = Get-Content -Raw -LiteralPath '{text_path}'; "
        f"$s.SetOutputToWaveFile('{wav_path}'); $s.Speak($t); $s.Dispose();"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)
    text_path.unlink(missing_ok=True)


def synthesize(text: str, output_path: Path, voice: dict, force: bool = False) -> Path:
    cached_candidates = (output_path, output_path.with_suffix(".wav"))
    if not force:
        for candidate in cached_candidates:
            if not candidate.exists():
                continue
            try:
                media_duration(candidate)
            except RuntimeError:
                candidate.unlink(missing_ok=True)
            else:
                return candidate
    try:
        asyncio.run(neural_speech(text, output_path, voice))
        media_duration(output_path)
        return output_path
    except Exception as exc:
        print(f"Neural voice failed ({exc}); using the local AI voice fallback.", file=sys.stderr)
        output_path.unlink(missing_ok=True)
        windows_speech(text, output_path)
        fallback = output_path.with_suffix(".wav")
        media_duration(fallback)
        return fallback


def run_ffmpeg(arguments: list[str], *, allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", *arguments]
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode and not allow_failure:
        raise RuntimeError(f"FFmpeg failed:\n{result.stderr}")
    return result


def media_duration(path: Path) -> float:
    result = run_ffmpeg(["-i", str(path)], allow_failure=True)
    match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
    if not match:
        raise RuntimeError(f"Could not determine media duration for {path}")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def render_clip(frame: Path, audio: Path, output: Path, voice_duration: float, pad: float = 0.55) -> float:
    duration = voice_duration + pad
    frames = max(1, math.ceil(duration * FPS))
    fade_out = max(0.0, duration - 0.35)
    video_filter = (
        f"zoompan=z='min(zoom+0.00018,1.035)':"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS},"
        f"fade=t=in:st=0:d=0.30,fade=t=out:st={fade_out:.3f}:d=0.30,format=yuv420p"
    )
    audio_filter = f"apad=pad_dur={pad:.3f},afade=t=in:st=0:d=0.15,afade=t=out:st={fade_out:.3f}:d=0.30"
    run_ffmpeg(
        [
            "-y",
            "-i",
            str(frame),
            "-i",
            str(audio),
            "-vf",
            video_filter,
            "-af",
            audio_filter,
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "19",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    return duration


def sentence_chunks(text: str, max_words: int = 13) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: list[str] = []
    for sentence in sentences:
        words = sentence.split()
        while len(words) > max_words:
            split_at = max_words
            for index in range(max_words, max(5, max_words - 5), -1):
                if words[index - 1].endswith((",", ";", ":")):
                    split_at = index
                    break
            chunks.append(" ".join(words[:split_at]))
            words = words[split_at:]
        if words:
            chunks.append(" ".join(words))
    return chunks


def srt_timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def build_captions(media: list[SceneMedia], output_path: Path) -> None:
    entries: list[tuple[float, float, str]] = []
    scene_start = 0.0
    for scene in media:
        chunks = sentence_chunks(scene.narration)
        weights = [max(1, len(chunk.split())) for chunk in chunks]
        total_weight = sum(weights)
        cursor = scene_start + 0.10
        available = max(0.5, scene.voice_duration - 0.20)
        for chunk, weight in zip(chunks, weights):
            duration = available * weight / total_weight
            entries.append((cursor, cursor + duration, chunk))
            cursor += duration
        scene_start += scene.clip_duration

    lines: list[str] = []
    for index, (start, end, caption) in enumerate(entries, start=1):
        lines.extend([str(index), f"{srt_timestamp(start)} --> {srt_timestamp(end)}", caption, ""])
    output_path.write_text("\n".join(lines), encoding="utf-8")


def concat_clips(media: list[SceneMedia], work_dir: Path, output_path: Path) -> None:
    concat_path = work_dir / "concat.txt"
    lines = []
    for scene in media:
        normalized = scene.clip_path.resolve().as_posix().replace("'", "'\\''")
        lines.append(f"file '{normalized}'")
    concat_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    run_ffmpeg(["-y", "-f", "concat", "-safe", "0", "-i", str(concat_path), "-c", "copy", str(output_path)])


def attach_captions(video_path: Path, captions_path: Path, final_path: Path) -> None:
    run_ffmpeg(
        [
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(captions_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-map",
            "1:0",
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-c:s",
            "mov_text",
            "-metadata:s:s:0",
            "language=eng",
            "-metadata:s:s:0",
            "title=English",
            "-movflags",
            "+faststart",
            str(final_path),
        ]
    )


def validate_quiz_coverage(lesson: dict) -> dict[str, dict]:
    questions = load_yaml(ROOT / "content" / "questions.yaml")["lesson_banks"][lesson["lesson_code"]]
    expected = {question["id"] for question in questions}
    coverage = lesson.get("quiz_coverage", {})
    actual = set(coverage)
    if expected != actual:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"Quiz coverage mismatch. Missing={missing}; extra={extra}")
    scene_ids = {scene["id"] for scene in lesson["scenes"]}
    for question_id, item in coverage.items():
        unknown = set(item["scenes"]) - scene_ids
        if unknown:
            raise ValueError(f"{question_id} references unknown scenes: {sorted(unknown)}")
    return coverage


def write_text_artifacts(lesson: dict, media: list[SceneMedia], output_dir: Path) -> None:
    transcript = [f"# Lesson {lesson['lesson_code']}: {lesson['title']}", ""]
    for scene in lesson["scenes"]:
        transcript.extend([f"## {scene['headline']}", "", scene["narration"], ""])
    transcript.extend(["## Disclaimer", "", lesson["disclaimer"], ""])
    (output_dir / "transcript.md").write_text("\n".join(transcript), encoding="utf-8")

    coverage_lines = [
        f"# Lesson {lesson['lesson_code']} Quiz Coverage",
        "",
        "Every published question is explicitly taught in the narration. The quiz wording and answer choices are not displayed in the video.",
        "",
        "| Question ID | Concept taught | Scenes |",
        "|---|---|---|",
    ]
    for question_id, item in lesson["quiz_coverage"].items():
        coverage_lines.append(f"| {question_id} | {item['concept']} | {', '.join(item['scenes'])} |")
    (output_dir / "quiz_coverage.md").write_text("\n".join(coverage_lines) + "\n", encoding="utf-8")

    metadata = {
        "lesson_code": lesson["lesson_code"],
        "title": lesson["title"],
        "voice": lesson["voice"],
        "resolution": f"{WIDTH}x{HEIGHT}",
        "fps": FPS,
        "duration_seconds": round(sum(item.clip_duration for item in media), 2),
        "duration_minutes": round(sum(item.clip_duration for item in media) / 60, 2),
        "scenes": [
            {
                "id": item.scene_id,
                "title": item.title,
                "voice_duration_seconds": round(item.voice_duration, 2),
                "clip_duration_seconds": round(item.clip_duration, 2),
            }
            for item in media
        ],
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def create_contact_sheet(media: list[SceneMedia], output_path: Path) -> None:
    thumbs: list[Image.Image] = []
    for scene in media:
        image = Image.open(scene.frame_path).convert("RGB")
        image.thumbnail((480, 270), Image.Resampling.LANCZOS)
        thumbs.append(image.copy())
    columns = 2
    rows = math.ceil(len(thumbs) / columns)
    sheet = Image.new("RGB", (columns * 480, rows * 270), NAVY)
    for index, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((index % columns) * 480, (index // columns) * 270))
    sheet.save(output_path, quality=94)


def render_lesson(config_path: Path, *, force: bool = False) -> Path:
    lesson = load_yaml(config_path)
    validate_quiz_coverage(lesson)

    safe_code = lesson["lesson_code"].replace(".", "_")
    safe_title = re.sub(r"[^A-Za-z0-9]+", "_", lesson["title"]).strip("_")
    output_dir = ROOT / "video_output" / f"lesson_{safe_code}"
    final_video = output_dir / f"FFCU_Lesson_{safe_code}_{safe_title}.mp4"
    if not force and final_video.is_file():
        try:
            media_duration(final_video)
        except RuntimeError:
            final_video.unlink(missing_ok=True)
        else:
            print(f"Reusing finished video: {final_video}")
            return final_video

    work_dir = output_dir / "work"
    frames_dir = work_dir / "frames"
    audio_dir = work_dir / "audio"
    clips_dir = work_dir / "clips"
    for directory in (output_dir, work_dir, frames_dir, audio_dir, clips_dir):
        directory.mkdir(parents=True, exist_ok=True)

    logo = load_logo()
    media: list[SceneMedia] = []
    for index, scene in enumerate(lesson["scenes"], start=1):
        stem = f"{index:02d}_{scene['id']}"
        frame = frames_dir / f"{stem}.png"
        audio = audio_dir / f"{stem}.mp3"
        clip = clips_dir / f"{stem}.mp4"
        if force or not frame.exists():
            render_scene_frame(scene, lesson, logo, frame)
        actual_audio = synthesize(scene["narration"], audio, lesson["voice"], force=force)
        voice_duration = media_duration(actual_audio)
        if force or not clip.exists():
            clip_duration = render_clip(frame, actual_audio, clip, voice_duration)
        else:
            try:
                clip_duration = media_duration(clip)
            except RuntimeError:
                clip.unlink(missing_ok=True)
                clip_duration = render_clip(frame, actual_audio, clip, voice_duration)
        media.append(
            SceneMedia(
                scene_id=scene["id"],
                title=scene["headline"],
                narration=scene["narration"],
                frame_path=frame,
                audio_path=actual_audio,
                clip_path=clip,
                voice_duration=voice_duration,
                clip_duration=clip_duration,
            )
        )
        print(f"Prepared {stem}: {clip_duration:.1f}s")

    captions_path = output_dir / f"lesson_{safe_code}_captions.srt"
    build_captions(media, captions_path)
    raw_video = work_dir / f"lesson_{safe_code}_raw.mp4"
    concat_clips(media, work_dir, raw_video)
    attach_captions(raw_video, captions_path, final_video)

    shutil.copyfile(media[0].frame_path, output_dir / f"lesson_{safe_code}_thumbnail.png")
    create_contact_sheet(media, output_dir / f"lesson_{safe_code}_contact_sheet.jpg")
    write_text_artifacts(lesson, media, output_dir)
    print(f"Finished: {final_video}")
    return final_video


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a Fortune & Finance lesson video.")
    parser.add_argument(
        "config",
        nargs="?",
        type=Path,
        default=ROOT / "video_production" / "lessons" / "1.1.yaml",
        help="Path to a lesson production YAML file.",
    )
    parser.add_argument("--force", action="store_true", help="Regenerate cached scene media.")
    args = parser.parse_args()
    render_lesson(args.config.resolve(), force=args.force)


if __name__ == "__main__":
    main()
