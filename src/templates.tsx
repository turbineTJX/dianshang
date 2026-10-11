import { useState } from 'react';
import { ArrowRight, Search, X, Heart, Play, Layers3 } from 'lucide-react';
import { Modal } from './components';
import type { AgentMode } from './types';

export interface CreativeTemplate { id: string; title: string; category: string; mode: AgentMode; operation: string; prompt: string; color: string; art: string; type: string }
const rows = [
  ['商品套图', '投影仪 A+ 图|毛绒玩具详情页|扫地机器人套图|单人沙发 A+ 图|宠物喂食器套图|露营装备套图', 'suite', 'product_suite', 'projector|toy|robot|chair|bottle|tent'],
  ['模特套图', '网球裙套图|宴会礼服裙|夏季吊带裙|皮质夹克套图|儿童 T 恤套图|男士冲锋衣', 'suite', 'clothing_suite', 'dress|dress|dress|jacket|shirt|jacket'],
  ['人物模特', '模特换姿势|模特改身材|模特穿衣|模特换服装|人台换模特|模特换背景', 'free', 'model_pose|smart_edit|tryon|model_replace|mannequin|model_scene', 'model|model|dress|shirt|model|model'],
  ['人物互动', '亲子园艺互动|母亲节礼盒|模特手持香水|情侣对戒展示|商品使用场景|模特展示耳机', 'free', 'product_scene', 'plant|gift|bottle|ring|chair|headphones'],
  ['服饰穿戴', '服装配饰搭配|童模穿搭|鞋子试穿|耳饰佩戴|墨镜佩戴|帽子佩戴', 'free', 'accessory', 'bag|shirt|shoe|ring|glasses|hat'],
  ['宠物互动', '宠物服装试穿|玩具球互动|牵引绳展示|猫玩具展示|宠物模特展示|宠物窝展示', 'free', 'product_scene', 'pet|ball|pet|toy|pet|chair'],
  ['视频创作', '商品环绕运镜|服装动态展示|带货口播短片|生活场景短片|首尾帧过渡|品牌创意短片', 'video', 'image_to_video|model_video|talking_video|image_to_video|first_last_video|text_to_video', 'bottle|dress|model|chair|bag|projector'],
];
const palette = ['#e8e0d3', '#e5e8dc', '#dde6ed', '#f0e0d9', '#ddd8ed', '#e5e9e8'];
export const templates: CreativeTemplate[] = rows.flatMap(([category, titles, mode, operations, arts], row) => titles.split('|').map((title, index) => ({
  id: `${row}-${index}`, title, category, mode: mode as AgentMode,
  operation: operations.split('|')[index] || operations.split('|')[0], color: palette[(row + index) % palette.length], art: arts.split('|')[index],
  type: row === 6 ? '视频' : row < 2 ? '套图' : '图片',
  prompt: `参考「${title}」的创作方向，为我的商品制作${row < 2 ? '主图、场景图、细节图和卖点图，统一视觉风格' : row === 6 ? '自然流畅的电商展示视频' : '自然、清晰的展示图片'}。保留实际商品的外观、颜色、材质和标识。${row === 1 ? '保持模特形象与服装一致。' : ''}`,
})));

function ProductShape({ art, color = '#728777' }: { art: string; color?: string }) {
  if (['model', 'dress', 'shirt', 'jacket'].includes(art)) return <g><ellipse cx="102" cy="39" rx="18" ry="23" fill="#a47b62" /><path d="M84 36q-2-34 20-30q25-1 20 45l-10-17-3-12-24 13" fill="#423a36" /><path d="M89 63l26-2 27 23-9 47-19-17-20 1-27 19-7-40z" fill={color} /><path d="M90 76l-11 11-14 66-11-3 7-62 17-19m42 8 16 16 20 47-9 5-25-43" fill="#c9a18a" /><path d={art === 'dress' ? 'M85 103l34 0 26 81-81 0z' : 'M82 111l44 0-5 70-18 0-4-48-6 48-18 0z'} fill={art === 'dress' ? color : '#ece3d6'} /><path d="M83 180l-2 28 11 0 5-28m12 0 5 28 11 0-4-28" fill="#b18b75" /></g>;
  if (art === 'chair') return <g fill={color}><rect x="48" y="67" width="111" height="66" rx="22" /><rect x="34" y="98" width="142" height="55" rx="18" /><rect x="46" y="138" width="11" height="39" rx="3" /><rect x="156" y="138" width="11" height="39" rx="3" /><path d="M51 130h109" stroke="#ffffff66" /></g>;
  if (art === 'bag' || art === 'gift') return <g><path d="M77 71q0-45 28-45t29 45" fill="none" stroke="#526557" strokeWidth="8" /><path d="M54 68h98l13 106H43z" fill={color} /><path d="M51 79h107M86 82v83" stroke="#ffffff55" strokeWidth="2" /><text x="112" y="134" textAnchor="middle" fill="#ffffffaa" fontSize="10">STUDIO</text></g>;
  if (art === 'projector' || art === 'robot') return <g><rect x="34" y="82" width="145" height="77" rx={art === 'robot' ? 37 : 15} fill="#f7f6f0" /><rect x="42" y="93" width="52" height="55" rx="8" fill={color} /><circle cx="135" cy="119" r="27" fill="#39424a" /><circle cx="135" cy="119" r="20" fill="#647b8d" /><circle cx="135" cy="119" r="13" fill="#2e4459" /><circle cx="129" cy="112" r="5" fill="#bdcedd" /></g>;
  if (art === 'tent') return <g><path d="M19 174L97 56l100 118z" fill={color} /><path d="M54 174l47-85 43 85z" fill="#435447" /><path d="M97 56l47 118M54 174L97 56" stroke="#eee9d4" strokeWidth="3" /></g>;
  if (art === 'plant') return <g><path d="M104 148V54" stroke="#587355" strokeWidth="5" /><ellipse cx="79" cy="88" rx="28" ry="13" transform="rotate(30 79 88)" fill="#799b6c" /><ellipse cx="128" cy="66" rx="30" ry="14" transform="rotate(-25 128 66)" fill="#5b7d56" /><path d="M72 130h65l-12 51H83z" fill="#c0a992" /></g>;
  if (art === 'headphones') return <g fill="none" stroke={color} strokeWidth="16"><path d="M52 122V93a52 52 0 01104 0v29" /><path d="M52 114v45m104-45v45" strokeWidth="29" strokeLinecap="round" /></g>;
  if (art === 'shoe') return <path d="M25 153l15-36 31 17 23-38 39 39 44 12q19 10 14 27H23z" fill={color} stroke="#f8f6f0" strokeWidth="5" />;
  if (art === 'glasses') return <g fill="#4d544f" stroke="#ac9875" strokeWidth="5"><path d="M23 110h68v32q-31 29-59-3zM121 110h68l-9 29q-28 29-59 3z" /><path d="M90 119q15-10 30 0" fill="none" /></g>;
  if (art === 'ring' || art === 'ball') return <g><circle cx="105" cy="119" r="45" fill={art === 'ball' ? color : 'none'} stroke="#b79c67" strokeWidth="12" /><path d="M81 77l25-23 26 23-25 23z" fill="#f8f5e8" stroke="#bca981" strokeWidth="2" /></g>;
  if (art === 'pet' || art === 'toy') return <g fill={color}><ellipse cx="105" cy="130" rx="47" ry="51" /><circle cx="105" cy="78" r="40" /><circle cx="70" cy="50" r="18" /><circle cx="140" cy="50" r="18" /><ellipse cx="105" cy="93" rx="25" ry="18" fill="#eee5d7" /><circle cx="91" cy="75" r="4" fill="#343b37" /><circle cx="120" cy="75" r="4" fill="#343b37" /><ellipse cx="105" cy="87" rx="7" ry="5" fill="#51473e" /></g>;
  if (art === 'hat') return <g fill={color}><path d="M59 128q-6-75 49-75t46 75z" /><ellipse cx="105" cy="134" rx="81" ry="18" /></g>;
  return <g><rect x="78" y="42" width="52" height="17" rx="4" fill="#5d6b60" /><rect x="66" y="58" width="76" height="117" rx="13" fill={color} /><rect x="66" y="93" width="76" height="49" fill="#f8f5e8" /><text x="104" y="113" textAnchor="middle" fontSize="10" fill="#526154">NATURAL</text><text x="104" y="130" textAnchor="middle" fontSize="6" fill="#849086">EVERYDAY ESSENTIAL</text></g>;
}

export function TemplateCover({ template: t, large = false }: {template: CreativeTemplate; large?: boolean}) {
  const fashion = ['model','dress','shirt','jacket'].includes(t.art);
  return <div className={'template-cover ' + (large ? 'large' : '')} style={{ background: t.color }}>
    <svg viewBox="0 0 320 290" role="img" aria-label={`${t.title}排版示意`}><defs><linearGradient id={'g' + t.id}><stop stopColor="#ffffff" stopOpacity=".3" /><stop offset="1" stopColor={t.color} /></linearGradient></defs><rect width="320" height="290" fill={`url(#g${t.id})`} /><rect x="16" y="16" width="181" height="256" rx="3" fill="#ffffff40" /><text x="29" y="38" fontSize="9" fill="#575c57" letterSpacing="2">STUDIO / COLLECTION</text><text x="29" y="63" fontSize="18" fill="#454c43" fontFamily="Georgia,serif">{fashion ? 'Everyday elegance.' : 'Made for living.'}</text><g transform="translate(11 59) scale(.86)"><ellipse cx="104" cy="209" rx="76" ry="9" fill="#0000000d" /><ProductShape art={t.art} color={t.id.endsWith('1') ? '#b49682' : t.id.endsWith('2') ? '#788b96' : '#7f907a'} /></g><rect x="207" y="16" width="97" height="118" rx="3" fill="#ffffff80" /><g transform="translate(206 12) scale(.48)"><ProductShape art={t.art} color="#8f9c90" /></g><rect x="207" y="144" width="97" height="128" rx="3" fill="#ffffffa0" /><text x="219" y="169" fontSize="10" fill="#626b5e">THE DETAILS</text><g transform="translate(206 165) scale(.43)"><ProductShape art={t.art} color="#bdac92" /></g><text x="29" y="255" fontSize="7" fill="#73776d" letterSpacing="1">THOUGHTFULLY DESIGNED</text></svg>
    <span className="cover-type">{t.type === '视频' ? <Play size={11} /> : <Layers3 size={11} />}{t.type}</span>
  </div>;
}

export function Inspiration({ compact = false, useTemplate }: {compact?: boolean; useTemplate: (t: CreativeTemplate) => void}) {
  const [tab, setTab] = useState('Agent 创作');
  const [category, setCategory] = useState('热门');
  const [search, setSearch] = useState('');
  const [preview, setPreview] = useState<CreativeTemplate | null>(null);
  const [favorites, setFavorites] = useState<string[]>(() => { try { return JSON.parse(localStorage.getItem('studio-favorite-templates') || '[]'); } catch { return []; } });
  const categories = ['热门', ...rows.map(row => row[0])];
  const visible = templates.filter(t => (category === '热门' || t.category === category) && (!search || t.title.includes(search)) && (tab !== '我的收藏' || favorites.includes(t.id)) && (tab !== '当季热门' || ['商品套图', '模特套图'].includes(t.category)) && (tab !== 'AI 作图工具' || t.mode === 'free') && (tab !== '设计模板' || t.type === '套图'));
  const sections = category === '热门' ? [...new Set(visible.map(t => t.category))].slice(0, compact ? 2 : 7) : [category];
  return <section className="inspiration-section"><div className="reference-section-title"><h2>灵感库</h2><span>找到适合商品的创作方向</span></div><div className="inspiration-tabs">{['Agent 创作','设计模板','AI 作图工具','当季热门','我的收藏'].map(name => <button key={name} className={tab===name?'active':''} onClick={()=>setTab(name)}>{name}</button>)}{!compact && <div className="library-search"><Search size={15} /><input aria-label="搜索灵感" placeholder="搜索灵感" value={search} onChange={e=>setSearch(e.target.value)} /></div>}</div><div className="category-chips">{categories.map(name => <button key={name} className={category===name?'active':''} onClick={()=>setCategory(name)}>{name}</button>)}</div>
    {sections.map(name => <div className="template-section" key={name}><div className="template-section-heading"><h3>{name}</h3><button className="text-button" onClick={()=>setCategory(name)}>查看更多<ArrowRight size={14} /></button></div><div className="template-grid">{visible.filter(t=>t.category===name).map(t=><article className="template-card" key={t.id}><button className="template-visual" aria-label={`预览${t.title}`} onClick={()=>setPreview(t)}><TemplateCover template={t} /></button><button className={'favorite-template '+(favorites.includes(t.id)?'saved':'')} aria-label={favorites.includes(t.id)?`取消收藏${t.title}`:`收藏${t.title}`} onClick={()=>{const next=favorites.includes(t.id)?favorites.filter(id=>id!==t.id):[...favorites,t.id];setFavorites(next);localStorage.setItem('studio-favorite-templates',JSON.stringify(next));}}><Heart size={15} fill={favorites.includes(t.id)?'currentColor':'none'} /></button><div className="template-caption"><strong>{t.title}</strong><button onClick={()=>useTemplate(t)}>做同款<ArrowRight size={12} /></button></div></article>)}</div></div>)}
    {!visible.length && <div className="gallery-empty">{tab==='我的收藏'?'点击模板上的爱心收藏喜欢的创作方向。':'没有找到匹配的模板。'}<button className="text-button" onClick={()=>{setSearch('');setCategory('热门');setTab('Agent 创作');}}>重置筛选<X size={12} /></button></div>}
    {preview && <Modal title={preview.title} close={()=>setPreview(null)} wide><div className="template-preview"><TemplateCover template={preview} large /><div><span className="eyebrow">CREATIVE DIRECTION</span><h3>{preview.title}</h3><p className="muted">{preview.category} · {preview.type}</p><div className="readonly-box">{preview.prompt}</div><small>封面为排版示意。使用你自己的商品素材生成实际内容。</small><button className="primary full" onClick={()=>{useTemplate(preview);setPreview(null);}}>做同款<ArrowRight size={16} /></button></div></div></Modal>}
  </section>;
}
