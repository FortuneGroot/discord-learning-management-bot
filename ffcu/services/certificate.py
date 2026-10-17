from __future__ import annotations

import math
import secrets
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ffcu.models import Certificate, Student


DISCLAIMER = (
    "This Certificate of Completion is not an accredited academic degree, professional license, "
    "investment adviser credential, or guarantee of trading knowledge, performance, or ability."
)

DEFAULT_LOGO_PATH = Path(__file__).resolve().parents[2] / "assets" / "fortune_finance_logo.jpg"
CALLIGRAPHY_FONT = "FFCU-Calligraphy"


class CertificateService:
    def __init__(self, output_directory: Path, logo_path: Path | None = None):
        self.output_directory = output_directory.resolve()
        self.logo_path = (logo_path or DEFAULT_LOGO_PATH).resolve()

    @staticmethod
    def _next_id(session: Session, year: int) -> str:
        prefix = f"FFCU-{year}-"
        latest = session.scalar(
            select(Certificate.certificate_id)
            .where(Certificate.certificate_id.like(f"{prefix}%"))
            .order_by(Certificate.certificate_id.desc())
            .limit(1)
        )
        sequence = int(latest.rsplit("-", 1)[1]) + 1 if latest else 1
        return f"{prefix}{sequence:06d}"

    def issue(self, session: Session, student: Student, certificate_name: str | None = None) -> Certificate:
        existing = session.scalar(select(Certificate).where(Certificate.student_id == student.id))
        if existing:
            return existing
        if student.status != "graduate":
            raise ValueError("Certificate issuance requires verified graduation.")
        name = (certificate_name or student.certificate_name or student.display_name).strip()[:120]
        if not name:
            raise ValueError("A certificate name is required.")
        year = datetime.now(timezone.utc).year
        certificate_id = self._next_id(session, year)
        verification_code = secrets.token_hex(6).upper()
        self.output_directory.mkdir(parents=True, exist_ok=True)
        output = self.output_directory / f"{certificate_id}.pdf"
        issued_at = datetime.now(timezone.utc)
        self._render(output, name, certificate_id, verification_code, issued_at, self.logo_path)
        certificate = Certificate(
            certificate_id=certificate_id,
            verification_code=verification_code,
            student_id=student.id,
            certificate_name=name,
            issued_at=issued_at,
            file_path=str(output),
        )
        session.add(certificate)
        session.flush()
        return certificate

    @staticmethod
    def _logo_reader(logo_path: Path, paper_hex: str, strength: float):
        """Create a circular, paper-blended logo without writing a temporary image."""
        try:
            from PIL import Image, ImageDraw, ImageFilter, ImageOps
            from reportlab.lib.utils import ImageReader
        except ImportError as exc:
            raise RuntimeError("Pillow and ReportLab are required to render the certificate logo.") from exc

        with Image.open(logo_path) as source:
            logo = ImageOps.fit(source.convert("RGB"), (700, 700), method=Image.Resampling.LANCZOS)
        paper_rgb = tuple(int(paper_hex[index:index + 2], 16) for index in (1, 3, 5))
        paper = Image.new("RGB", logo.size, paper_rgb)
        blended = Image.blend(paper, logo, max(0.0, min(1.0, strength))).convert("RGBA")
        mask = Image.new("L", logo.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((18, 18, 682, 682), fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(7))
        blended.putalpha(mask)
        buffer = BytesIO()
        blended.save(buffer, format="PNG", optimize=True)
        buffer.seek(0)
        return ImageReader(buffer)

    @staticmethod
    def _register_calligraphy_font() -> str:
        """Register ReportLab's redistributable calligraphy face for recipient names."""
        try:
            import reportlab
            from reportlab.pdfbase import pdfmetrics
        except ImportError as exc:
            raise RuntimeError("ReportLab is required to render the certificate calligraphy.") from exc

        if CALLIGRAPHY_FONT not in pdfmetrics.getRegisteredFontNames():
            font_directory = Path(reportlab.__file__).resolve().parent / "fonts"
            face = pdfmetrics.EmbeddedType1Face(
                str(font_directory / "callig15.afm"),
                str(font_directory / "callig15.pfb"),
            )
            pdfmetrics.registerTypeFace(face)
            pdfmetrics.registerFont(pdfmetrics.Font(CALLIGRAPHY_FONT, face.name, "WinAnsiEncoding"))
        return CALLIGRAPHY_FONT

    @staticmethod
    def _draw_arc_text(canvas, text: str, center_x: float, center_y: float, radius: float, start: float, end: float, *, font: str, size: float, color) -> None:
        if not text:
            return
        angles = [start] if len(text) == 1 else [start + (end - start) * index / (len(text) - 1) for index in range(len(text))]
        for character, angle in zip(text, angles):
            radians = math.radians(angle)
            canvas.saveState()
            canvas.translate(center_x + radius * math.cos(radians), center_y + radius * math.sin(radians))
            rotation = angle - 90 if center_y + radius * math.sin(radians) >= center_y else angle + 90
            canvas.rotate(rotation)
            canvas.setFillColor(color)
            canvas.setFont(font, size)
            canvas.drawCentredString(0, -size * 0.32, character)
            canvas.restoreState()

    @classmethod
    def _draw_seal(cls, canvas, center_x: float, center_y: float, logo_path: Path | None, colors: dict[str, object]) -> None:
        navy, gold, deep_gold, paper, pale_gold = (
            colors["navy"], colors["gold"], colors["deep_gold"], colors["paper"], colors["pale_gold"]
        )
        # Traditional ribbon tails behind the circular seal.
        canvas.setFillColor(navy)
        left = canvas.beginPath()
        left.moveTo(center_x - 34, center_y - 28)
        left.lineTo(center_x - 57, center_y - 76)
        left.lineTo(center_x - 35, center_y - 66)
        left.lineTo(center_x - 21, center_y - 81)
        left.lineTo(center_x - 12, center_y - 37)
        left.close()
        canvas.drawPath(left, fill=1, stroke=0)
        right = canvas.beginPath()
        right.moveTo(center_x + 34, center_y - 28)
        right.lineTo(center_x + 57, center_y - 76)
        right.lineTo(center_x + 35, center_y - 66)
        right.lineTo(center_x + 21, center_y - 81)
        right.lineTo(center_x + 12, center_y - 37)
        right.close()
        canvas.drawPath(right, fill=1, stroke=0)
        canvas.setStrokeColor(gold)
        canvas.setLineWidth(1)
        canvas.line(center_x - 34, center_y - 30, center_x - 50, center_y - 68)
        canvas.line(center_x + 34, center_y - 30, center_x + 50, center_y - 68)

        # Serrated antique-medallion edge.
        edge = canvas.beginPath()
        points = 72
        for index in range(points):
            angle = math.tau * index / points
            radius = 61 if index % 2 == 0 else 56.5
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            if index == 0:
                edge.moveTo(x, y)
            else:
                edge.lineTo(x, y)
        edge.close()
        canvas.setFillColor(pale_gold)
        canvas.setStrokeColor(deep_gold)
        canvas.setLineWidth(1.2)
        canvas.drawPath(edge, fill=1, stroke=1)

        canvas.setFillColor(paper)
        canvas.setStrokeColor(navy)
        canvas.setLineWidth(1.4)
        canvas.circle(center_x, center_y, 53, fill=1, stroke=1)
        canvas.setStrokeColor(gold)
        canvas.setLineWidth(2)
        canvas.circle(center_x, center_y, 48.5, fill=0, stroke=1)
        canvas.setStrokeColor(deep_gold)
        canvas.setLineWidth(0.55)
        canvas.circle(center_x, center_y, 42, fill=0, stroke=1)

        if logo_path and logo_path.exists():
            logo = cls._logo_reader(logo_path, "#FBF8F1", 0.48)
            canvas.drawImage(logo, center_x - 31, center_y - 31, 62, 62, preserveAspectRatio=True, mask="auto")

        cls._draw_arc_text(
            canvas, "FORTUNE & FINANCE", center_x, center_y, 45, 151, 29,
            font="Helvetica-Bold", size=5.1, color=navy,
        )
        cls._draw_arc_text(
            canvas, "EST. 2025", center_x, center_y, 45, 215, 325,
            font="Helvetica-Bold", size=5.2, color=navy,
        )
        canvas.setFillColor(gold)
        canvas.circle(center_x - 44, center_y, 1.5, fill=1, stroke=0)
        canvas.circle(center_x + 44, center_y, 1.5, fill=1, stroke=0)

    @staticmethod
    def _name_layout(
        canvas,
        name: str,
        font_name: str = CALLIGRAPHY_FONT,
        maximum_size: int = 42,
    ) -> tuple[list[str], int]:
        size = maximum_size
        if canvas.stringWidth(name, font_name, size) <= 500:
            return [name], size
        words = name.split()
        if len(words) == 1:
            measured = canvas.stringWidth(name, font_name, size)
            return [name], max(10, int(size * 500 / measured))
        candidates = [(" ".join(words[:index]), " ".join(words[index:])) for index in range(1, len(words))]
        for candidate_size in range(maximum_size - 4, 15, -1):
            best = min(
                candidates,
                key=lambda pair: max(canvas.stringWidth(part, font_name, candidate_size) for part in pair),
            )
            if max(canvas.stringWidth(part, font_name, candidate_size) for part in best) <= 500:
                return list(best), candidate_size
        return [name[:60], name[60:]], 15

    @classmethod
    def _render(
        cls,
        path: Path,
        name: str,
        certificate_id: str,
        verification_code: str,
        issued_at: datetime,
        logo_path: Path | None = None,
    ) -> None:
        try:
            from reportlab.lib.colors import HexColor
            from reportlab.lib.pagesizes import landscape, letter
            from reportlab.pdfgen.canvas import Canvas
        except ImportError as exc:
            raise RuntimeError("ReportLab is required to generate certificates.") from exc

        width, height = landscape(letter)
        colors = {
            "navy": HexColor("#0B1424"),
            "gold": HexColor("#D4AF37"),
            "deep_gold": HexColor("#9A741C"),
            "ivory": HexColor("#F4EFE6"),
            "paper": HexColor("#FBF8F1"),
            "pale_gold": HexColor("#E8D9AE"),
            "slate": HexColor("#526071"),
            "faint": HexColor("#D9D1C2"),
        }
        navy, gold, deep_gold, ivory, paper, slate = (
            colors["navy"], colors["gold"], colors["deep_gold"], colors["ivory"], colors["paper"], colors["slate"]
        )
        canvas = Canvas(str(path), pagesize=(width, height), pageCompression=1)
        canvas.setTitle(f"Fortune & Finance Certificate - {certificate_id}")
        canvas.setAuthor("Fortune & Finance LLC")

        # Warm paper, with the website's navy and gold used as restrained accents.
        canvas.setFillColor(ivory)
        canvas.rect(0, 0, width, height, fill=1, stroke=0)
        canvas.setFillColor(paper)
        canvas.roundRect(17, 17, width - 34, height - 34, 5, fill=1, stroke=0)
        canvas.setStrokeColor(navy)
        canvas.setLineWidth(2.8)
        canvas.rect(25, 25, width - 50, height - 50, fill=0, stroke=1)
        canvas.setStrokeColor(gold)
        canvas.setLineWidth(1.2)
        canvas.rect(32, 32, width - 64, height - 64, fill=0, stroke=1)
        canvas.setStrokeColor(deep_gold)
        canvas.setLineWidth(0.45)
        canvas.rect(38, 38, width - 76, height - 76, fill=0, stroke=1)

        # Small geometric corner details echo the site's editorial, institutional feel.
        for x_sign, y_sign in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            corner_x = 48 if x_sign == 1 else width - 48
            corner_y = 48 if y_sign == 1 else height - 48
            canvas.setStrokeColor(gold)
            canvas.setLineWidth(0.8)
            canvas.line(corner_x, corner_y, corner_x + x_sign * 29, corner_y)
            canvas.line(corner_x, corner_y, corner_x, corner_y + y_sign * 29)
            canvas.setFillColor(gold)
            canvas.circle(corner_x, corner_y, 2.3, fill=1, stroke=0)

        logo = logo_path or DEFAULT_LOGO_PATH

        canvas.setFillColor(gold)
        canvas.setFont("Helvetica-Bold", 9.2)
        canvas.drawCentredString(width / 2, height - 69, "FORTUNE & FINANCE ACADEMY - ESTABLISHED 2025")
        canvas.setFillColor(navy)
        canvas.setFont("Times-Bold", 31)
        canvas.drawCentredString(width / 2, height - 106, "CRYPTO UNIVERSITY")
        canvas.setStrokeColor(gold)
        canvas.setLineWidth(0.9)
        canvas.line(width / 2 - 142, height - 120, width / 2 - 12, height - 120)
        canvas.line(width / 2 + 12, height - 120, width / 2 + 142, height - 120)
        diamond = canvas.beginPath()
        diamond.moveTo(width / 2, height - 115)
        diamond.lineTo(width / 2 + 5, height - 120)
        diamond.lineTo(width / 2, height - 125)
        diamond.lineTo(width / 2 - 5, height - 120)
        diamond.close()
        canvas.setFillColor(gold)
        canvas.drawPath(diamond, fill=1, stroke=0)

        canvas.setFillColor(navy)
        canvas.setFont("Times-Roman", 16)
        canvas.drawCentredString(width / 2, height - 151, "CERTIFICATE OF COMPLETION")
        canvas.setFillColor(slate)
        canvas.setFont("Times-Italic", 10.8)
        canvas.drawCentredString(
            width / 2,
            height - 179,
            "By authority of Fortune & Finance Academy, this certifies that",
        )

        font_name = cls._register_calligraphy_font()
        name_lines, name_font_size = cls._name_layout(canvas, name, font_name)
        canvas.setFillColor(navy)
        canvas.setFont(font_name, name_font_size)
        if len(name_lines) == 1:
            canvas.drawCentredString(width / 2, height - 220, name_lines[0])
            rule_y, description_y = height - 231, height - 260
        else:
            canvas.drawCentredString(width / 2, height - 213, name_lines[0])
            canvas.drawCentredString(width / 2, height - 243, name_lines[1])
            rule_y, description_y = height - 254, height - 281
        canvas.setStrokeColor(gold)
        canvas.setLineWidth(1)
        canvas.line(width / 2 - 250, rule_y, width / 2 + 250, rule_y)
        canvas.setFillColor(navy)
        canvas.setFont("Times-Roman", 11.2)
        canvas.drawCentredString(width / 2, description_y, "has successfully completed the prescribed course of study and examinations")
        canvas.drawCentredString(width / 2, description_y - 18, "of the Fortune & Finance Crypto University.")

        cls._draw_seal(canvas, width / 2, 137, logo if logo.exists() else None, colors)

        canvas.setFillColor(slate)
        canvas.setFont("Helvetica", 8.1)
        canvas.drawString(67, 157, "DATE OF COMPLETION")
        canvas.setFillColor(navy)
        canvas.setFont("Times-Bold", 10)
        canvas.drawString(67, 141, f"{issued_at:%B %d, %Y}")
        canvas.setStrokeColor(colors["faint"])
        canvas.setLineWidth(0.6)
        canvas.line(67, 132, 254, 132)
        canvas.setFillColor(slate)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(67, 116, f"CERTIFICATE ID  {certificate_id}")
        canvas.drawString(67, 102, f"VERIFICATION  {verification_code}")

        canvas.setStrokeColor(navy)
        canvas.setLineWidth(0.75)
        canvas.line(width - 255, 151, width - 67, 151)
        canvas.line(width - 255, 111, width - 67, 111)
        canvas.setFillColor(slate)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawCentredString(width - 161, 138, "AUTHORIZED SIGNATURE")
        canvas.drawCentredString(width - 161, 98, "PROGRAM DIRECTOR")

        canvas.setFillColor(gold)
        canvas.setFont("Helvetica-Bold", 7.2)
        canvas.drawCentredString(width / 2, 63, "FORTUNEANDFINANCE.COM")
        canvas.setFillColor(slate)
        disclaimer_font_size = 6.2
        canvas.setFont("Helvetica", disclaimer_font_size)
        words = DISCLAIMER.split()
        disclaimer_lines: list[str] = []
        current_line = ""
        for word in words:
            candidate = f"{current_line} {word}".strip()
            if current_line and canvas.stringWidth(candidate, "Helvetica", disclaimer_font_size) > 650:
                disclaimer_lines.append(current_line)
                current_line = word
            else:
                current_line = candidate
        if current_line:
            disclaimer_lines.append(current_line)
        for index, line in enumerate(disclaimer_lines[:2]):
            canvas.drawCentredString(width / 2, 49 - index * 7, line)
        canvas.showPage()
        canvas.save()
