from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from ffcu.services.certificate import CertificateService


def main() -> None:
    output = PROJECT / "assets" / "certificate_preview.pdf"
    CertificateService._render(
        output,
        "Sample Student",
        "FFCU-2026-PREVIEW",
        "PREVIEW-ONLY",
        datetime.now(timezone.utc),
    )
    print(f"Certificate preview created: {output}")


if __name__ == "__main__":
    main()
