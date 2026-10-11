export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const response = await fetch('/api' + path, { ...options, headers, credentials: 'same-origin' });
  if (!response.ok) {
    let message = '请求失败，请稍后重试';
    try {
      const body = await response.json();
      message = typeof body.detail === 'string' ? body.detail : Array.isArray(body.detail) ? body.detail.map((v: { msg: string }) => v.msg).join('；') : message;
    } catch { /* Preserve readable fallback for network and proxy failures. */ }
    throw new Error(message);
  }
  return response.json();
}
export const post = <T>(path: string, body: unknown = {}) => api<T>(path, { method: 'POST', body: JSON.stringify(body) });
export const put = <T>(path: string, body: unknown) => api<T>(path, { method: 'PUT', body: JSON.stringify(body) });
export const date = (value: string) => new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value));
export const size = (value: number) => value >= 1024 * 1024 ? (value / 1024 / 1024).toFixed(1) + ' MB' : Math.round(value / 1024) + ' KB';
export const capabilityNames: Record<string, string> = { 'agent.plan': 'Agent 方案规划', 'link.import': '链接资料解析', 'image.generate': '图片生成', 'image.edit': '图片编辑', 'image.cutout': '抠图与白底', 'image.upscale': '高清放大', 'image.translate': '图片翻译', 'model.tryon': '模特试衣', 'video.generate': '视频生成', 'video.avatar': '带货口播', 'video.reference': '参考视频创作', 'video.edit': '视频编辑', 'video.translate': '视频翻译' };
export const statusNames: Record<string, string> = { awaiting_model: '待配置模型', queued: '排队中', running: '生成中', succeeded: '已完成', failed: '失败', canceled: '已取消', needs_attention: '需要检查' };


