import { useEffect, useRef, useState } from 'react';
import { Lightbulb, ShoppingBag, Film, Link, Bot, Plus, ChevronDown, ArrowRight, ArrowUpRight, WandSparkles, Eraser, Mic, Images, X, LoaderCircle, FolderOpen, SlidersHorizontal, Upload, Check } from 'lucide-react';
import { api, post } from './api';
import { AssetPicker, AssetVisual, Modal } from './components';
import { Inspiration, TemplateCover, templates, type CreativeTemplate } from './templates';
import type { AgentMode, Asset, User, Navigate, AgentSession, Product, ProductLink, LaunchOptions, Operation } from './types';

const modes: {id: AgentMode; name: string; icon: typeof Lightbulb; placeholder: string}[] = [
  {id:'free',name:'自由创作',icon:Lightbulb,placeholder:'描述你的创意，或上传商品图片，开始创作…'},
  {id:'suite',name:'套图 Agent',icon:ShoppingBag,placeholder:'上传商品图，告诉我商品卖点和风格，一次创建主图、场景图、细节图与卖点图'},
  {id:'video',name:'视频 Agent',icon:Film,placeholder:'上传商品素材，描述视频的场景、运镜和动作，例如：让镜头缓慢环绕商品展示细节'},
  {id:'replicate',name:'链接复刻',icon:Link,placeholder:'先选择或上传商品图，再粘贴要参考的 Amazon 等商品链接'},
  {id:'commerce',name:'电商 Agent',icon:Bot,placeholder:'选择商品并描述需求，组合生成商品套图与展示视频'},
];

export function Tools({ all = false, go }: {all?: boolean; go: Navigate}) {
  const primary = [
    {title:'电商套图',description:'一张商品图，生成电商套图',op:'product_suite',page:'image' as const,cover:templates[0],tag:'套图 Agent'},
    {title:'智能修图',description:'输入编辑指令，轻松完成修图',op:'smart_edit',page:'image' as const,cover:templates[4],tag:'图片创作'},
    {title:'AI 视频',description:'商品素材生成电商展示视频',op:'image_to_video',page:'video' as const,cover:templates[36],tag:'视频 Agent'},
  ];
  const shortcuts=[
    {name:'AI 模特',desc:'服装试穿与模特展示',icon:WandSparkles,page:'model' as const,op:'tryon'},
    {name:'图转视频',desc:'上传商品图，生成视频',icon:Film,page:'video' as const,op:'image_to_video'},
    {name:'批量生图',desc:'多商品素材，批量创作',icon:Images,page:'image' as const,op:'product_scene',batch:true},
    {name:'局部消除',desc:'轻松移除画面中的元素',icon:Eraser,page:'image' as const,op:'erase'},
    {name:'带货口播',desc:'人物素材与商品文案结合',icon:Mic,page:'video' as const,op:'talking_video'},
    {name:'视频复刻',desc:'参考视频，创建商品短片',icon:Link,page:'video' as const,op:'video_reference'},
  ];
  return <section className="reference-tools"><div className="reference-section-title"><h2>创作工具</h2><button className="text-button" onClick={()=>go(all?'image':'tools')}>{all?'打开图片工作台':'查看全部工具'}<ArrowRight size={14}/></button></div><div className="reference-feature-grid">{primary.map((t,i)=><button className={'reference-feature feature-'+i} key={t.title} onClick={()=>go(t.page,t.op)}><div><span>{t.tag}</span><h3>{t.title}</h3><p>{t.description}</p><strong>进入主功能<ArrowUpRight size={15}/></strong></div><div className="feature-preview"><TemplateCover template={t.cover}/>{i===2&&<i><Film size={20}/></i>}</div></button>)}</div><div className="shortcut-grid">{shortcuts.map(t=><button key={t.name} onClick={()=>go(t.page,t.op,[],{batch:t.batch})}><span><t.icon size={22}/></span><div><h3>{t.name}</h3><p>{t.desc}</p></div><ArrowUpRight size={15}/></button>)}</div></section>;
}

type Props={user:User|null;assets:Asset[];operations:Operation[];launch:LaunchOptions;go:Navigate;signIn:()=>void;notify:(v:string)=>void;refresh:()=>Promise<void>};
export default function Home({user,assets,operations,launch,go,signIn,notify,refresh}:Props) {
  const template = templates.find(t=>t.id===launch.template);
  const [mode,setMode]=useState<AgentMode>(launch.mode||template?.mode||'free');
  const [brief,setBrief]=useState(launch.prompt||template?.prompt||'');
  const [selected,setSelected]=useState<string[]>([]);
  const [extra,setExtra]=useState<Asset[]>([]);
  const [picker,setPicker]=useState(false);
  const [addMenu,setAddMenu]=useState(false);
  const [settings,setSettings]=useState(false);
  const [products,setProducts]=useState<Product[]>([]);
  const [links,setLinks]=useState<ProductLink[]>([]);
  const [productId,setProductId]=useState(launch.productId||'');
  const [linkId,setLinkId]=useState(launch.linkId||'');
  const [productPicker,setProductPicker]=useState(false);
  const [linkPicker,setLinkPicker]=useState(false);
  const [ratio,setRatio]=useState('1:1');
  const [language,setLanguage]=useState('中文');
  const [busy,setBusy]=useState(false);
  const [operation,setOperation]=useState(template?.operation||'');
  const file=useRef<HTMLInputElement>(null);
  const allAssets=[...assets,...extra.filter(a=>!assets.some(b=>b.id===a.id))];
  const chosenProduct=products.find(p=>p.id===productId);
  const images=selected.length?selected:chosenProduct?.asset_ids.slice(0,6)||[];
  const current=modes.find(m=>m.id===mode)!;
  useEffect(()=>{if(user)Promise.all([api<Product[]>('/products'),api<ProductLink[]>('/links')]).then(([p,l])=>{setProducts(p);setLinks(l);}).catch(e=>notify(e.message));},[user?.id]);
  async function upload(files:FileList|null){
    if(!files?.length)return;
    setBusy(true);
    try{const data=new FormData();Array.from(files).forEach(f=>data.append('files',f));data.append('category','product');const result=await api<Asset[]>('/assets/upload',{method:'POST',body:data});setExtra(v=>[...v,...result]);setSelected(v=>[...v,...result.map(a=>a.id)].slice(0,6));await refresh();}catch(e){notify((e as Error).message);}finally{setBusy(false);if(file.current)file.current.value='';}
  }
  function useTemplate(t:CreativeTemplate){setBrief(t.prompt);setMode(t.mode);setOperation(t.operation);window.scrollTo({top:0,behavior:'smooth'});}
  async function create(){
    if(!user){signIn();return;}
    setBusy(true);
    try{
      let reference=linkId;
      if(mode==='replicate'&&!reference){const match=brief.match(/https?:\/\/[^\s]+/);if(!match)throw new Error('请粘贴完整商品链接，或从链接库选择');const link=await post<ProductLink>('/links',{url:match[0],title:'创作参考链接',product_id:productId||null});reference=link.id;setLinkId(reference);}
      const session=await post<AgentSession>('/agents',{mode,brief,input_ids:images,product_id:productId||null,link_id:reference||null,operation:mode==='free'?operation:mode==='suite'&&operation==='clothing_suite'?operation:'',parameters:{ratio,language,resolution:mode==='video'?'720P':'2K',duration:5,template_id:template?.id||''}});
      go('agents',session.id);notify('已创建方案，请确认后开始生成');
    }catch(e){notify((e as Error).message);}finally{setBusy(false);}
  }
  const requiresImage=['suite','commerce','replicate'].includes(mode);
  const valid=!!(brief.trim()||images.length) && (!requiresImage||images.length>0);
  const estimated=mode==='commerce'?4*(operations.find(o=>o.id==='product_suite')?.price||10)+(operations.find(o=>o.id==='image_to_video')?.price||60):mode==='suite'||mode==='replicate'?4*(operations.find(o=>o.id==='product_suite')?.price||10):mode==='video'?operations.find(o=>o.id==='image_to_video')?.price||60:operations.find(o=>o.id===(operation||'smart_edit'))?.price||10;
  return <><section className="agent-hero"><h1>从一个想法，开始电商创作</h1><div className="agent-mode-tabs" role="tablist" aria-label="创作模式">{modes.map(m=><button role="tab" aria-selected={mode===m.id} className={mode===m.id?'active':''} key={m.id} onClick={()=>{setMode(m.id);setOperation('');}}><m.icon size={16}/>{m.name}</button>)}</div><div className={'agent-composer '+(images.length?'has-inputs':'')}><textarea aria-label="创作需求" placeholder={current.placeholder} maxLength={5000} value={brief} onChange={e=>setBrief(e.target.value)}/>{(images.length>0||chosenProduct||linkId)&&<div className="composer-assets">{chosenProduct&&<span className="selected-product"><ShoppingBag size={14}/>{chosenProduct.name}<button aria-label="取消商品" onClick={()=>setProductId('')}><X size={13}/></button></span>}{images.map(id=>{const a=allAssets.find(a=>a.id===id);return a&&<div className="composer-image" key={id}><AssetVisual asset={a}/><button aria-label={`移除${a.name}`} onClick={()=>{setSelected(images.filter(i=>i!==id));setProductId('');}}><X size={12}/></button></div>;})}{linkId&&<span className="selected-product"><Link size={14}/>{links.find(l=>l.id===linkId)?.title||'已添加参考链接'}<button aria-label="取消链接" onClick={()=>setLinkId('')}><X size={13}/></button></span>}</div>}
    <div className="composer-bottom"><div className="composer-actions"><div className="composer-menu"><button className="secondary small" onClick={()=>user?setAddMenu(!addMenu):signIn()}><Plus size={17}/>{mode==='replicate'?'上传商品图':'添加'}<ChevronDown size={12}/></button>{addMenu&&<div className="popover-menu"><button onClick={()=>{file.current?.click();setAddMenu(false);}}><Upload size={15}/>上传商品图</button><button onClick={()=>{setPicker(true);setAddMenu(false);}}><FolderOpen size={15}/>从素材库选择</button><button onClick={()=>{setProductPicker(true);setAddMenu(false);}}><ShoppingBag size={15}/>从商品库选择</button><button onClick={()=>{setLinkPicker(true);setAddMenu(false);}}><Link size={15}/>从链接库选择</button></div>}</div><button className="composer-setting" onClick={()=>setSettings(!settings)}><SlidersHorizontal size={14}/>{mode==='replicate'?'更多建库方式':'智能模式'}<ChevronDown size={12}/></button></div><div className="composer-submit"><small>{valid?`预计 ${estimated} 积分`:'先描述需求或添加素材'}</small><button className="primary" disabled={busy||(!valid&&!!user)} onClick={create}>{busy?<LoaderCircle className="spin" size={16}/>:null}{mode==='replicate'?'开始参考创作':mode==='free'?'去创作':'创建方案'}<ArrowRight size={17}/></button></div></div>{settings&&<div className="composer-options"><label>输出比例<select value={ratio} onChange={e=>setRatio(e.target.value)}>{['1:1','3:4','4:5','9:16','16:9'].map(v=><option key={v}>{v}</option>)}</select></label><label>文案语言<select value={language} onChange={e=>setLanguage(e.target.value)}>{['中文','英语','日语','德语','法语','西班牙语'].map(v=><option key={v}>{v}</option>)}</select></label><div><p>{mode==='replicate'?'链接会入库保存。请补充参考文案或上传参考图，当前没有自动抓取网页内容。':'先建立可编辑的标准方案，确认后开始生成。'}</p><button className="text-button" onClick={()=>go('products')}>新建商品资料<ArrowRight size={12}/></button></div></div>}</div><input ref={file} type="file" accept="image/*" multiple hidden onChange={e=>upload(e.target.files)}/><div className="composer-suggestions"><span>试试：</span>{['自然光商品场景','极简风格商品套图','商品环绕展示视频'].map((s,i)=><button key={s} onClick={()=>{setMode((['free','suite','video'] as AgentMode[])[i]);setBrief(s+'，保留商品真实外观和标识。');setOperation('');}}>{s}</button>)}</div></section><Tools go={go}/><Inspiration compact useTemplate={useTemplate}/>
    {picker&&<Modal title="选择商品素材" close={()=>setPicker(false)} wide><div className="modal-body"><AssetPicker assets={allAssets} selected={images} kind="image" toggle={id=>{setSelected(images.includes(id)?images.filter(v=>v!==id):[...images,id]);setProductId('');}}/></div><div className="modal-actions"><button className="primary" onClick={()=>setPicker(false)}>确定选择<Check size={16}/></button></div></Modal>}
    {productPicker&&<Modal title="从商品库选择" close={()=>setProductPicker(false)}><div className="modal-body product-select-list">{products.length?products.map(p=><button key={p.id} onClick={()=>{setProductId(p.id);setSelected([]);setProductPicker(false);}}><ShoppingBag size={19}/><div><strong>{p.name}</strong><small>{p.sku||p.category||'商品资料'} · {p.asset_ids.length} 张图</small></div><ArrowRight size={16}/></button>):<><p className="muted">还没有商品资料。</p><button className="secondary" onClick={()=>go('products')}>创建商品<Plus size={15}/></button></>}</div></Modal>}
    {linkPicker&&<Modal title="从链接库选择" close={()=>setLinkPicker(false)}><div className="modal-body product-select-list">{links.length?links.map(l=><button key={l.id} onClick={()=>{setLinkId(l.id);setMode('replicate');setLinkPicker(false);}}><Link size={19}/><div><strong>{l.title}</strong><small>{l.platform}</small></div><ArrowRight size={16}/></button>):<><p className="muted">还没有参考链接，可直接在输入框中粘贴链接。</p><button className="secondary" onClick={()=>go('links')}>管理链接<ArrowRight size={15}/></button></>}</div></Modal>}
  </>;
}
