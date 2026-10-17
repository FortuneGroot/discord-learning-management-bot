# Fortune & Finance University Video Production

This folder contains the source packages for fully AI-produced course videos. No filming or screen recording is required.

Each lesson package contains:

- Word-for-word narration
- Scene headlines and visual direction
- AI voice settings
- Exact quiz-question coverage mapping
- A reusable render configuration

The renderer creates:

- A 1080p MP4 with an embedded optional English caption track
- A separate `.srt` caption file
- A transcript
- A quiz coverage report
- A thumbnail
- A visual QA contact sheet
- Duration and scene metadata

## Render a lesson

From the project directory:

```powershell
.\.venv\Scripts\python.exe scripts\render_lesson_video.py video_production\lessons\1.1.yaml
```

Use `--force` to regenerate cached narration, frames, and clips.

The renderer uses a natural neural AI voice when online. If that service is unavailable, it automatically falls back to a local Windows AI voice so production is never blocked.
