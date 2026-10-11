import io
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw, ImageFont, ImageColor


def color(value, fallback):
    try:
        return ImageColor.getrgb(value)
    except Exception:
        return ImageColor.getrgb(fallback)


def font(size):
    for candidate in [Path('C:/Windows/Fonts/msyh.ttc'), Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default(size=size)


def design(asset, parameters):
    width = max(128, min(4096, int(parameters.get('width', 1080))))
    height = max(128, min(4096, int(parameters.get('height', 1080))))
    image = Image.open(asset['path']).convert('RGBA')
    background = color(parameters.get('background', '#ffffff'), '#ffffff')
    mode = parameters.get('fit', 'contain')
    if mode == 'cover':
        product = ImageOps.fit(image, (width, height), centering=(0.5, 0.5))
    else:
        title_space = int(height * .16) if parameters.get('text') else 0
        product = ImageOps.contain(image, (max(1, int(width * .9)), max(1, int((height - title_space) * .9))))
    result = Image.new('RGBA', (width, height), background + (255,))
    title_space = int(height * .16) if parameters.get('text') else 0
    result.alpha_composite(product, ((width - product.width) // 2, (height - title_space - product.height) // 2))
    drawing = ImageDraw.Draw(result)
    title = str(parameters.get('text', ''))[:120]
    if title:
        title_font = font(max(16, int(min(width, height) * .045)))
        lines = []
        current = ''
        for character in title:
            if character == '\n' or drawing.textlength(current + character, font=title_font) > width * .9:
                lines.append(current)
                current = '' if character == '\n' else character
            else:
                current += character
        if current:
            lines.append(current)
        text = '\n'.join(lines[:3])
        drawing.multiline_text((width / 2, height - title_space / 2), text, font=title_font,
                               fill=color(parameters.get('text_color', '#18243d'), '#18243d'),
                               anchor='mm', align='center', spacing=6)
    watermark = str(parameters.get('watermark', ''))[:60]
    if watermark:
        drawing.text((width * .96, height * .035), watermark, font=font(max(12, int(width * .025))),
                     fill=(100, 100, 100, 150), anchor='rt')
    output = io.BytesIO()
    result.convert('RGB').save(output, 'PNG')
    return output.getvalue()
