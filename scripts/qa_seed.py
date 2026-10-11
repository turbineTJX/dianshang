"""Creates disposable QA accounts and original geometric fixtures in data/qa only."""
import io
from pathlib import Path
import httpx
from PIL import Image, ImageDraw

BASE = 'http://127.0.0.1:8011'
client = httpx.Client(base_url=BASE, timeout=20, trust_env=False)
health = client.get('/api/health').json()
account = {'email': 'qa@example.test', 'password': 'Studio-QA-2026', 'name': '示例工作台'}
response = client.post('/api/auth/setup' if health['setup_required'] else '/api/auth/login', json=account)
response.raise_for_status()
directory = Path(__file__).resolve().parent.parent / 'data' / 'qa-fixtures'
directory.mkdir(parents=True, exist_ok=True)


def fixture(index):
    palette = [('#efe6dc', '#c6a88c'), ('#e8edf0', '#8da4b6'), ('#e9ece5', '#a4af96')]
    background, product = palette[index]
    image = Image.new('RGB', (900, 900), background)
    draw = ImageDraw.Draw(image)
    draw.ellipse((190, 630, 725, 740), fill='#ded8cf')
    if index == 0:
        draw.rounded_rectangle((525, 315, 730, 560), radius=95, outline=product, width=42)
        draw.rounded_rectangle((245, 245, 615, 645), radius=60, fill=product)
        draw.ellipse((245, 235, 615, 290), fill='#e9d5bf')
        draw.ellipse((275, 250, 585, 279), fill='#9b7f67')
    elif index == 1:
        draw.rounded_rectangle((220, 270, 675, 670), radius=42, fill=product)
        draw.arc((315, 130, 590, 430), 175, 365, fill='#6b8497', width=26)
        draw.line((285, 325, 285, 635), fill='#aebfc9', width=3)
        draw.line((615, 325, 615, 635), fill='#aebfc9', width=3)
    else:
        draw.rounded_rectangle((422, 345, 478, 685), radius=7, fill='#969f8a')
        draw.ellipse((290, 645, 610, 705), fill='#8c957e')
        draw.polygon([(315, 245), (585, 245), (710, 430), (190, 430)], fill=product)
        draw.ellipse((190, 402, 710, 449), fill='#c4cbb9')
    return image


names = ['示例 · 陶瓷杯', '示例 · 帆布包', '示例 · 桌灯']
if not client.get('/api/assets').json():
    for index, name in enumerate(names):
        image = fixture(index)
        path = directory / f'product-{index + 1}.png'
        image.save(path)
        buffer = io.BytesIO()
        image.save(buffer, 'PNG')
        response = client.post('/api/assets/upload', files={'files': (name + '.png', buffer.getvalue(), 'image/png')}, data={'category': 'product'})
        response.raise_for_status()
        client.post('/api/assets/tags', json={'ids': [response.json()[0]['id']], 'tags': ['示例素材', '商品']} )
print('Disposable QA workspace initialized on port 8011. No model provider configured.')
