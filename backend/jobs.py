import base64
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from contextlib import nullcontext
from pathlib import Path
import httpx
from fastapi import HTTPException
from . import db
from .catalog import BY_ID, SUITE_ROLES, operation_with_price
from .adapters import get_adapter
from .adapters.base import ModelRequest
from .storage import model_input, save_asset, MAX_VIDEO_BYTES
from .local_image import design


def binding(capability, conn=None):
    sql = 'SELECT p.* FROM providers p JOIN bindings b ON b.provider_id=p.id WHERE b.capability=? AND p.enabled=1'
    row = conn.execute(sql, (capability,)).fetchone() if conn else db.one(sql, (capability,))
    if row:
        value = dict(row)
        value['config'] = json.loads(value['config'])
        return value
    return None


def public_job(row):
    return {**{k: row[k] for k in ('id', 'batch_id', 'operation', 'title', 'prompt', 'status', 'cost', 'reserved',
                                  'error', 'progress', 'attempts', 'created_at', 'updated_at')},
            'inputs': json.loads(row['inputs']), 'parameters': json.loads(row['parameters']),
            'result_ids': json.loads(row['result_ids']), 'remote_id': row['remote_id']}


def validate_inputs(user_id, operation, inputs):
    if not operation['min_assets'] <= len(inputs) <= operation['max_assets']:
        raise HTTPException(400, f"{operation['name']}需要 {operation['min_assets']}–{operation['max_assets']} 个素材")
    for source in inputs:
        asset = db.one('SELECT * FROM assets WHERE id=? AND user_id=? AND deleted=0', (source['id'], user_id))
        if not asset:
            raise HTTPException(400, '素材不存在或已移入回收站')
        video_input = operation['id'] in ('video_reference', 'video_edit', 'video_translate')
        if not video_input and asset['kind'] != 'image':
            raise HTTPException(400, '此功能需要图片素材')
    if operation['id'] in ('video_reference', 'video_edit', 'video_translate') and not any(
        db.one('SELECT kind FROM assets WHERE id=?', (source['id'],))['kind'] == 'video' for source in inputs
    ):
        raise HTTPException(400, '请至少选择一个视频素材')


def create_jobs(user_id, operation_id, inputs, prompt, parameters, count, input_groups=None, connection=None):
    if operation_id not in BY_ID:
        raise HTTPException(400, '未知功能')
    operation = operation_with_price(operation_id)
    groups = input_groups or [inputs]
    for sources in groups:
        validate_inputs(user_id, operation, sources)
    count = max(1, min(count, 20))
    if not prompt.strip() and operation['min_assets'] == 0:
        raise HTTPException(400, '请填写创作描述')
    batch_id = db.uid()
    created = []
    with (nullcontext(connection) if connection is not None else db.transaction()) as conn:
        provider = binding(operation['capability'], conn)
        ready = provider is not None or operation['capability'] == 'local.image'
        user = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
        total = operation['price'] * count * len(groups) if ready else 0
        if user['balance'] - user['reserved'] < total:
            raise HTTPException(400, f'可用积分不足，本次需要 {total} 积分')
        for sequence in range(count * len(groups)):
            index = sequence % count
            group_index = sequence // count
            sources = groups[group_index]
            job_id, date = db.uid(), db.now()
            title = operation['name']
            task_prompt = prompt.strip()
            if operation_id in ('product_suite', 'clothing_suite'):
                role, instruction = SUITE_ROLES[index % len(SUITE_ROLES)]
                title += ' · ' + role
                task_prompt += '\n' + instruction + '。严格保留商品外观、颜色、印花和标识。'
            elif count * len(groups) > 1:
                title += f' · {sequence + 1}'
            snapshot = json.dumps(provider or {}, ensure_ascii=False)
            conn.execute('''INSERT INTO jobs(id,user_id,batch_id,operation,title,prompt,inputs,parameters,status,
                          provider_id,provider_snapshot,cost,reserved,created_at,updated_at)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                         (job_id, user_id, batch_id, operation_id, title, task_prompt,
                          json.dumps(sources, ensure_ascii=False), json.dumps(parameters, ensure_ascii=False),
                          'queued' if ready else 'awaiting_model', provider['id'] if provider else None,
                          snapshot, operation['price'], operation['price'] if ready else 0, date, date))
            if ready and operation['price']:
                db.ledger(conn, user_id, 'reserve', 0, operation['price'], '创作任务冻结积分', job_id)
            created.append(job_id)
    if connection is not None:
        return [public_job(dict(connection.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone())) for job_id in created]
    return [public_job(db.one('SELECT * FROM jobs WHERE id=?', (job_id,))) for job_id in created]


def resume_job(job_id, user_id):
    with db.transaction() as conn:
        row = conn.execute('SELECT * FROM jobs WHERE id=? AND user_id=?', (job_id, user_id)).fetchone()
        if not row:
            raise HTTPException(404, '任务不存在')
        if row['status'] not in ('awaiting_model', 'failed', 'canceled', 'needs_attention'):
            raise HTTPException(409, '此任务当前不能继续或重试')
        op = BY_ID[row['operation']]
        provider = binding(op['capability'], conn)
        if not provider and op['capability'] != 'local.image':
            raise HTTPException(409, '此能力尚未绑定启用的模型接口')
        # A known vendor task is resumed by polling its original snapshot.
        retain_remote = row['status'] == 'needs_attention' and bool(row['remote_id'])
        cost_to_reserve = row['cost'] - row['reserved']
        user = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
        if user['balance'] - user['reserved'] < cost_to_reserve:
            raise HTTPException(400, '可用积分不足')
        if cost_to_reserve:
            db.ledger(conn, user_id, 'reserve', 0, cost_to_reserve, '继续任务冻结积分', job_id)
        conn.execute('''UPDATE jobs SET status='queued',reserved=cost,error='',progress=0,updated_at=?,
                        provider_id=?,provider_snapshot=?,remote_id=? WHERE id=?''',
                     (db.now(), row['provider_id'] if retain_remote else provider['id'] if provider else None,
                      row['provider_snapshot'] if retain_remote else json.dumps(provider or {}, ensure_ascii=False),
                      row['remote_id'] if retain_remote else None, job_id))


def cancel_job(job_id, user_id):
    with db.transaction() as conn:
        row = conn.execute('SELECT * FROM jobs WHERE id=? AND user_id=?', (job_id, user_id)).fetchone()
        if not row:
            raise HTTPException(404, '任务不存在')
        if row['status'] not in ('queued', 'awaiting_model') or row['remote_id']:
            raise HTTPException(409, '已提交供应商的任务不能直接取消')
        if row['reserved']:
            db.ledger(conn, user_id, 'release', 0, -row['reserved'], '取消任务退回冻结积分', job_id)
        conn.execute("UPDATE jobs SET status='canceled',reserved=0,updated_at=? WHERE id=?", (db.now(), job_id))


def settle(job_id, status, error='', result_ids=None):
    with db.transaction() as conn:
        row = conn.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not row or row['status'] in ('succeeded', 'failed', 'canceled'):
            return
        if row['reserved']:
            charge = -row['reserved'] if status == 'succeeded' else 0
            db.ledger(conn, row['user_id'], 'charge' if charge else 'release', charge, -row['reserved'],
                      '作品完成结算' if charge else '任务失败退回冻结积分', job_id)
        conn.execute('UPDATE jobs SET status=?,reserved=0,error=?,result_ids=?,progress=?,updated_at=? WHERE id=?',
                     (status, error, json.dumps(result_ids or []), 100 if status == 'succeeded' else 0, db.now(), job_id))


def attention(job_id, message):
    with db.transaction() as conn:
        conn.execute("UPDATE jobs SET status='needs_attention',error=?,updated_at=? WHERE id=?",
                     (message, db.now(), job_id))


def download_output(output):
    if output.base64:
        value = output.base64.split(',', 1)[-1] if output.base64.startswith('data:') else output.base64
        if len(value) > MAX_VIDEO_BYTES * 1.4:
            raise ValueError('模型输出超过大小限制')
        return base64.b64decode(value, validate=True)
    from .adapters.http import validate_url
    validate_url(output.url)
    content = bytearray()
    with httpx.Client(timeout=60, follow_redirects=False, trust_env=False) as client:
        with client.stream('GET', output.url) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > MAX_VIDEO_BYTES:
                    raise ValueError('模型输出超过大小限制')
    return bytes(content)


class JobRunner:
    def __init__(self):
        self.stop_event = threading.Event()
        self.inflight = set()
        self.lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='studio-job')

    def start(self):
        # Submitted tasks without IDs cannot be safely resubmitted after a process restart.
        with db.transaction() as conn:
            conn.execute("UPDATE jobs SET status='needs_attention',error='服务重启前的提交结果未知，请核对供应商记录后重试' WHERE status='running' AND remote_id IS NULL AND operation!='local_design'")
            conn.execute("UPDATE jobs SET status='queued' WHERE status='running' AND (remote_id IS NOT NULL OR operation='local_design')")
        threading.Thread(target=self.loop, daemon=True, name='studio-scheduler').start()

    def stop(self):
        self.stop_event.set()
        self.pool.shutdown(wait=True, cancel_futures=True)

    def loop(self):
        while not self.stop_event.wait(.5):
            for row in db.rows("SELECT id FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 2"):
                with self.lock:
                    if row['id'] in self.inflight or len(self.inflight) >= 2:
                        continue
                    self.inflight.add(row['id'])
                self.pool.submit(self.run, row['id'])

    def run(self, job_id):
        submitted = False
        try:
            with db.transaction() as conn:
                row = conn.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
                if not row or row['status'] != 'queued':
                    return
                conn.execute("UPDATE jobs SET status='running',progress=10,attempts=attempts+1,updated_at=? WHERE id=?", (db.now(), job_id))
                job = dict(row)
            op = BY_ID[job['operation']]
            sources = json.loads(job['inputs'])
            validate_inputs(job['user_id'], op, sources)
            assets = [db.one('SELECT * FROM assets WHERE id=?', (source['id'],)) for source in sources]
            params = json.loads(job['parameters'])
            if op['capability'] == 'local.image':
                output = design(assets[0], params)
                asset = save_asset(job['user_id'], output, job['title'] + '.png', 'work', source_job=job_id)
                settle(job_id, 'succeeded', result_ids=[asset['id']])
                return
            provider = json.loads(job['provider_snapshot'])
            adapter = get_adapter(provider, job['operation'])
            if job['remote_id']:
                submitted = True
                result = adapter.poll(job['remote_id'])
            else:
                request = ModelRequest(job['operation'], op['capability'], job['prompt'],
                                       [model_input(asset, sources[index].get('role', 'reference')) for index, asset in enumerate(assets)],
                                       params, op['kind'], job_id)
                submitted = True
                result = adapter.submit(request)
            if result.remote_id:
                with db.transaction() as conn:
                    conn.execute('UPDATE jobs SET remote_id=?,progress=35,updated_at=? WHERE id=?', (result.remote_id, db.now(), job_id))
            deadline = time.monotonic() + max(30, min(3600, int(provider.get('config', {}).get('poll_timeout', 900))))
            while result.status == 'running':
                if not result.remote_id:
                    raise ValueError('异步任务缺少供应商任务 ID')
                if self.stop_event.wait(3):
                    return  # Persisted remote ID will be recovered on next startup.
                if time.monotonic() > deadline:
                    attention(job_id, '供应商任务仍未完成，可稍后继续查询原任务')
                    return
                result = adapter.poll(result.remote_id)
            if result.status == 'failed':
                settle(job_id, 'failed', result.error)
                return
            if not result.outputs:
                raise ValueError('模型没有返回作品')
            ids = []
            for index, output in enumerate(result.outputs):
                content = download_output(output)
                asset = save_asset(job['user_id'], content, f"{job['title']} {index + 1}", 'work', source_job=job_id, mime=output.mime, expected_kind=op['kind'])
                ids.append(asset['id'])
            settle(job_id, 'succeeded', result_ids=ids)
        except httpx.HTTPStatusError:
            attention(job_id, '作品下载未完成，请检查结果地址是否有效后继续查询')
        except httpx.RequestError:
            attention(job_id, '连接中断，提交结果可能未知。请核对供应商任务，避免重复生成和计费')
        except Exception as exc:
            if submitted and isinstance(exc, ValueError) and any(text in str(exc) for text in ('提取', 'JSON', '缺少供应商')):
                attention(job_id, str(exc))
            else:
                message = exc.detail if isinstance(exc, HTTPException) else str(exc) if isinstance(exc, ValueError) else '任务处理失败，请检查素材和模型配置'
                settle(job_id, 'failed', message)
        finally:
            with self.lock:
                self.inflight.discard(job_id)
