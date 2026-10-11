# 模型接入契约

业务操作调用 `ModelRequest`，不直接导入任何供应商 SDK。模型连接由管理员配置，能力绑定决定每个操作使用哪一条连接。

## 统一输入

`operation` 为业务功能（如 product_scene、tryon）；`capability` 为通用能力（如 image.edit、model.tryon）；`prompt` 为创作描述；`parameters` 保存比例、分辨率、时长等参数。

`inputs` 中每项包含：

| 字段 | 含义 |
| --- | --- |
| id | 我们系统的素材 ID |
| role | product、reference、garment、person、bottom、first_frame、last_frame、mask、video |
| kind / mime | 素材类型 |
| data_url | 图片的内嵌数据 URL |
| base64 | 不带前缀的图片 Base64 |
| url | 设置公网基础地址后生成的临时签名 URL |

视频不内嵌 Base64。需要公网可访问素材时，设置 `STUDIO_PUBLIC_BASE_URL`。本地的 127.0.0.1 地址不能被供应商读取。临时签名链接有效期一小时，仅授权对应素材。

## 统一输出

`ModelResult.status` 为 running、succeeded、failed；running 必须携带 remote_id；succeeded 必须携带 outputs。每个输出可提供 url 或 base64，后台会下载、验证类型并保存到素材存储。

`submit(request)` 仅提交一次；`poll(remote_id)` 只查询原任务。请求超时或提交结果不明时保留为“需要检查”，不自动重复发送付费生成请求。已知 remote_id 的任务可以继续轮询。

## 通用 JSON 适配器配置

```json
{
  "submit_path": "/generate",
  "poll_path": "/tasks/{task_id}",
  "auth_header": "Authorization",
  "auth_prefix": "Bearer ",
  "timeout": 90,
  "poll_timeout": 900,
  "request_template": {
    "model": "{{model}}",
    "prompt": "{{prompt}}",
    "image": "{{inputs[0].data_url}}",
    "duration": "{{parameters.duration}}"
  },
  "task_id_path": "output.task_id",
  "status_path": "output.task_status",
  "outputs_path": "output.results",
  "url_path": "url",
  "base64_path": "b64_json",
  "success_states": ["SUCCEEDED"],
  "failed_states": ["FAILED", "CANCELED"]
}
```

路径按真实供应商响应调整。`outputs_path` 也可直接指向单个结果 URL，例如 `output.video_url`。同步响应没有状态字段时，只要能提取到作品即可完成。缺少作品、任务 ID 或成功响应的结果映射时会给出明确提示。

完全等于 `{{parameters}}` 的值保留对象类型，`{{parameters.duration}}` 保留数字类型；包含普通文本的模板转换为字符串。模板不执行脚本。

`{{images}}` 为所有图片的 data URL 数组，`{{image_urls}}` 和 `{{video_urls}}` 为对应的签名 URL 数组。可通过 `{{roles.garment.data_url}}`、`{{roles.person.url}}` 等按素材用途读取输入。

同一连接中不同业务操作需要不同参数时，可设置 `operation_overrides`，以操作 ID 为键覆盖 `request_template`、提交路径和响应映射。例如为 tryon 单独设置服装和人物字段，为 inpaint 单独设置图片和 mask 字段。查询时继续使用对应操作的映射。

可设置非敏感额外 `headers`，鉴权密钥使用独立字段。若供应商支持幂等头，配置 `idempotency_header`，值由我们系统的 request_id 提供。

少数接口要求密钥在 JSON 请求体中，可使用 `{{api_key}}` 引用独立加密保存的密钥，设置 `auth_header` 为空字符串即可关闭默认鉴权头。不要直接把真实密钥写在 JSON 配置中。

## 特殊协议扩展

```python
from backend.adapters.base import ModelAdapter, ModelResult

class VendorAdapter(ModelAdapter):
    def submit(self, request):
        # 在此转换参数、进行 multipart 上传或签名。
        # 同步：返回 ModelResult('succeeded', outputs=[...])
        # 异步：返回 ModelResult('running', remote_id='供应商任务ID')
        raise NotImplementedError

    def poll(self, remote_id):
        # 在此查询该供应商的原任务并转换为统一结果。
        raise NotImplementedError
```

在 `backend/adapters/__init__.py` 的 REGISTRY 注册适配器 ID。前端适配器选项自动读取 `/api/providers` 返回的 adapters 列表，注册后即可在配置页面选择；专用字段可放在 JSON 配置中。无需修改现有任务生命周期和积分结算。

## 操作与价格

能力绑定使用能力 ID，不是操作名称。同一供应商连接可服务多个操作，但必须确认真实 API 能满足每种输入和输出格式。兼容图片生成适配器仅服务无参考图的创意生图，不自动兼容试衣、修图或视频。

每个任务保存创建时的价格；排队执行时保存模型连接快照。更改功能价格或连接不会修改已经创建的任务。重试时选择当前绑定，已有 remote_id 的继续查询仍使用原快照。

数据库事务确保冻结余额不超支，结算幂等。生产系统可把适配器的供应商用量字段扩展到任务成本表，分别记录用户积分收费和供应商实际成本。

## 独立文本规划能力 agent.plan

为文本模型创建一条连接，绑定“Agent 方案规划”。默认通过 /v1/chat/completions 请求 JSON 方案；也可以完全替换路径、请求与结果映射。与图片 / 视频生成连接相互独立。

```json
{
  "planner_adapter": "http_json",
  "planner_path": "/v1/chat/completions",
  "planner_response_path": "choices[0].message.content"
}
```

planner_request_template 可使用 {{model}}、{{system}}、{{brief}}、{{mode}}、{{inputs}}、{{parameters}}。其中 inputs 仅包含用户素材 ID，不是图片内容；当前规划主要基于商品名称、描述、卖点与用户说明。

期望响应为对象或 JSON 字符串：

```json
{"steps":[{"title":"商品场景图","operation":"product_scene","prompt":"保留商品外观，生成自然光展示场景","count":2,"parameters":{"ratio":"1:1"}}]}
```

服务端验证功能 ID、素材要求、最多 8 步及总计最多 20 份输出；生成前仍须确认方案。注册专用规划协议可扩展 backend/workspace.py 的 Planner 和 PLANNERS。

## 独立链接资料解析能力 link.import

配置能读取商品 / 视频链接并返回资料的服务，绑定“链接资料解析”。不默认抓取网页，也不调用 LinkFox。

```json
{
  "import_adapter": "http_json",
  "import_path": "/extract",
  "import_request_template": {"url":"{{url}}"},
  "import_response_path": "data",
  "import_fields": {"title":"title","reference_text":"reference_text"}
}
```

服务返回 data.title 与 data.reference_text；后者应包含参考文案、版式与场景说明。也可通过映射改为实际服务的字段。返回有效资料后才标记已解析；失败保留已有内容。商品图片由用户提供，不会自动下载外站图片。专用协议通过 LinkImporter 与 IMPORTERS 扩展。

文本规划和链接解析目前不单独扣平台积分，供应商费用按其实际规则产生。上线收费时需要为这两类请求增加用量与成本记录。
