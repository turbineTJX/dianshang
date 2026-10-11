import base64
import io
import json
import time
from pathlib import Path
from PIL import Image, ImageOps
from fastapi import HTTPException
from . import db
from .config import DATA_DIR, PUBLIC_BASE_URL
from .security import sign_asset, cipher

Image.MAX_IMAGE_PIXELS = 32_000_000
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_VIDEO_BYTES = 100 * 1024 * 1024


def save_asset(user_id, content, name, category='product', tags=None, source_job=None, mime='', expected_kind=None):
    if len(content) > MAX_VIDEO_BYTES:
        raise HTTPException(413, '视频不能超过 100 MB')
    width = height = None
    try:
        image = Image.open(io.BytesIO(content))
        image.load()
        image = ImageOps.exif_transpose(image)
        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(413, '图片不能超过 20 MB')
        width, height = image.size
        if width * height > 32_000_000:
            raise HTTPException(413, '图片总像素不能超过 3200 万')
        normalized = io.BytesIO()
        image.save(normalized, 'PNG')
        content, kind, ext, mime = normalized.getvalue(), 'image', '.png', 'image/png'
        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(413, '处理后的图片超过 20 MB，请缩小图片尺寸后上传')
    except HTTPException:
        raise
    except Exception:
        # MP4 and MOV are accepted only with their container signature, not a user supplied suffix.
        if len(content) > 12 and content[4:8] == b'ftyp':
            kind, ext, mime = 'video', '.mp4', 'video/mp4'
        elif content[:4] == b'\x1aE\xdf\xa3':
            kind, ext, mime = 'video', '.webm', 'video/webm'
        else:
            raise HTTPException(400, '请选择有效的图片或 MP4 / MOV / WebM 视频')
    if expected_kind and kind != expected_kind:
        raise ValueError('模型输出类型与功能要求不符，请检查接口映射')
    asset_id = db.uid()
    directory = DATA_DIR / 'uploads' / user_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (asset_id + ext)
    path.write_bytes(content)
    # Preview uses the same ownership checked endpoint as the original file.
    if kind == 'image':
        preview = image.copy()
        preview.thumbnail((640, 640))
        preview.save(path.with_suffix('.thumb.webp'), 'WEBP', quality=85)
    try:
        with db.transaction() as conn:
            conn.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                         (asset_id, user_id, Path(name).name[:180], kind, category,
                          json.dumps(tags or [], ensure_ascii=False), str(path), mime,
                          len(content), width, height, source_job, 0, db.now()))
    except Exception:
        path.unlink(missing_ok=True)
        path.with_suffix('.thumb.webp').unlink(missing_ok=True)
        raise
    return db.one('SELECT * FROM assets WHERE id=?', (asset_id,))


def public_asset(asset):
    return dict(id=asset['id'], name=asset['name'], kind=asset['kind'], category=asset['category'],
                tags=json.loads(asset['tags']), size=asset['size'], width=asset['width'], height=asset['height'],
                source_job=asset['source_job'], created_at=asset['created_at'],
                url=f"/api/assets/{asset['id']}/file", thumbnail=f"/api/assets/{asset['id']}/file?thumbnail=1")


def download_name(asset):
    name = asset['name']
    suffix = Path(name).suffix.lower()
    if suffix in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.heic', '.mp4', '.mov', '.webm'):
        name = name[:-len(suffix)]
    return name + Path(asset['path']).suffix


def model_input(asset, role):
    url = ''
    if PUBLIC_BASE_URL:
        cipher()
        expires = int(time.time()) + 3600
        signature = sign_asset(asset['id'], expires)
        url = f"{PUBLIC_BASE_URL}/api/model-assets/{asset['id']}?expires={expires}&signature={signature}"
    raw = Path(asset['path']).read_bytes()
    b64 = base64.b64encode(raw).decode() if asset['kind'] == 'image' else ''
    return dict(id=asset['id'], role=role, kind=asset['kind'], mime=asset['mime'], url=url,
                base64=b64, data_url=f"data:{asset['mime']};base64,{b64}" if b64 else '',
                width=asset['width'], height=asset['height'])
