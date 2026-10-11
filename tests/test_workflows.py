import base64
import io
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from backend import db, security, storage, jobs
from backend.main import app
from backend.adapters import REGISTRY
from backend.adapters.base import ModelAdapter, ModelResult, ModelOutput
from backend.adapters.http import render, HttpAdapter


@pytest.fixture
def client(tmp_path, monkeypatch):
    for module in (db, security, storage):
        monkeypatch.setattr(module, 'DATA_DIR', tmp_path)
    with TestClient(app) as test_client:
        result = test_client.post('/api/auth/setup', json={'email': 'owner@example.com', 'password': 'test-password-123', 'name': '测试管理员'})
        assert result.status_code == 200
        yield test_client


def image_bytes(color='red'):
    buffer = io.BytesIO()
    Image.new('RGB', (320, 240), color).save(buffer, 'PNG')
    return buffer.getvalue()


def upload(client):
    result = client.post('/api/assets/upload', files=[('files', ('product.png', image_bytes(), 'image/png'))])
    assert result.status_code == 200, result.text
    return result.json()[0]


def wait_for(client, job_id, states=('succeeded', 'failed'), timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = next(j for j in client.get('/api/jobs').json() if j['id'] == job_id)
        if job['status'] in states:
            return job
        time.sleep(.05)
    raise AssertionError(f'Task did not reach {states}: {job}')


class TestImageAdapter(ModelAdapter):
    __test__ = False
    def submit(self, request):
        return ModelResult('succeeded', outputs=[ModelOutput(base64=base64.b64encode(image_bytes('blue')).decode())])
    def poll(self, remote_id):
        raise AssertionError('Synchronous tasks must not be polled')


class FailureAdapter(ModelAdapter):
    def submit(self, request):
        return ModelResult('failed', error='测试供应商返回失败')
    def poll(self, remote_id):
        raise AssertionError()


def configure(client, monkeypatch, adapter=TestImageAdapter):
    monkeypatch.setitem(REGISTRY, 'test_image', adapter)
    result = client.post('/api/providers', json={'name': '测试协议', 'adapter': 'test_image', 'model': 'test',
                         'base_url': 'https://example.com', 'api_key': 'test-secret-key', 'enabled': True})
    assert result.status_code == 200, result.text
    provider = result.json()
    assert client.put('/api/bindings', json={'bindings': {'image.edit': provider['id']}}).status_code == 200
    return provider


def test_unconfigured_tasks_are_saved_without_charging(client):
    asset = upload(client)
    result = client.post('/api/jobs', json={'operation': 'product_scene', 'inputs': [{'id': asset['id']}], 'prompt': '放到桌面上', 'count': 2})
    assert result.status_code == 200
    assert all(j['status'] == 'awaiting_model' and j['reserved'] == 0 for j in result.json())
    credits = client.get('/api/credits').json()
    assert credits['balance'] == 500 and credits['reserved'] == 0
    assert len(credits['ledger']) == 1


def test_local_design_produces_a_real_downloadable_image(client):
    asset = upload(client)
    result = client.post('/api/jobs', json={'operation': 'local_design', 'inputs': [{'id': asset['id']}],
                         'parameters': {'width': 800, 'height': 1000, 'text': '测试商品', 'background': '#ffffff', 'watermark': '品牌'}})
    assert result.status_code == 200, result.text
    job = wait_for(client, result.json()[0]['id'])
    assert job['status'] == 'succeeded', job
    response = client.get(f"/api/assets/{job['result_ids'][0]}/file")
    image = Image.open(io.BytesIO(response.content))
    assert image.size == (800, 1000)
    assert image.getpixel((0, 0)) == (255, 255, 255)
    assert client.get('/api/credits').json()['balance'] == 500
    assert len(client.get('/api/assets?works=true').json()) == 1


def test_model_decoupling_settlement_and_repeat_settlement(client, monkeypatch):
    asset = upload(client)
    provider = configure(client, monkeypatch)
    assert 'test-secret-key' not in client.get('/api/providers').text
    assert provider['has_key'] is True
    result = client.post('/api/jobs', json={'operation': 'product_scene', 'inputs': [{'id': asset['id']}], 'prompt': '场景'})
    job = wait_for(client, result.json()[0]['id'])
    assert job['status'] == 'succeeded', job
    credits = client.get('/api/credits').json()
    assert credits['balance'] == 490 and credits['reserved'] == 0
    assert sorted(row['action'] for row in credits['ledger']) == ['charge', 'grant', 'reserve']
    jobs.settle(job['id'], 'succeeded', result_ids=job['result_ids'])
    assert client.get('/api/credits').json() == credits
    assert 'provider_snapshot' not in client.get('/api/jobs').text


def test_failed_model_task_releases_frozen_credits(client, monkeypatch):
    asset = upload(client)
    configure(client, monkeypatch, FailureAdapter)
    result = client.post('/api/jobs', json={'operation': 'product_scene', 'inputs': [{'id': asset['id']}], 'prompt': '场景'})
    job = wait_for(client, result.json()[0]['id'])
    assert job['status'] == 'failed'
    credits = client.get('/api/credits').json()
    assert credits['balance'] == 500 and credits['reserved'] == 0
    assert any(row['action'] == 'release' and row['reserved_delta'] == -10 for row in credits['ledger'])


def test_owner_isolation_and_admin_permissions(client):
    asset = upload(client)
    response = client.post('/api/auth/register', json={'email': 'member@example.com', 'password': 'another-password', 'name': '成员'})
    assert response.status_code == 200
    assert client.get(f"/api/assets/{asset['id']}/file").status_code == 404
    assert client.get('/api/providers').status_code == 403
    assert client.post('/api/assets/download', json={'ids': [asset['id']]}).status_code == 404
    assert client.get('/api/assets').json() == []
    assert client.post('/api/jobs', json={'operation': 'product_scene', 'inputs': [{'id': asset['id']}]}).status_code == 400


def test_trash_restore_tags_and_archive(client):
    asset = upload(client)
    assert client.post('/api/assets/tags', json={'ids': [asset['id']], 'tags': ['新品', '杯子']}).status_code == 200
    assert len(client.get('/api/assets?q=新品').json()) == 1
    response = client.post('/api/assets/download', json={'ids': [asset['id']]})
    import zipfile
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert len(archive.namelist()) == 1
        assert Image.open(archive.open(archive.namelist()[0])).size == (320, 240)
    client.post('/api/assets/trash', json={'ids': [asset['id']]})
    assert client.get('/api/assets').json() == []
    assert len(client.get('/api/assets?trash=true').json()) == 1
    client.post('/api/assets/restore', json={'ids': [asset['id']]})
    assert len(client.get('/api/assets').json()) == 1


def test_resume_waiting_job_uses_binding_and_preserves_price(client, monkeypatch):
    asset = upload(client)
    job = client.post('/api/jobs', json={'operation': 'product_scene', 'inputs': [{'id': asset['id']}], 'prompt': '场景'}).json()[0]
    configure(client, monkeypatch)
    client.put('/api/admin/prices', json={'prices': {'product_scene': 30}})
    assert client.post(f"/api/jobs/{job['id']}/resume").status_code == 200
    done = wait_for(client, job['id'])
    assert done['cost'] == 10 and done['status'] == 'succeeded'
    assert client.get('/api/credits').json()['balance'] == 490


def test_concurrent_reservations_cannot_overspend(client, monkeypatch):
    asset = upload(client)
    configure(client, monkeypatch)
    user = client.get('/api/auth/me').json()
    with db.transaction() as conn:
        conn.execute('UPDATE users SET balance=15 WHERE id=?', (user['id'],))
    def create():
        try:
            return jobs.create_jobs(user['id'], 'product_scene', [{'id': asset['id']}], '测试', {}, 1)
        except Exception:
            return None
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: create(), range(2)))
    assert len([r for r in results if r]) == 1
    account = db.one('SELECT * FROM users WHERE id=?', (user['id'],))
    assert account['reserved'] <= account['balance']


def test_http_mapping_sync_and_async_are_protocol_independent(client):
    context = {'model': 'vendor-anything', 'inputs': [{'url': 'https://example.com/image'}], 'parameters': {'duration': 10}}
    assert render({'model': '{{model}}', 'image': '{{inputs[0].url}}', 'duration': '{{parameters.duration}}'}, context) == {
        'model': 'vendor-anything', 'image': 'https://example.com/image', 'duration': 10}
    adapter = HttpAdapter({'config': {'outputs_path': 'output.results', 'url_path': 'image', 'task_id_path': 'output.task_id', 'status_path': 'output.status'}, 'api_key': '', 'base_url': 'https://example.com', 'model': ''})
    assert adapter.parse({'output': {'task_id': 'task-1', 'status': 'RUNNING'}}).remote_id == 'task-1'
    result = adapter.parse({'output': {'task_id': 'task-1', 'status': 'SUCCEEDED', 'results': [{'image': 'https://example.com/result.png'}]}})
    assert result.status == 'succeeded' and result.outputs[0].url.endswith('result.png')


def test_no_fake_payments_or_invalid_uploads(client):
    assert client.post('/api/orders').status_code == 503
    assert client.post('/api/assets/upload', files={'files': ('bad.png', b'not-an-image', 'image/png')}).status_code == 400
    assert client.post('/api/admin/credits', json={'user_id': 'missing', 'amount': -1}).status_code == 422
    assert client.post('/api/jobs', json={'operation': 'tryon', 'inputs': []}).status_code == 400


def test_invalid_batch_is_atomic(client):
    asset = upload(client)
    response = client.post('/api/jobs', json={'operation': 'product_scene', 'batch_mode': True,
                          'inputs': [{'id': asset['id']}, {'id': 'missing'}], 'prompt': '批量'})
    assert response.status_code == 400
    assert client.get('/api/jobs').json() == []


def test_real_http_async_adapter_submits_once_and_persists_output(client):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    submissions = []
    class VendorHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def respond(self, body, code=200, content_type='application/json'):
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.end_headers()
            self.wfile.write(body)
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            submissions.append((self.path, body, self.headers.get('Authorization')))
            self.respond(json.dumps({'ticket': {'id': 'ticket-1', 'phase': 'QUEUED'}}).encode(), 202)
        def do_GET(self):
            if self.path == '/result.png':
                self.respond(image_bytes('blue'), content_type='image/png')
            else:
                address = f'http://127.0.0.1:{self.server.server_port}/result.png'
                self.respond(json.dumps({'ticket': {'id': 'ticket-1', 'phase': 'DONE'}, 'media': [{'download': address}]}).encode())
    server = ThreadingHTTPServer(('127.0.0.1', 0), VendorHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        source = upload(client)
        response = client.post('/api/providers', json={'name': '异步 HTTP 协议验证', 'adapter': 'http_json',
                         'base_url': f'http://127.0.0.1:{server.server_port}', 'model': 'vendor-specific-id',
                         'api_key': 'local-test-only', 'enabled': True,
                         'config': {'submit_path': '/unused', 'poll_path': '/vendor/status/{task_id}',
                                    'operation_overrides': {'product_scene': {'submit_path': '/vendor/create',
                                       'request_template': {'model_id': '{{model}}', 'source': '{{roles.reference.data_url}}'}}},
                                    'task_id_path': 'ticket.id', 'status_path': 'ticket.phase',
                                    'success_states': ['DONE'], 'outputs_path': 'media', 'url_path': 'download'}})
        assert response.status_code == 200, response.text
        client.put('/api/bindings', json={'bindings': {'image.edit': response.json()['id']}})
        task = client.post('/api/jobs', json={'operation': 'product_scene', 'inputs': [{'id': source['id']}], 'prompt': '场景'}).json()[0]
        completed = wait_for(client, task['id'], timeout=8)
        assert completed['status'] == 'succeeded', completed
        assert completed['remote_id'] == 'ticket-1'
        assert len(submissions) == 1
        assert submissions[0][0] == '/vendor/create'
        assert submissions[0][1]['model_id'] == 'vendor-specific-id'
        assert submissions[0][1]['source'].startswith('data:image/png;base64,')
        assert submissions[0][2] == 'Bearer local-test-only'
        output = client.get(f"/api/assets/{completed['result_ids'][0]}/file")
        assert Image.open(io.BytesIO(output.content)).getpixel((0, 0)) == (0, 0, 255)
        assert client.get('/api/credits').json()['balance'] == 490
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
