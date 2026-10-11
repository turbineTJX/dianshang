import json
import re
from urllib.parse import quote, urlparse
import httpx
from .base import ModelAdapter, ModelRequest, ModelOutput, ModelResult
from ..security import decrypt


def lookup(value, path, default=None):
    if not path:
        return value
    current = value
    for part in re.sub(r'\[(\d+)\]', r'.\1', path).split('.'):
        if not part:
            continue
        try:
            current = current[int(part)] if isinstance(current, list) else current[part]
        except (KeyError, IndexError, ValueError, TypeError):
            return default
    return current


def render(template, context):
    """Data substitution only: no eval, scripting or execution of configuration."""
    if isinstance(template, dict):
        return {k: render(v, context) for k, v in template.items()}
    if isinstance(template, list):
        return [render(v, context) for v in template]
    if not isinstance(template, str):
        return template
    full = re.fullmatch(r'\{\{\s*([^{}]+?)\s*\}\}', template)
    if full:
        value = lookup(context, full.group(1))
        if value is None:
            raise ValueError(f'请求映射缺少字段：{full.group(1)}')
        return value
    return re.sub(r'\{\{\s*([^{}]+?)\s*\}\}', lambda m: str(lookup(context, m.group(1), '')), template)


def validate_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError('接口地址必须是有效 HTTP(S) 地址，不能包含账号密码')
    return url


class HttpAdapter(ModelAdapter):
    def __init__(self, provider):
        super().__init__(provider)
        self.config = provider['config'] if isinstance(provider['config'], dict) else json.loads(provider['config'])

    def headers(self, request_id=''):
        headers = dict(self.config.get('headers', {}))
        key = decrypt(self.provider['api_key'])
        auth_header = self.config.get('auth_header', 'Authorization')
        if key and auth_header:
            headers[auth_header] = self.config.get('auth_prefix', 'Bearer ') + key
        if request_id and self.config.get('idempotency_header'):
            headers[self.config['idempotency_header']] = request_id
        return headers

    def send(self, method, path, body=None, request_id=''):
        url = validate_url(self.provider['base_url'].rstrip('/') + '/' + path.lstrip('/'))
        # Deliberately no retry of POST: an ambiguous timeout must not create another paid task.
        with httpx.Client(timeout=float(self.config.get('timeout', 90)), follow_redirects=False, trust_env=False) as client:
            response = client.request(method, url, headers=self.headers(request_id), json=body)
        if response.status_code >= 400:
            # Never persist vendor error bodies that could contain request secrets.
            raise ValueError(f'模型接口返回 HTTP {response.status_code}，请检查配置或供应商后台')
        try:
            return response.json()
        except ValueError:
            raise ValueError('模型接口没有返回 JSON，请检查协议配置')

    def parse(self, data):
        cfg = self.config
        remote_id = str(lookup(data, cfg.get('task_id_path', 'task_id'), '') or '')
        state = str(lookup(data, cfg.get('status_path', 'status'), '')).lower()
        failure = {str(v).lower() for v in cfg.get('failed_states', ['failed', 'error', 'canceled'])}
        if state in failure:
            return ModelResult('failed', remote_id=remote_id, error='供应商任务失败，请在供应商后台查询详细原因')
        raw = lookup(data, cfg.get('outputs_path', 'data'), []) or []
        if not isinstance(raw, list):
            raw = [raw]
        outputs = []
        for value in raw:
            if isinstance(value, str):
                outputs.append(ModelOutput(url=value, mime=cfg.get('output_mime', 'image/png')))
            elif isinstance(value, dict):
                url = lookup(value, cfg.get('url_path', 'url'), '') or ''
                b64 = lookup(value, cfg.get('base64_path', 'b64_json'), '') or ''
                if url or b64:
                    outputs.append(ModelOutput(url=url, base64=b64, mime=cfg.get('output_mime', 'image/png')))
        succeeded = {str(v).lower() for v in cfg.get('success_states', ['succeeded', 'success', 'completed'])}
        if outputs and (not state or state in succeeded):
            return ModelResult('succeeded', outputs=outputs, remote_id=remote_id)
        if state in succeeded:
            return ModelResult('failed', remote_id=remote_id, error='任务已完成但未提取到作品，请检查结果字段映射')
        if remote_id:
            return ModelResult('running', remote_id=remote_id)
        raise ValueError('无法提取作品或任务 ID，请检查响应字段映射')

    def submit(self, request: ModelRequest):
        context = {'model': self.provider['model'], 'operation': request.operation,
                   'capability': request.capability, 'prompt': request.prompt,
                   'inputs': request.inputs, 'parameters': request.parameters,
                   'request_id': request.request_id,
                   'images': [source['data_url'] for source in request.inputs if source['kind'] == 'image'],
                   'image_urls': [source['url'] for source in request.inputs if source['kind'] == 'image'],
                   'video_urls': [source['url'] for source in request.inputs if source['kind'] == 'video'],
                   'roles': {source['role']: source for source in request.inputs},
                   'api_key': decrypt(self.provider['api_key'])}
        template = self.config.get('request_template', {'model': '{{model}}', 'prompt': '{{prompt}}'})
        body = render(template, context)
        return self.parse(self.send('POST', self.config.get('submit_path', '/generate'), body, request.request_id))

    def poll(self, remote_id):
        path = self.config.get('poll_path', '/tasks/{task_id}').replace('{task_id}', quote(remote_id, safe=''))
        result = self.parse(self.send('GET', path))
        result.remote_id = result.remote_id or remote_id
        return result


class OpenAIImageAdapter(HttpAdapter):
    """Only the standard text-to-image endpoint. Editing requires its own HTTP mapping."""
    def submit(self, request: ModelRequest):
        if request.inputs:
            raise ValueError('图片生成协议不接受参考图，请使用通用 HTTP 适配器配置图像编辑接口')
        body = {'model': self.provider['model'], 'prompt': request.prompt,
                'n': 1, 'size': request.parameters.get('size', '1024x1024')}
        return self.parse(self.send('POST', self.config.get('submit_path', '/images/generations'), body, request.request_id))
