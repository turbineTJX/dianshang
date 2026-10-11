import { useEffect, useRef, useState } from 'react';
import { UploadCloud, Plus, Check, WandSparkles, ArrowRight, Image, UsersRound, Film, Save, SlidersHorizontal, X, Layers3, LoaderCircle, Info, Brush, Eraser } from 'lucide-react';
import { api, post, capabilityNames } from './api';
import type { User, Operation, Asset, Job, Page } from './types';
import { AssetPicker, AssetVisual, Modal } from './components';

type Props = { group: string; operations: Operation[]; assets: Asset[]; initialOperation: string; initialAssets: string[]; initialPrompt?: string; initialBatch?: boolean; user: User; notify: (message: string) => void; refresh: () => Promise<void>; go: (page: Page, operation?: string, assets?: string[]) => void };
const ratioOptions = ['1:1', '3:4', '4:5', '9:16', '16:9'];
const roleNames: Record<string, string> = { product: '商品原图', reference: '参考图', garment: '服装图', person: '模特图', bottom: '下装图', first_frame: '首帧', last_frame: '尾帧', video: '参考视频', mask: '区域蒙版' };

export default function Studio({ group, operations, assets, initialOperation, initialAssets, initialPrompt = '', initialBatch = false, user, notify, refresh, go }: Props) {
  const [operationId, setOperationId] = useState(initialOperation || (group === 'model' ? 'tryon' : group === 'video' ? 'image_to_video' : 'product_scene'));
  const op = operations.find(value => value.id === operationId) || operations[0];
  const [selected, setSelected] = useState<string[]>(initialAssets);
  const [roles, setRoles] = useState<Record<string, string>>({});
  const [extraAssets, setExtraAssets] = useState<Asset[]>([]);
  const allAssets = [...assets, ...extraAssets.filter(a => !assets.some(b => b.id === a.id))];
  const [picker, setPicker] = useState(false);
  const [prompt, setPrompt] = useState(initialPrompt);
  const [ratio, setRatio] = useState('1:1');
  const [resolution, setResolution] = useState(group === 'video' ? '720P' : '2K');
  const [duration, setDuration] = useState(5);
  const [count, setCount] = useState(initialOperation.includes('suite') ? 4 : 1);
  const [batch, setBatch] = useState(initialBatch);
  const [language, setLanguage] = useState('英语');
  const [busy, setBusy] = useState(false);
  const [width, setWidth] = useState(1080);
  const [height, setHeight] = useState(1080);
  const [fit, setFit] = useState('contain');
  const [text, setText] = useState('');
  const [background, setBackground] = useState('#ffffff');
  const [textColor, setTextColor] = useState('#18243d');
  const [watermark, setWatermark] = useState('');
  const [maskOpen, setMaskOpen] = useState(false);
  const [mask, setMask] = useState<File | null>(null);
  const [presetName, setPresetName] = useState<string | null>(null);
  const presetKey = 'studio-presets-' + user.id;
  const [presets, setPresets] = useState<{name: string; operation: string; prompt: string; ratio: string; resolution: string}[]>(() => { try { return JSON.parse(localStorage.getItem(presetKey) || '[]'); } catch { return []; } });
  const fileInput = useRef<HTMLInputElement>(null);
  useEffect(() => { if (!op) return; setSelected(ids => ids.slice(0, op.max_assets)); }, [operationId, op?.max_assets]);
  if (!op) return <p className="muted">正在加载功能配置…</p>;
  const isLocal = op.id === 'local_design';
  const title = group === 'image' ? '图片创作' : group === 'model' ? 'AI 模特' : '视频创作';
  const Icon = group === 'model' ? UsersRound : group === 'video' ? Film : Image;
  const inputAssets = selected.map(id => allAssets.find(a => a.id === id)).filter((a): a is Asset => !!a);
  const units = count * (batch ? selected.length : 1);
  const cost = units * op.price;
  const defaultRole = (index: number, asset: Asset) => asset.kind === 'video' ? 'video' : op.id === 'tryon' ? ['garment', 'person', 'bottom'][index] : op.id === 'first_last_video' ? ['first_frame', 'last_frame'][index] : index === 0 ? 'product' : 'reference';
  const validSelection = batch ? selected.length > 0 : selected.length >= op.min_assets && selected.length <= op.max_assets;
  const disabled = busy || !validSelection || (!selected.length && !prompt.trim()) || units > 20;

  async function upload(files: FileList | File[] | null) {
    if (!files?.length) return;
    setBusy(true);
    try {
      const form = new FormData(); for (const file of Array.from(files)) form.append('files', file);
      form.append('category', group === 'model' ? 'reference' : 'product');
      const added = await api<Asset[]>('/assets/upload', { method: 'POST', body: form });
      setExtraAssets(prev => [...prev, ...added]);
      setSelected(prev => [...prev, ...added.map(a => a.id)].slice(0, op.max_assets));
      notify(`已上传 ${added.length} 个素材`); await refresh();
    } catch (e) { notify((e as Error).message); } finally { setBusy(false); if (fileInput.current) fileInput.current.value = ''; }
  }
  async function submit() {
    setBusy(true);
    try {
      const sources = inputAssets.map((a, i) => ({ id: a.id, role: roles[a.id] || defaultRole(i, a) }));
      if (mask && op.id === 'inpaint') {
        const form = new FormData(); form.append('files', mask); form.append('category', 'reference');
        const uploaded = await api<Asset[]>('/assets/upload', { method: 'POST', body: form });
        sources.push({ id: uploaded[0].id, role: 'mask' });
      }
      const parameters = { aspect_ratio: ratio, size: ratio === '1:1' ? '1024x1024' : ratio === '16:9' ? '1536x1024' : '1024x1536', resolution, duration, language, width, height, fit, text, background, text_color: textColor, watermark };
      const tasks = await post<Job[]>('/jobs', { operation: op.id, inputs: sources, prompt, parameters, count, batch_mode: batch });
      notify(op.configured ? `已创建 ${tasks.length} 个创作任务` : `已保存 ${tasks.length} 个待配置任务，未扣积分`);
      await refresh(); go('jobs');
    } catch (e) { notify((e as Error).message); } finally { setBusy(false); }
  }

  return <><div className="page-heading"><div><span className="eyebrow">{group === 'video' ? 'MOTION STUDIO' : group === 'model' ? 'MODEL STUDIO' : 'IMAGE STUDIO'}</span><h1>{title}</h1><p>{group === 'model' ? '把服装与模特素材，组合成新的展示画面。' : group === 'video' ? '从素材到动态展示，管理完整的视频创作流程。' : '选择一种创作方式，让商品素材发挥更多可能。'}</p></div><button className="secondary" onClick={() => go('works')}><Layers3 size={17} />我的作品</button></div><div className="operation-tabs">{operations.map(item => <button key={item.id} className={op.id === item.id ? 'active' : ''} onClick={() => { setOperationId(item.id); setBatch(false); setMask(null); setRoles({}); setCount(item.id.includes('suite') ? 4 : 1); }}><span>{item.name}</span>{item.id === 'local_design' && <small>免费</small>}</button>)}</div>
  <div className="studio-layout"><section className="panel studio-main"><div className="studio-section-title"><span className="step-number">01</span><div><h2>{op.min_assets === 0 ? '创作方向' : '准备素材'}</h2><p>{op.description}</p></div><Icon size={23} /></div>{op.max_assets > 0 && <><div className={'upload-zone ' + (inputAssets.length ? 'has-files' : '')} onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); void upload(e.dataTransfer.files); }}>
    {inputAssets.length ? <div className="selected-sources">{inputAssets.map((asset, index) => <div key={asset.id} className="source-card"><AssetVisual asset={asset} /><button className="source-remove" onClick={() => setSelected(ids => ids.filter(id => id !== asset.id))} aria-label={'移除' + asset.name}><X size={14} /></button><strong title={asset.name}>{asset.name}</strong><select aria-label={asset.name + '素材用途'} value={roles[asset.id] || defaultRole(index, asset)} onChange={e => setRoles(prev => ({ ...prev, [asset.id]: e.target.value }))}>{Object.entries(roleNames).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></div>)}{selected.length < op.max_assets && <button className="source-add" onClick={() => setPicker(true)}><Plus size={23} /><span>添加素材</span></button>}</div> : <><div className="upload-icon"><UploadCloud size={28} /></div><h3>上传商品或参考素材</h3><p>拖拽文件至此，或选择已有素材</p><div><button className="primary" onClick={() => fileInput.current?.click()} disabled={busy}><Plus size={16} />本地上传</button><button className="secondary" onClick={() => setPicker(true)}>从素材库选择</button></div><small>图片不超过 20 MB · 视频不超过 100 MB</small></>}
  </div><input ref={fileInput} type="file" hidden multiple accept="image/*,video/mp4,video/quicktime,video/webm" onChange={e => void upload(e.target.files)} />{inputAssets.length > 0 && <div className="source-meta"><span>已选 {selected.length} 个素材 · {op.min_assets === op.max_assets ? `需要 ${op.min_assets} 个` : `支持 ${op.min_assets}–${op.max_assets} 个`}</span><button className="text-button" onClick={() => fileInput.current?.click()}>继续上传</button></div>}{op.id === 'tryon' && <div className="inline-tip"><Info size={16} />按顺序选择服装图、模特图；可选第三张下装图。也可在素材下方调整用途。</div>}{op.id === 'inpaint' && inputAssets[0] && <button className="secondary" onClick={() => setMaskOpen(true)}><Brush size={16} />{mask ? '重新绘制区域蒙版' : '绘制修改区域'}</button>}</>}
  <div className="studio-section-title second"><span className="step-number">02</span><div><h2>{isLocal ? '画板与文字' : '描述创作需求'}</h2><p>{isLocal ? '尺寸、背景、文字与水印均可直接处理。' : '描述需要改变的部分，以及必须保留的商品细节。'}</p></div><WandSparkles size={22} /></div>
  {isLocal ? <div className="local-editor"><div className="form-row"><label>画板宽度<input type="number" value={width} min={128} max={4096} onChange={e => setWidth(Number(e.target.value))} /></label><label>画板高度<input type="number" value={height} min={128} max={4096} onChange={e => setHeight(Number(e.target.value))} /></label><label>图片适配<select value={fit} onChange={e => setFit(e.target.value)}><option value="contain">完整显示</option><option value="cover">居中裁剪铺满</option></select></label></div><label>图片文字<textarea placeholder="输入商品标题或卖点，留空则不添加文字" value={text} onChange={e => setText(e.target.value)} maxLength={120} rows={2} /></label><div className="form-row"><label>背景颜色<input type="color" value={background} onChange={e => setBackground(e.target.value)} /></label><label>文字颜色<input type="color" value={textColor} onChange={e => setTextColor(e.target.value)} /></label><label>水印文字<input placeholder="品牌或店铺名" value={watermark} onChange={e => setWatermark(e.target.value)} maxLength={60} /></label></div></div> : <><div className="prompt-heading"><div className="preset-buttons">{presets.filter(p => p.operation === op.id).map((p, i) => <button key={i} className="preset-chip" onClick={() => { setPrompt(p.prompt); setRatio(p.ratio); setResolution(p.resolution); }}>{p.name}</button>)}</div><button className="text-button" onClick={() => setPresetName('')} disabled={!prompt.trim()}><Save size={14} />保存预设</button></div><textarea className="prompt-input" placeholder={group === 'model' ? '例如：自然站姿，柔和棚拍光线，保持衣服原有版型、印花和颜色。' : group === 'video' ? '例如：缓慢推进镜头，商品保持形状不变，柔和自然光，最后停留在商品细节。' : '例如：把商品放在浅色木桌上，背景是明亮的客厅。保持商品形状、颜色和标识不变。'} value={prompt} onChange={e => setPrompt(e.target.value)} maxLength={5000} rows={5} /><div className="prompt-footer"><span>具体描述有助于控制生成方向</span><span>{prompt.length} / 5000</span></div></>}
  </section><aside className="studio-settings"><section className="panel"><div className="section-heading"><h2><SlidersHorizontal size={17} />创作设置</h2></div>{!isLocal && <><label>输出比例</label><div className="ratio-options">{ratioOptions.map(v => <button key={v} className={ratio === v ? 'active' : ''} onClick={() => setRatio(v)}><i style={{ aspectRatio: v.replace(':', '/') }} /><span>{v}</span></button>)}</div><label>分辨率<select value={resolution} onChange={e => setResolution(e.target.value)}>{(group === 'video' ? ['720P', '1080P'] : ['1K', '2K', '4K']).map(v => <option key={v}>{v}</option>)}</select></label>{group === 'video' && <label>视频时长<select value={duration} onChange={e => setDuration(Number(e.target.value))}>{[5, 10, 15, 20, 30].map(v => <option key={v} value={v}>{v} 秒</option>)}</select></label>}{op.id.includes('translate') && <label>目标语言<select value={language} onChange={e => setLanguage(e.target.value)}>{['英语', '德语', '法语', '西班牙语', '日语', '中文'].map(v => <option key={v}>{v}</option>)}</select></label>}</>}
    <label>生成数量<div className="number-control"><button onClick={() => setCount(v => Math.max(1, v - 1))} disabled={count <= 1}>−</button><strong>{count}</strong><button onClick={() => setCount(v => Math.min(20, v + 1))} disabled={count >= 20}>＋</button></div></label>{op.min_assets === 1 && selected.length > 1 && <label className="checkbox-label"><input type="checkbox" checked={batch} onChange={e => setBatch(e.target.checked)} />每个素材分别创建任务</label>}{op.id.includes('suite') && <div className="inline-tip"><Layers3 size={16} />按主图、场景、细节、卖点依次创建套图任务。</div>}
    <div className={'model-status ' + (op.configured ? 'ready' : '')}><span>{op.configured ? <Check size={16} /> : <Info size={16} />}</span><div><strong>{isLocal ? '本地处理' : op.configured ? op.provider_name : '此功能尚未配置模型'}</strong><small>{isLocal ? '立即处理，无需积分' : capabilityNames[op.capability] || op.capability}</small></div></div>{!op.configured && <p className="configuration-note">可先保存需求，配置模型后继续执行。当前不冻结、不扣除积分。</p>}
    <div className="cost-summary"><span>{op.configured ? '预计使用' : '配置后预计使用'}</span><strong>{cost}<small>积分</small></strong><p>{units} 个任务 × {op.price} 积分</p></div><button className="primary full generate-button" disabled={disabled} onClick={() => void submit()}>{busy ? <LoaderCircle size={18} className="spin" /> : <WandSparkles size={18} />}{isLocal ? '生成排版作品' : op.configured ? '开始生成' : '保存待配置任务'}<ArrowRight size={16} /></button>{!validSelection && <small className="validation-hint">请先选择符合数量要求的素材</small>}{units > 20 && <small className="validation-hint">单批最多 20 个任务，请减少数量</small>}</section>{isLocal && inputAssets[0] ? <section className="panel design-preview-panel"><div className="section-heading"><h2>画板预览</h2></div><div className="design-preview" style={{ aspectRatio: `${Math.max(1, width)}/${Math.max(1, height)}`, background }}><img src={inputAssets[0].url} alt="画板预览" style={{ objectFit: fit === 'cover' ? 'cover' : 'contain', padding: fit === 'cover' ? 0 : '5%', height: text ? '84%' : '100%' }} /><span className="preview-watermark">{watermark}</span>{text && <strong style={{color: textColor}}>{text}</strong>}</div><small>实际作品按画板尺寸导出。</small></section> : <section className="workflow-note"><span>创作流程</span><ol><li>选择商品与参考素材</li><li>设置创作方向和参数</li><li>在任务中心跟踪结果</li><li>下载作品或继续创作</li></ol></section>}</aside></div>
  {picker && <Modal title="从素材库选择" close={() => setPicker(false)} wide><div className="modal-body"><AssetPicker assets={allAssets} selected={selected} maximum={op.max_assets} kind={['video_reference', 'video_edit', 'video_translate'].includes(op.id) ? undefined : 'image'} toggle={id => setSelected(ids => ids.includes(id) ? ids.filter(v => v !== id) : [...ids, id])} /></div><div className="modal-actions"><span>已选 {selected.length} / {op.max_assets}</span><button className="primary" onClick={() => setPicker(false)}>确认选择</button></div></Modal>}
  {presetName !== null && <Modal title="保存创作预设" close={() => setPresetName(null)}><div className="modal-body"><label>预设名称<input autoFocus placeholder="例如：明亮客厅场景" value={presetName} onChange={e => setPresetName(e.target.value)} maxLength={30} /></label></div><div className="modal-actions"><button className="secondary" onClick={() => setPresetName(null)}>取消</button><button className="primary" disabled={!presetName.trim()} onClick={() => { const values = [...presets, {name: presetName.trim(), operation: op.id, prompt, ratio, resolution}].slice(-30); localStorage.setItem(presetKey, JSON.stringify(values)); setPresets(values); setPresetName(null); notify('创作预设已保存'); }}>保存</button></div></Modal>}
  {maskOpen && inputAssets[0] && <MaskEditor asset={inputAssets[0]} close={() => setMaskOpen(false)} saved={file => { setMask(file); setSelected(ids => ids.slice(0, op.max_assets - 1)); setMaskOpen(false); notify('区域蒙版已添加'); }} />}
  </>;
}

function MaskEditor({ asset, close, saved }: {asset: Asset; close: () => void; saved: (file: File) => void}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const [brush, setBrush] = useState(40);
  useEffect(() => { const context = canvas.current?.getContext('2d'); if (context) { context.clearRect(0, 0, canvas.current!.width, canvas.current!.height); } }, []);
  function paint(e: React.PointerEvent<HTMLCanvasElement>) { if (!drawing.current || !canvas.current) return; const rect = canvas.current.getBoundingClientRect(); const context = canvas.current.getContext('2d')!; context.fillStyle = 'rgba(75,130,255,.7)'; context.beginPath(); context.arc((e.clientX - rect.left) * canvas.current.width / rect.width, (e.clientY - rect.top) * canvas.current.height / rect.height, brush * canvas.current.width / rect.width / 2, 0, Math.PI * 2); context.fill(); }
  return <Modal title="绘制修改区域" close={close} wide><div className="modal-body"><p className="muted">涂抹需要重绘的区域，蓝色区域将转换成白色蒙版。</p><div className="mask-toolbar"><Brush size={17} /><input type="range" min={5} max={120} value={brush} onChange={e => setBrush(Number(e.target.value))} /><button className="secondary" onClick={() => canvas.current?.getContext('2d')?.clearRect(0, 0, canvas.current.width, canvas.current.height)}><Eraser size={16} />清空</button></div><div className="mask-canvas" style={{aspectRatio: `${asset.width || 1080}/${asset.height || 1080}`}}><img src={asset.url} alt={asset.name} /><canvas ref={canvas} width={asset.width || 1080} height={asset.height || 1080} onPointerDown={e => { drawing.current = true; e.currentTarget.setPointerCapture(e.pointerId); paint(e); }} onPointerMove={paint} onPointerUp={() => { drawing.current = false; }} onPointerCancel={() => { drawing.current = false; }} /></div></div><div className="modal-actions"><button className="secondary" onClick={close}>取消</button><button className="primary" onClick={() => { const source = canvas.current!; const result = document.createElement('canvas'); result.width = source.width; result.height = source.height; const ctx = result.getContext('2d')!; const data = source.getContext('2d')!.getImageData(0, 0, source.width, source.height); for (let index = 0; index < data.data.length; index += 4) { const value = data.data[index + 3] ? 255 : 0; data.data[index] = data.data[index + 1] = data.data[index + 2] = value; data.data[index + 3] = 255; } ctx.putImageData(data, 0, 0); result.toBlob(blob => { if (blob) saved(new File([blob], 'region-mask.png', {type: 'image/png'})); }, 'image/png'); }}>保存蒙版</button></div></Modal>;
}
