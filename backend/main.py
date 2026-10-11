import io
import json
import os
import re
import time
import zipfile
import hmac
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Response, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from . import db, jobs, payments
from .catalog import BY_ID, CAPABILITIES, operation_with_price
from .config import ROOT, DATA_DIR
from .security import current_user, public_user, password_hash, verify_password, start_session, session_hash, encrypt, sign_asset, cipher
from .storage import save_asset, public_asset, download_name, MAX_VIDEO_BYTES
from .adapters import REGISTRY
from .adapters.http import validate_url
from .workspace import router as workspace_router

runner = jobs.JobRunner()


@asynccontextmanager
async def lifespan(app):
    global runner
    db.initialize()
    cipher()
    runner = jobs.JobRunner()
    runner.start()
    yield
    runner.stop()


app = FastAPI(title='商景 Studio API', version='0.1.0', lifespan=lifespan)


@app.middleware('http')
async def origin_guard(request: Request, call_next):
    origin = request.headers.get('origin')
    if origin and request.method not in ('GET', 'HEAD', 'OPTIONS'):
        allowed = {'http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:8000', 'http://localhost:8000'}
        allowed.update(filter(None, os.getenv('STUDIO_ALLOWED_ORIGINS', '').split(',')))
        allowed.add(f"{request.url.scheme}://{request.headers.get('host', '')}")
        if origin not in allowed:
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail': '请求来源不受信任'}, status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    return response


def admin(user=Depends(current_user)):
    if user['role'] != 'admin':
        raise HTTPException(403, '此操作需要管理员权限')
    return user


class Account(BaseModel):
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default='创作者', min_length=1, max_length=40)

    @field_validator('email')
    @classmethod
    def email_valid(cls, value):
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('请输入有效邮箱')
        return value.lower()


class Login(BaseModel):
    email: str
    password: str


class AssetPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    category: str | None = None
    tags: list[str] | None = Field(default=None, max_length=20)


class Selection(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=100)


class TagSelection(Selection):
    tags: list[str] = Field(max_length=20)


class InputAsset(BaseModel):
    id: str
    role: str = Field(default='reference', max_length=40)


class JobRequest(BaseModel):
    operation: str
    inputs: list[InputAsset] = Field(default=[], max_length=6)
    prompt: str = Field(default='', max_length=5000)
    parameters: dict[str, Any] = Field(default={})
    count: int = Field(default=1, ge=1, le=20)
    batch_mode: bool = False


class ProviderRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    adapter: str = 'http_json'
    base_url: str = Field(default='', max_length=500)
    model: str = Field(default='', max_length=120)
    api_key: str | None = Field(default=None, max_length=4096)
    enabled: bool = False
    config: dict[str, Any] = Field(default={})

    @field_validator('adapter')
    @classmethod
    def adapter_valid(cls, value):
        if value not in REGISTRY:
            raise ValueError('未注册的适配器')
        return value

    @field_validator('base_url')
    @classmethod
    def url_valid(cls, value):
        return validate_url(value) if value else ''

    @field_validator('config')
    @classmethod
    def config_valid(cls, value):
        if len(json.dumps(value)) > 50000:
            raise ValueError('配置内容过大')
        for key in value.get('headers', {}):
            if any(secret in key.lower() for secret in ('authorization', 'api-key', 'apikey', 'token', 'secret', 'cookie')):
                raise ValueError('鉴权请使用专用 API Key 字段和 auth_header，不要放入普通请求头')
        return value


class BindingRequest(BaseModel):
    bindings: dict[str, str | None]


class CreditGrant(BaseModel):
    user_id: str
    amount: int = Field(ge=1, le=100000)
    note: str = Field(default='管理员发放积分', max_length=120)


class PriceRequest(BaseModel):
    prices: dict[str, int]


@app.get('/api/health')
def health():
    return {'status': 'ok', 'setup_required': db.one('SELECT COUNT(*) AS n FROM users')['n'] == 0}


def create_account(body, response, setup=False):
    hashed = password_hash(body.password)
    with db.transaction() as conn:
        initialized = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0] > 0
        if setup and initialized:
            raise HTTPException(409, '管理员已创建，请登录')
        if not setup and not initialized:
            raise HTTPException(409, '请先创建管理员')
        if conn.execute('SELECT id FROM users WHERE email=?', (body.email,)).fetchone():
            raise HTTPException(409, '该邮箱已注册')
        user_id = db.uid()
        conn.execute('INSERT INTO users(id,email,name,password,role,created_at) VALUES(?,?,?,?,?,?)',
                     (user_id, body.email, body.name, hashed, 'admin' if setup else 'member', db.now()))
        db.ledger(conn, user_id, 'grant', 500 if setup else 50, 0, '初始测试积分')
    start_session(response, user_id)
    return public_user(db.one('SELECT * FROM users WHERE id=?', (user_id,)))


@app.post('/api/auth/setup')
def setup(body: Account, response: Response):
    return create_account(body, response, True)


@app.post('/api/auth/register')
def register(body: Account, response: Response):
    return create_account(body, response)


@app.post('/api/auth/login')
def login(body: Login, response: Response):
    user = db.one('SELECT * FROM users WHERE email=?', (body.email.lower(),))
    if not user or not verify_password(body.password, user['password']):
        raise HTTPException(401, '邮箱或密码不正确')
    start_session(response, user['id'])
    return public_user(user)


@app.post('/api/auth/logout')
def logout(request: Request, response: Response, user=Depends(current_user)):
    token = request.cookies.get('studio_session', '')
    with db.transaction() as conn:
        conn.execute('DELETE FROM sessions WHERE token=?', (session_hash(token),))
    response.delete_cookie('studio_session', path='/')
    return {'ok': True}


@app.get('/api/auth/me')
def me(user=Depends(current_user)):
    return public_user(user)


@app.get('/api/catalog')
def catalog():
    operations = []
    for operation_id in BY_ID:
        op = operation_with_price(operation_id)
        provider = jobs.binding(op['capability'])
        operations.append({**op, 'configured': bool(provider) or op['capability'] == 'local.image',
                           'provider_name': provider['name'] if provider else None})
    return {'operations': operations, 'capabilities': CAPABILITIES}


@app.get('/api/assets')
def assets(q: str = '', category: str = '', kind: str = '', works: bool = False, trash: bool = False, user=Depends(current_user)):
    sql = 'SELECT * FROM assets WHERE user_id=? AND deleted=?'
    params = [user['id'], int(trash)]
    if works:
        sql += ' AND source_job IS NOT NULL'
    elif category:
        sql += ' AND category=?'
        params.append(category)
    if kind:
        sql += ' AND kind=?'
        params.append(kind)
    if q:
        sql += " AND (name LIKE ? ESCAPE '\\' OR tags LIKE ? ESCAPE '\\')"
        escaped = q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        params.extend(['%' + escaped + '%'] * 2)
    sql += ' ORDER BY created_at DESC LIMIT 1000'
    return [public_asset(a) for a in db.rows(sql, params)]


@app.post('/api/assets/upload')
async def upload(files: list[UploadFile] = File(...), category: str = Form('product'), user=Depends(current_user)):
    if category not in ('product', 'reference', 'collected'):
        raise HTTPException(400, '未知素材分类')
    if len(files) > 20:
        raise HTTPException(400, '单次最多上传 20 个文件')
    result = []
    for file in files:
        content = await file.read(MAX_VIDEO_BYTES + 1)
        result.append(public_asset(save_asset(user['id'], content, file.filename or '素材', category)))
    return result


def owned_asset(asset_id, user):
    asset = db.one('SELECT * FROM assets WHERE id=? AND user_id=?', (asset_id, user['id']))
    if not asset:
        raise HTTPException(404, '素材不存在')
    return asset


@app.get('/api/assets/{asset_id}/file')
def asset_file(asset_id: str, thumbnail: bool = False, download: bool = False, user=Depends(current_user)):
    asset = owned_asset(asset_id, user)
    path = Path(asset['path'])
    if thumbnail and asset['kind'] == 'image':
        path = path.with_suffix('.thumb.webp')
    if not path.exists():
        raise HTTPException(404, '素材文件缺失')
    return FileResponse(path, media_type='image/webp' if thumbnail and asset['kind'] == 'image' else asset['mime'],
                        filename=download_name(asset) if download else None)


@app.get('/api/model-assets/{asset_id}')
def signed_asset(asset_id: str, expires: int, signature: str):
    if expires < time.time() or expires > time.time() + 3700 or not hmac.compare_digest(sign_asset(asset_id, expires), signature):
        raise HTTPException(403, '素材访问授权无效或已过期')
    asset = db.one('SELECT * FROM assets WHERE id=? AND deleted=0', (asset_id,))
    if not asset:
        raise HTTPException(404, '素材不存在')
    return FileResponse(asset['path'], media_type=asset['mime'])


@app.patch('/api/assets/{asset_id}')
def patch_asset(asset_id: str, body: AssetPatch, user=Depends(current_user)):
    owned_asset(asset_id, user)
    changes = body.model_dump(exclude_none=True)
    if changes.get('category') not in (None, 'product', 'reference', 'collected', 'work'):
        raise HTTPException(400, '未知分类')
    if changes:
        with db.transaction() as conn:
            for key, value in changes.items():
                conn.execute(f'UPDATE assets SET {key}=? WHERE id=?',
                             (json.dumps(value, ensure_ascii=False) if key == 'tags' else value, asset_id))
    return public_asset(owned_asset(asset_id, user))


@app.post('/api/assets/tags')
def bulk_tags(body: TagSelection, user=Depends(current_user)):
    for asset_id in body.ids:
        owned_asset(asset_id, user)
    with db.transaction() as conn:
        for asset_id in body.ids:
            conn.execute('UPDATE assets SET tags=? WHERE id=?', (json.dumps(body.tags, ensure_ascii=False), asset_id))
    return {'ok': True}


@app.post('/api/assets/trash')
def trash_assets(body: Selection, user=Depends(current_user)):
    return set_deleted(body, user, True)


@app.post('/api/assets/restore')
def restore_assets(body: Selection, user=Depends(current_user)):
    return set_deleted(body, user, False)


def set_deleted(body, user, deleted):
    for asset_id in body.ids:
        owned_asset(asset_id, user)
    with db.transaction() as conn:
        for asset_id in body.ids:
            conn.execute('UPDATE assets SET deleted=? WHERE id=?', (int(deleted), asset_id))
    return {'ok': True}


@app.post('/api/assets/download')
def download_assets(body: Selection, user=Depends(current_user)):
    selected = [owned_asset(asset_id, user) for asset_id in body.ids]
    if sum(a['size'] for a in selected) > 250 * 1024 * 1024:
        raise HTTPException(400, '单次打包不能超过 250 MB，请分批下载')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_STORED) as archive:
        for index, asset in enumerate(selected):
            safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', download_name(asset))
            archive.write(asset['path'], f"{index + 1:03d}_{safe_name}")
    buffer.seek(0)
    return StreamingResponse(buffer, media_type='application/zip', headers={'Content-Disposition': 'attachment; filename="studio-assets.zip"'})


@app.get('/api/jobs')
def list_jobs(user=Depends(current_user)):
    return [jobs.public_job(row) for row in db.rows('SELECT * FROM jobs WHERE user_id=? ORDER BY created_at DESC LIMIT 500', (user['id'],))]


@app.post('/api/jobs')
def create_job(body: JobRequest, user=Depends(current_user)):
    sources = [source.model_dump() for source in body.inputs]
    if body.batch_mode:
        op = BY_ID.get(body.operation)
        if not op or op['min_assets'] > 1 or not sources:
            raise HTTPException(400, '此功能不能逐素材批量执行，请使用单任务多参考图')
        if len(sources) * body.count > 20:
            raise HTTPException(400, '单批最多 20 个任务')
        return jobs.create_jobs(user['id'], body.operation, [], body.prompt, body.parameters, body.count,
                                input_groups=[[source] for source in sources])
    return jobs.create_jobs(user['id'], body.operation, sources, body.prompt, body.parameters, body.count)


@app.post('/api/jobs/{job_id}/resume')
def resume(job_id: str, user=Depends(current_user)):
    jobs.resume_job(job_id, user['id'])
    return {'ok': True}


@app.post('/api/jobs/{job_id}/cancel')
def cancel(job_id: str, user=Depends(current_user)):
    jobs.cancel_job(job_id, user['id'])
    return {'ok': True}


def public_provider(row):
    return {**{key: row[key] for key in ('id', 'name', 'adapter', 'base_url', 'model', 'created_at')},
            'enabled': bool(row['enabled']), 'has_key': bool(row['api_key']), 'config': json.loads(row['config'])}


@app.get('/api/providers')
def list_providers(user=Depends(admin)):
    providers = [public_provider(row) for row in db.rows('SELECT * FROM providers ORDER BY created_at')]
    return {'providers': providers, 'bindings': {r['capability']: r['provider_id'] for r in db.rows('SELECT * FROM bindings')},
            'capabilities': CAPABILITIES, 'adapters': list(REGISTRY)}


@app.post('/api/providers')
def add_provider(body: ProviderRequest, user=Depends(admin)):
    provider_id = db.uid()
    write_provider(provider_id, body)
    return public_provider(db.one('SELECT * FROM providers WHERE id=?', (provider_id,)))


@app.put('/api/providers/{provider_id}')
def update_provider(provider_id: str, body: ProviderRequest, user=Depends(admin)):
    if not db.one('SELECT id FROM providers WHERE id=?', (provider_id,)):
        raise HTTPException(404, '配置不存在')
    write_provider(provider_id, body)
    return public_provider(db.one('SELECT * FROM providers WHERE id=?', (provider_id,)))


def write_provider(provider_id, body):
    if body.enabled and not body.base_url:
        raise HTTPException(400, '启用前请填写接口地址')
    previous = db.one('SELECT * FROM providers WHERE id=?', (provider_id,))
    key = previous['api_key'] if previous and body.api_key is None else encrypt(body.api_key or '')
    with db.transaction() as conn:
        conn.execute('''INSERT INTO providers VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                      name=excluded.name,adapter=excluded.adapter,model=excluded.model,base_url=excluded.base_url,
                      api_key=excluded.api_key,enabled=excluded.enabled,config=excluded.config''',
                     (provider_id, body.name, body.adapter, body.model, body.base_url, key, int(body.enabled),
                      json.dumps(body.config, ensure_ascii=False), previous['created_at'] if previous else db.now()))


@app.put('/api/bindings')
def update_bindings(body: BindingRequest, user=Depends(admin)):
    with db.transaction() as conn:
        for capability, provider_id in body.bindings.items():
            if capability not in CAPABILITIES:
                raise HTTPException(400, '未知能力')
            if provider_id and not conn.execute('SELECT id FROM providers WHERE id=?', (provider_id,)).fetchone():
                raise HTTPException(400, '模型配置不存在')
            conn.execute('INSERT INTO bindings VALUES(?,?) ON CONFLICT(capability) DO UPDATE SET provider_id=excluded.provider_id',
                         (capability, provider_id or None))
    return {'ok': True}


@app.get('/api/credits')
def credits(user=Depends(current_user)):
    return {'balance': user['balance'], 'reserved': user['reserved'],
            'available': user['balance'] - user['reserved'], 'payment_configured': False,
            'ledger': db.rows('SELECT action,delta,reserved_delta,balance,note,created_at,job_id FROM ledger WHERE user_id=? ORDER BY created_at DESC LIMIT 200', (user['id'],))}


@app.post('/api/orders')
def checkout(user=Depends(current_user)):
    return payments.gateway.create_checkout(db.uid(), 0)


@app.get('/api/admin/users')
def list_users(user=Depends(admin)):
    return [public_user(row) for row in db.rows('SELECT * FROM users ORDER BY created_at')]


@app.post('/api/admin/credits')
def grant_credits(body: CreditGrant, user=Depends(admin)):
    with db.transaction() as conn:
        if not conn.execute('SELECT id FROM users WHERE id=?', (body.user_id,)).fetchone():
            raise HTTPException(404, '成员不存在')
        db.ledger(conn, body.user_id, 'grant', body.amount, 0, body.note)
    return {'ok': True}


@app.put('/api/admin/prices')
def prices(body: PriceRequest, user=Depends(admin)):
    for operation_id, value in body.prices.items():
        if operation_id not in BY_ID or not 0 <= value <= 100000 or operation_id == 'local_design' and value != 0:
            raise HTTPException(400, '价格配置不合法，本地排版保持免费')
    with db.transaction() as conn:
        conn.execute("INSERT INTO settings VALUES('prices',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(body.prices),))
    return {'ok': True}


@app.get('/api/stats')
def stats(user=Depends(current_user)):
    return {'assets': db.one('SELECT COUNT(*) AS n FROM assets WHERE user_id=? AND deleted=0 AND source_job IS NULL', (user['id'],))['n'],
            'works': db.one('SELECT COUNT(*) AS n FROM assets WHERE user_id=? AND deleted=0 AND source_job IS NOT NULL', (user['id'],))['n'],
            'active': db.one("SELECT COUNT(*) AS n FROM jobs WHERE user_id=? AND status IN ('queued','running')", (user['id'],))['n'],
            'waiting': db.one("SELECT COUNT(*) AS n FROM jobs WHERE user_id=? AND status='awaiting_model'", (user['id'],))['n'],
            'configured': len([c for c in CAPABILITIES if jobs.binding(c)]), 'total_capabilities': len(CAPABILITIES)}


app.include_router(workspace_router)

if (ROOT / 'dist').exists():
    app.mount('/', StaticFiles(directory=ROOT / 'dist', html=True), name='frontend')
