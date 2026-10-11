"""Protocol registry. New vendor integrations register here, without changing jobs or UI."""
from .base import ModelAdapter
from .http import HttpAdapter, OpenAIImageAdapter

REGISTRY: dict[str, type[ModelAdapter]] = {
    'http_json': HttpAdapter,
    'openai_image': OpenAIImageAdapter,
}


def get_adapter(provider, operation=''):
    adapter = REGISTRY.get(provider['adapter'])
    if not adapter:
        raise ValueError('未注册的模型适配器')
    import json
    config = provider['config'] if isinstance(provider['config'], dict) else json.loads(provider['config'])
    overrides = config.get('operation_overrides', {}).get(operation, {})
    return adapter({**provider, 'config': {**config, **overrides}})
