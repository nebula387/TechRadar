import logging
import textwrap
from pathlib import Path

logger = logging.getLogger(__name__)

CARD_W, CARD_H = 1080, 1080

# Font paths tried in order (Linux CI first, then Windows)
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
]


def _find_font():
    try:
        from PIL import ImageFont
        for path in FONT_CANDIDATES:
            if Path(path).exists():
                return path
    except ImportError:
        pass
    return None


def _load_font(size: int):
    try:
        from PIL import ImageFont
        path = _find_font()
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

        # Top accent stripe
        for y in range(10):
            opacity_color = tuple(int(c * (1 - y / 12)) for c in accent)
            draw.line([(0, y), (CARD_W, y)], fill=opacity_color)

        # Inner card surface
        draw.rounded_rectangle(
            [pad, pad, CARD_W - pad, CARD_H - pad],
            radius=28,
            fill=(22, 22, 35),
        )

        # Fonts
        f_xs = _load_font(26)
        f_sm = _load_font(34)
        f_md = _load_font(48)
        f_lg = _load_font(70)

        inner_x = pad + 48
        inner_y = pad + 44

        # Source + score line
        meta = f"#{source.upper()}  ·  Score {score}/100"
        draw.text((inner_x, inner_y), meta, font=f_xs, fill=(120, 120, 145))

        # Category badge
        badge_y = inner_y + 46
        badge_text = category.upper()
        badge_w = len(badge_text) * 16 + 24
        draw.rounded_rectangle(
            [inner_x, badge_y, inner_x + badge_w, badge_y + 38],
            radius=6,
            fill=accent,
        )
        draw.text((inner_x + 12, badge_y + 6), badge_text, font=f_xs, fill=(255, 255, 255))

        # Emoji
        emoji_y = badge_y + 60
        draw.text((inner_x, emoji_y), emoji, font=_load_font(90), fill=(255, 255, 255))

        # Title
        title_y = emoji_y + 118
        for line in textwrap.wrap(title, width=26)[:4]:
            draw.text((inner_x, title_y), line, font=f_lg, fill=(240, 240, 255))
            title_y += 82

        # Description
        desc_y = title_y + 14
        for line in textwrap.wrap(description[:200], width=44)[:3]:
            draw.text((inner_x, desc_y), line, font=f_md, fill=(160, 160, 185))
            desc_y += 60

        # Bottom separator + brand
        sep_y = CARD_H - pad - 72
        draw.line([(inner_x, sep_y), (CARD_W - pad - 48, sep_y)], fill=accent, width=2)
        draw.text(
            (inner_x, sep_y + 14),
            "TechRadar AI  ·  Signal, not noise.",
            font=f_sm,
            fill=(90, 90, 115),
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, "PNG", optimize=True)
        logger.info(f"Card saved: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Card generation failed: {e}")
        return None
