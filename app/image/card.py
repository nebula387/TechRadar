import logging
import textwrap
from pathlib import Path

logger = logging.getLogger(__name__)

CARD_W, CARD_H = 1080, 1080

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
]

FONT_REGULAR_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
]


def _find_font(candidates: list[str]) -> str | None:
    try:
        from PIL import ImageFont  # noqa: F401
        for path in candidates:
            if Path(path).exists():
                return path
    except ImportError:
        pass
    return None


def _load_font(size: int, bold: bool = True):
    try:
        from PIL import ImageFont
        path = _find_font(FONT_CANDIDATES if bold else FONT_REGULAR_CANDIDATES)
        if path:
            return ImageFont.truetype(path, size)
        return ImageFont.load_default()
    except Exception:
        from PIL import ImageFont
        return ImageFont.load_default()


def _hex_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _darken(rgb: tuple, amount: int = 110) -> tuple:
    return tuple(max(0, c - amount) for c in rgb)


def _ascii_only(text: str) -> str:
    """Strip non-ASCII characters (emoji, CJK) that DejaVu can't render."""
    return "".join(c if ord(c) < 128 else " " for c in text).strip()


def generate_card(
    title: str,
    description: str,
    category: str,
    emoji: str,
    accent_color: str,
    source: str,
    score: int,
    output_path: Path,
) -> Path | None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        logger.warning("Pillow not installed — skipping image card generation")
        return None

    try:
        accent = _hex_rgb(accent_color)
        bg = _darken(accent, 120)

        img = Image.new("RGB", (CARD_W, CARD_H), color=bg)
        draw = ImageDraw.Draw(img)

        pad = 56
        inner_x = pad + 52
        inner_w = CARD_W - pad * 2 - 104  # usable text width

        # ── Background ───────────────────────────────────────────────────────
        # Subtle gradient via horizontal bands
        for y in range(CARD_H):
            t = y / CARD_H
            c = tuple(int(bg[i] + (accent[i] - bg[i]) * 0.08 * (1 - t)) for i in range(3))
            draw.line([(0, y), (CARD_W, y)], fill=c)

        # Inner card surface
        draw.rounded_rectangle(
            [pad, pad, CARD_W - pad, CARD_H - pad],
            radius=32,
            fill=(16, 16, 28),
        )

        # Top accent bar
        draw.rounded_rectangle(
            [pad, pad, CARD_W - pad, pad + 8],
            radius=32,
            fill=accent,
        )

        # ── Fonts ────────────────────────────────────────────────────────────
        f_xs  = _load_font(24)
        f_sm  = _load_font(32)
        f_md  = _load_font(44)
        f_lg  = _load_font(68)
        f_xl  = _load_font(86)

        y = pad + 52

        # Source + score
        draw.text((inner_x, y), f"{source.upper()}  ·  Score {score}/100", font=f_xs, fill=(100, 100, 130))
        y += 46

        # Category badge
        badge_text = category.upper()
        badge_w = len(badge_text) * 15 + 28
        draw.rounded_rectangle([inner_x, y, inner_x + badge_w, y + 40], radius=6, fill=accent)
        draw.text((inner_x + 14, y + 7), badge_text, font=f_xs, fill=(255, 255, 255))
        y += 68

        # Accent divider
        draw.line([(inner_x, y), (inner_x + 64, y)], fill=accent, width=4)
        y += 28

        # Title — clean ASCII only (DejaVu can't render emoji/CJK)
        clean_title = _ascii_only(title)
        if not clean_title:
            clean_title = title[:60]  # last resort: raw, truncated
        char_w = max(18, inner_w // 44)  # approximate chars per line
        title_lines = textwrap.wrap(clean_title, width=char_w)[:4]
        for line in title_lines:
            draw.text((inner_x, y), line, font=f_lg, fill=(235, 235, 255))
            y += 84
        y += 12

        # Description — 3 lines max
        clean_desc = _ascii_only(description)
        if clean_desc:
            for line in textwrap.wrap(clean_desc[:240], width=int(inner_w / 22))[:3]:
                draw.text((inner_x, y), line, font=f_md, fill=(140, 140, 170))
                y += 56

        # ── Bottom brand ─────────────────────────────────────────────────────
        brand_y = CARD_H - pad - 68
        draw.line([(inner_x, brand_y), (CARD_W - pad - 52, brand_y)], fill=(40, 40, 60), width=1)
        draw.text(
            (inner_x, brand_y + 16),
            "TechRadar AI  ·  Signal, not noise.",
            font=f_sm,
            fill=(70, 70, 95),
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, "PNG", optimize=True)
        logger.info(f"Card saved: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Card generation failed: {e}")
        return None
