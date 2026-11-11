"""Small helper layer over python-pptx for a consistent, light, editable deck.

Everything is a native shape or text frame — no flattened images — so the decks
stay editable in PowerPoint / LibreOffice / Google Slides.
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

NAVY = RGBColor(0x0B, 0x1D, 0x33)
INK = RGBColor(0x1E, 0x29, 0x3B)
SLATE = RGBColor(0x51, 0x5F, 0x73)
MUTED = RGBColor(0x7A, 0x88, 0x99)
LINE = RGBColor(0xE3, 0xE8, 0xF0)
BRAND = RGBColor(0x25, 0x63, 0xEB)
BRAND_SOFT = RGBColor(0xEF, 0xF5, 0xFF)
GREEN = RGBColor(0x10, 0xB9, 0x81)
AMBER = RGBColor(0xF5, 0x9E, 0x0B)
ROSE = RGBColor(0xEF, 0x44, 0x44)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BG = RGBColor(0xF6, 0xF8, 0xFB)

FONT = "Inter"
MONO = "Consolas"

SLIDE_W = 13.333
SLIDE_H = 7.5


class Deck:
    def __init__(self) -> None:
        self.prs = Presentation()
        self.prs.slide_width = Inches(SLIDE_W)
        self.prs.slide_height = Inches(SLIDE_H)
        self.footer = "OpsDesk for TBO · synthetic demo data"
        self.index = 0

    # ---------------------------------------------------------------- helpers
    def _blank(self):
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(SLIDE_W), Inches(SLIDE_H))
        bg.fill.solid()
        bg.fill.fore_color.rgb = WHITE
        bg.line.fill.background()
        return slide

    def text(
        self,
        slide,
        left: float,
        top: float,
        width: float,
        height: float,
        content: str,
        size: int = 14,
        bold: bool = False,
        color: RGBColor = INK,
        font: str = FONT,
        align: PP_ALIGN = PP_ALIGN.LEFT,
        anchor: MSO_ANCHOR = MSO_ANCHOR.TOP,
        line_spacing: float = 1.15,
        space_after: int = 4,
    ):
        box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
        frame = box.text_frame
        frame.word_wrap = True
        frame.vertical_anchor = anchor
        frame.margin_left = 0
        frame.margin_right = 0
        frame.margin_top = 0
        frame.margin_bottom = 0
        lines = content.split("\n")
        for position, line in enumerate(lines):
            paragraph = frame.paragraphs[0] if position == 0 else frame.add_paragraph()
            paragraph.alignment = align
            paragraph.line_spacing = line_spacing
            paragraph.space_after = Pt(space_after)
            run = paragraph.add_run()
            run.text = line
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.color.rgb = color
            run.font.name = font
        return box

    def bullets(
        self,
        slide,
        left: float,
        top: float,
        width: float,
        height: float,
        items: list[str],
        size: int = 15,
        color: RGBColor = SLATE,
        bullet_color: RGBColor = BRAND,
        gap: int = 10,
    ):
        box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
        frame = box.text_frame
        frame.word_wrap = True
        frame.margin_left = 0
        frame.margin_top = 0
        for index, item in enumerate(items):
            paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
            paragraph.line_spacing = 1.18
            paragraph.space_after = Pt(gap)
            marker = paragraph.add_run()
            marker.text = "•  "
            marker.font.size = Pt(size)
            marker.font.bold = True
            marker.font.color.rgb = bullet_color
            marker.font.name = FONT
            run = paragraph.add_run()
            run.text = item
            run.font.size = Pt(size)
            run.font.color.rgb = color
            run.font.name = FONT
        return box

    def rect(
        self,
        slide,
        left: float,
        top: float,
        width: float,
        height: float,
        fill: RGBColor = BG,
        line: RGBColor | None = LINE,
        radius: bool = True,
        line_width: float = 1.0,
    ):
        shape = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
            Inches(left), Inches(top), Inches(width), Inches(height),
        )
        if radius:
            try:
                shape.adjustments[0] = 0.06
            except Exception:  # noqa: BLE001
                pass
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
        if line is None:
            shape.line.fill.background()
        else:
            shape.line.color.rgb = line
            shape.line.width = Pt(line_width)
        shape.shadow.inherit = False
        return shape

    def pill(self, slide, left: float, top: float, width: float, text: str, fill=BRAND_SOFT, color=BRAND, size=11):
        shape = self.rect(slide, left, top, width, 0.34, fill=fill, line=None)
        frame = shape.text_frame
        frame.word_wrap = False
        frame.margin_left = Emu(0)
        frame.margin_right = Emu(0)
        frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        paragraph = frame.paragraphs[0]
        paragraph.alignment = PP_ALIGN.CENTER
        run = paragraph.add_run()
        run.text = text
        run.font.size = Pt(size)
        run.font.bold = True
        run.font.color.rgb = color
        run.font.name = FONT
        return shape

    def kpi_card(self, slide, left, top, width, height, label, value, hint="", accent=BRAND):
        self.rect(slide, left, top, width, height, fill=WHITE, line=LINE)
        self.text(slide, left + 0.22, top + 0.18, width - 0.44, 0.28, label.upper(), size=10, bold=True, color=MUTED)
        self.text(slide, left + 0.22, top + 0.48, width - 0.44, 0.55, value, size=24, bold=True, color=accent)
        if hint:
            self.text(slide, left + 0.22, top + 1.02, width - 0.44, height - 1.1, hint, size=10.5, color=SLATE)

    def chrome(self, slide, kicker: str, title: str, subtitle: str = "", number: bool = True):
        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(0.14), Inches(SLIDE_H))
        bar.fill.solid()
        bar.fill.fore_color.rgb = BRAND
        bar.line.fill.background()
        self.text(slide, 0.62, 0.46, 9.5, 0.3, kicker.upper(), size=10.5, bold=True, color=BRAND)
        self.text(slide, 0.62, 0.74, 11.9, 0.8, title, size=27, bold=True, color=NAVY)
        if subtitle:
            self.text(slide, 0.62, 1.5, 11.2, 0.5, subtitle, size=13.5, color=SLATE)
        self.index += 1
        self.text(slide, 0.62, SLIDE_H - 0.42, 8.0, 0.3, self.footer, size=9.5, color=MUTED)
        if number:
            self.text(slide, SLIDE_W - 1.05, SLIDE_H - 0.42, 0.5, 0.3, f"{self.index:02d}", size=9.5, color=MUTED, align=PP_ALIGN.RIGHT)

    def picture(self, slide, path: Path, left, top, width, height=None, caption: str = "", frame=True):
        """Place a picture preserving its aspect ratio.

        ``width`` is the preferred width; if that would exceed ``height`` the
        picture is scaled down so it never overflows the slide area.
        """
        from PIL import Image

        with Image.open(path) as image:
            aspect = image.width / image.height
        draw_width = width
        draw_height = draw_width / aspect
        if height is not None and draw_height > height:
            draw_height = height
            draw_width = draw_height * aspect

        if frame:
            self.rect(slide, left - 0.05, top - 0.05, draw_width + 0.1, draw_height + 0.1, fill=WHITE, line=LINE)
        slide.shapes.add_picture(str(path), Inches(left), Inches(top), width=Inches(draw_width), height=Inches(draw_height))
        if caption:
            self.text(slide, left, top + draw_height + 0.1, draw_width, 0.3, caption, size=10, color=MUTED)
        return draw_width, draw_height

    def table(
        self,
        slide,
        left,
        top,
        width,
        rows: list[list[str]],
        col_widths: list[float],
        header_fill=NAVY,
        size=10.5,
        row_height=0.3,
        header_size=10,
    ):
        shape = slide.shapes.add_table(len(rows), len(rows[0]), Inches(left), Inches(top), Inches(width), Inches(row_height * len(rows)))
        table = shape.table
        for index, width_inches in enumerate(col_widths):
            table.columns[index].width = Inches(width_inches)
        for r, row in enumerate(rows):
            table.rows[r].height = Inches(row_height)
            for c, value in enumerate(row):
                cell = table.cell(r, c)
                cell.text = ""
                cell.margin_left = Inches(0.07)
                cell.margin_right = Inches(0.05)
                cell.margin_top = Inches(0.02)
                cell.margin_bottom = Inches(0.02)
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                cell.fill.solid()
                cell.fill.fore_color.rgb = header_fill if r == 0 else (WHITE if r % 2 else BG)
                paragraph = cell.text_frame.paragraphs[0]
                run = paragraph.add_run()
                run.text = str(value)
                run.font.size = Pt(header_size if r == 0 else size)
                run.font.bold = r == 0
                run.font.color.rgb = WHITE if r == 0 else INK
                run.font.name = FONT
        return table

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.prs.save(str(path))
        return path


def title_slide(deck: Deck, eyebrow: str, title: str, subtitle: str, bullets: list[str], meta: str):
    slide = deck._blank()
    # left panel
    panel = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(7.6), Inches(SLIDE_H))
    panel.fill.solid()
    panel.fill.fore_color.rgb = NAVY
    panel.line.fill.background()
    badge = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.7), Inches(0.75), Inches(0.55), Inches(0.55))
    badge.fill.solid()
    badge.fill.fore_color.rgb = BRAND
    badge.line.fill.background()
    frame = badge.text_frame
    frame.word_wrap = False
    frame.margin_left = Emu(0)
    frame.margin_right = Emu(0)
    frame.margin_top = Emu(0)
    frame.margin_bottom = Emu(0)
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    paragraph = frame.paragraphs[0]
    paragraph.alignment = PP_ALIGN.CENTER
    run = paragraph.add_run()
    run.text = "OD"
    run.font.size = Pt(12)
    run.font.bold = True
    run.font.color.rgb = WHITE
    run.font.name = FONT
    deck.text(slide, 1.38, 0.86, 5.0, 0.35, "OpsDesk for TBO", size=15, bold=True, color=WHITE)
    deck.text(slide, 0.7, 1.85, 6.4, 0.35, eyebrow.upper(), size=11, bold=True, color=RGBColor(0x5B, 0x95, 0xF7))
    deck.text(slide, 0.7, 2.2, 6.5, 1.9, title, size=36, bold=True, color=WHITE, line_spacing=1.06)
    deck.text(slide, 0.7, 4.05, 6.3, 0.7, subtitle, size=13.5, color=RGBColor(0xC7, 0xD2, 0xE0), line_spacing=1.25)
    deck.text(slide, 0.7, SLIDE_H - 0.75, 6.4, 0.3, meta, size=9.5, color=RGBColor(0x8A, 0x9B, 0xB0))
    for position, item in enumerate(bullets):
        deck.bullets(slide, 8.15, 1.9 + position * 1.25, 4.5, 1.1, [item], size=13, color=SLATE)
    deck.index += 1
    return slide


def closing_slide(deck: Deck, statement: str, supporting: list[str], signoff: str):
    slide = deck._blank()
    panel = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(SLIDE_W), Inches(SLIDE_H))
    panel.fill.solid()
    panel.fill.fore_color.rgb = NAVY
    panel.line.fill.background()
    deck.text(slide, 1.1, 2.1, 11.2, 1.6, statement, size=34, bold=True, color=WHITE, line_spacing=1.12)
    for position, item in enumerate(supporting):
        deck.text(slide, 1.12, 4.0 + position * 0.46, 10.8, 0.4, f"—  {item}", size=13, color=RGBColor(0xC7, 0xD2, 0xE0))
    deck.text(slide, 1.12, SLIDE_H - 0.95, 11.0, 0.3, signoff, size=10, color=RGBColor(0x8A, 0x9B, 0xB0))
    deck.index += 1
    return slide
