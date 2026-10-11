import json
from fastapi.testclient import TestClient
from backend import db
from backend.main import app
from backend.workspace import JsonHttpPlanner
from backend.adapters.http import HttpAdapter
from test_workflows import client, upload, configure, wait_for


def product(client):
    asset = upload(client)
    result = client.post('/api/products', json={'name': '轻量旅行包', 'asset_ids': [asset['id']], 'sku': 'BAG-01',
                         'selling_points': '轻量面料\n可折叠', 'variants': '绿色 / 20L'})
    assert result.status_code == 200, result.text
    return result.json(), asset


def test_public_catalog_and_owned_product_link_library(client):
    p, asset = product(client)
    assert p['asset_ids'] == [asset['id']]
    link = client.post('/api/links', json={'url': 'https://www.amazon.com/dp/example', 'title': '版式参考',
                                         'product_id': p['id']}).json()
    assert link['status'] == 'unparsed'
    updated = client.put('/api/links/' + link['id'], json={'url': link['url'], 'title': link['title'],
                         'product_id': p['id'], 'reference_text': '米色背景，突出轻量与容量。'}).json()
    assert updated['status'] == 'manual'
    assert client.post('/api/links', json={'url': 'javascript:alert(1)'}).status_code == 400
    client.post('/api/auth/logout')
    assert client.get('/api/catalog').status_code == 200
    assert client.get('/api/products').status_code == 401
    client.post('/api/auth/register', json={'email': 'second@example.com', 'name': '其他用户', 'password': 'test-password-123'})
    assert client.get('/api/products').json() == []
    assert client.put('/api/products/' + p['id'], json={'name': '越权'}).status_code == 404
    assert client.post('/api/products', json={'name': '越权图片', 'asset_ids': [asset['id']]}).status_code == 400
    assert client.post('/api/links', json={'url': link['url'], 'product_id': p['id']}).status_code == 404


def test_standard_agent_confirmation_is_idempotent_and_waits_without_charge(client):
    p, _ = product(client)
    result = client.post('/api/agents', json={'mode': 'commerce', 'brief': '生成套图与展示视频', 'product_id': p['id']})
    assert result.status_code == 200, result.text
    agent = result.json()
    assert agent['plan_source'] == 'standard'
    assert len(agent['steps']) == 2 and agent['estimated_cost'] == 100
    assert '轻量面料' in agent['brief']
    revision = {'revision': agent['revision']}
    assert client.post('/api/agents/' + agent['id'] + '/optimize', json=revision).status_code == 409
    confirmed = client.post('/api/agents/' + agent['id'] + '/execute', json=revision)
    assert confirmed.status_code == 200, confirmed.text
    confirmed = confirmed.json()
    assert confirmed['status'] == 'awaiting_model'
    assert sum(len(s['jobs']) for s in confirmed['steps']) == 5
    repeated = client.post('/api/agents/' + agent['id'] + '/execute', json=revision).json()
    assert [s['job_ids'] for s in repeated['steps']] == [s['job_ids'] for s in confirmed['steps']]
    assert len(client.get('/api/jobs').json()) == 5
    credits = client.get('/api/credits').json()
    assert credits['balance'] == 500 and credits['reserved'] == 0
    assert not any(l['action'] == 'reserve' for l in credits['ledger'])
    assert client.put('/api/agents/' + agent['id'] + '/plan', json={'revision': confirmed['revision'], 'steps': [
        {'title': '修改', 'operation': 'product_scene', 'prompt': '改图', 'count': 1}]}).status_code == 409


def test_plan_revision_validation_and_clothing_template(client):
    p, _ = product(client)
    agent = client.post('/api/agents', json={'mode': 'suite', 'operation': 'clothing_suite', 'product_id': p['id']}).json()
    assert agent['steps'][0]['operation'] == 'clothing_suite'
    body = {'revision': agent['revision'], 'steps': [{'title': '场景图', 'operation': 'product_scene', 'prompt': '自然光场景', 'count': 2}]}
    result = client.put('/api/agents/' + agent['id'] + '/plan', json=body)
    assert result.status_code == 200
    assert result.json()['plan_source'] == 'manual'
    assert client.put('/api/agents/' + agent['id'] + '/plan', json=body).status_code == 409
    assert client.post('/api/agents/' + agent['id'] + '/execute', json={'revision': agent['revision']}).status_code == 409
    body['revision'] = result.json()['revision']
    body['steps'][0]['operation'] = 'not_registered'
    assert client.put('/api/agents/' + agent['id'] + '/plan', json=body).status_code == 400
    assert client.post('/api/agents', json={'mode': 'suite', 'brief': '没有图片'}).status_code == 400
    assert client.post('/api/agents', json={'mode': 'replicate', 'product_id': p['id']}).status_code == 400


def test_mixed_model_plan_rolls_back_all_jobs_and_credit_freezes(client, monkeypatch):
    p, _ = product(client)
    provider = configure(client, monkeypatch)
    client.put('/api/bindings', json={'bindings': {'video.generate': provider['id']}})
    user = client.get('/api/auth/me').json()
    with db.transaction() as conn:
        conn.execute('UPDATE users SET balance=40 WHERE id=?', (user['id'],))
    agent = client.post('/api/agents', json={'mode': 'commerce', 'product_id': p['id']}).json()
    result = client.post('/api/agents/' + agent['id'] + '/execute', json={'revision': agent['revision']})
    assert result.status_code == 400
    assert client.get('/api/jobs').json() == []
    assert client.get('/api/auth/me').json()['reserved'] == 0
    assert client.get('/api/agents/' + agent['id']).json()['status'] == 'draft'


def test_text_planner_mapping_is_independent_of_media_protocol(client, monkeypatch):
    p, _ = product(client)
    provider = client.post('/api/providers', json={'name': '独立文本规划', 'adapter': 'http_json', 'model': 'planner-v1',
        'base_url': 'https://planner.example.com', 'enabled': True,
        'config': {'planner_path': '/plan', 'planner_request_template': {'text': '{{brief}}', 'model': '{{model}}'},
                   'planner_response_path': 'plan'}}).json()
    client.put('/api/bindings', json={'bindings': {'agent.plan': provider['id']}})
    calls = []
    def send(self, method, path, body, request_id):
        calls.append((method, path, body))
        return {'plan': {'steps': [{'title': '模型建议的主图', 'operation': 'product_scene', 'prompt': '简洁自然光展示', 'count': 2}]}}
    monkeypatch.setattr(HttpAdapter, 'send', send)
    agent = client.post('/api/agents', json={'mode': 'free', 'product_id': p['id']}).json()
    optimized = client.post('/api/agents/' + agent['id'] + '/optimize', json={'revision': agent['revision']})
    assert optimized.status_code == 200, optimized.text
    assert optimized.json()['plan_source'] == 'model'
    assert calls[0][0:2] == ('POST', '/plan') and calls[0][2]['model'] == 'planner-v1'
    assert optimized.json()['steps'][0]['configured'] is False
    assert client.get('/api/jobs').json() == []


def test_agent_owner_isolation_and_archived_products_keep_history(client):
    p, _ = product(client)
    agent = client.post('/api/agents', json={'mode': 'suite', 'product_id': p['id']}).json()
    assert client.delete('/api/products/' + p['id']).status_code == 200
    assert client.get('/api/products').json() == []
    assert client.get('/api/agents/' + agent['id']).status_code == 200
    client.post('/api/auth/logout')
    client.post('/api/auth/register', json={'email': 'other@example.com', 'name': '其他用户', 'password': 'test-password-123'})
    assert client.get('/api/agents').json() == []
    assert client.get('/api/agents/' + agent['id']).status_code == 404
    assert client.post('/api/agents/' + agent['id'] + '/execute', json={'revision': 1}).status_code == 404


def test_local_agent_completes_and_delivers_real_files(client):
    p, _ = product(client)
    agent = client.post('/api/agents', json={'mode': 'free', 'operation': 'local_design', 'product_id': p['id'],
        'parameters': {'width': 800, 'height': 1000, 'text': '旅行包', 'watermark': 'STUDIO'}}).json()
    confirmed = client.post('/api/agents/' + agent['id'] + '/execute', json={'revision': agent['revision']}).json()
    task_id = confirmed['steps'][0]['job_ids'][0]
    assert wait_for(client, task_id)['status'] == 'succeeded'
    completed = client.get('/api/agents/' + agent['id']).json()
    assert completed['status'] == 'succeeded' and len(completed['result_ids']) == 1
    output = client.get('/api/assets').json()[0]
    assert output['width'] == 800 and output['height'] == 1000
    bundle = client.post('/api/assets/download', json={'ids': completed['result_ids']})
    assert bundle.status_code == 200 and bundle.content.startswith(b'PK')


def test_link_import_remains_unparsed_until_configured_and_verified(client, monkeypatch):
    link = client.post('/api/links', json={'url': 'https://example.com/product'}).json()
    assert client.post('/api/links/' + link['id'] + '/import').status_code == 409
    assert client.get('/api/links').json()[0]['status'] == 'unparsed'
    provider = client.post('/api/providers', json={'name': '资料解析接口', 'adapter': 'http_json', 'enabled': True,
        'base_url': 'https://parser.example.com', 'config': {'import_path': '/metadata',
        'import_request_template': {'source': '{{url}}'}, 'import_response_path': 'metadata',
        'import_fields': {'title': 'name', 'reference_text': 'summary'}}}).json()
    client.put('/api/bindings', json={'bindings': {'link.import': provider['id']}})
    captured = []
    def send(self, method, path, body, request_id):
        captured.append((path, body))
        return {'metadata': {'name': '参考商品', 'summary': '米色背景、侧面大图、两列卖点展示。'}}
    monkeypatch.setattr(HttpAdapter, 'send', send)
    imported = client.post('/api/links/' + link['id'] + '/import')
    assert imported.status_code == 200 and imported.json()['status'] == 'imported'
    assert imported.json()['reference_text'].startswith('米色背景')
    assert captured == [('/metadata', {'source': link['url']})]
    monkeypatch.setattr(HttpAdapter, 'send', lambda *args: {'metadata': {'summary': ''}})
    assert client.post('/api/links/' + link['id'] + '/import').status_code == 502
    assert client.get('/api/links').json()[0]['reference_text'] == imported.json()['reference_text']
