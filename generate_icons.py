"""
Run once to generate PWA icons in static/icons/
Usage: python generate_icons.py
"""
from PIL import Image, ImageDraw, ImageFont
import os, math

SIZES   = [72, 96, 128, 144, 152, 192, 384, 512]
OUT_DIR = os.path.join('static', 'icons')
os.makedirs(OUT_DIR, exist_ok=True)

def make_icon(size):
    img  = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background circle — red
    margin = size * 0.04
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=(220, 53, 69, 255)
    )

    # Inner lighter circle for depth
    inner_m = size * 0.12
    draw.ellipse(
        [inner_m, inner_m, size - inner_m, size - inner_m],
        fill=(180, 35, 50, 255)
    )

    # Draw "SOS" text centred
    text     = 'SOS'
    font_size = int(size * 0.35)
    try:
        font = ImageFont.truetype('arial.ttf', font_size)
    except OSError:
        try:
            font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', font_size)
        except OSError:
            font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw   = bbox[2] - bbox[0]
    th   = bbox[3] - bbox[1]
    x    = (size - tw) / 2 - bbox[0]
    y    = (size - th) / 2 - bbox[1]

    # Shadow
    draw.text((x + size*0.015, y + size*0.015), text, font=font, fill=(100, 15, 25, 180))
    # Main text
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))

    # Small shield icon at bottom-right (just a triangle hint)
    shield_r = size * 0.14
    cx = size * 0.78
    cy = size * 0.78
    draw.ellipse(
        [cx - shield_r, cy - shield_r, cx + shield_r, cy + shield_r],
        fill=(255, 193, 7, 255)
    )

    return img

for size in SIZES:
    icon = make_icon(size)
    path = os.path.join(OUT_DIR, f'icon-{size}.png')
    icon.save(path, 'PNG')
    print(f'✅ Generated {path}')

print('\nAll PWA icons generated in static/icons/')
