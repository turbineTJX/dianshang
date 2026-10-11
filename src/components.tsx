import { type ReactNode, useEffect, useRef } from 'react';
import { X, ImagePlus, Film, Check, LoaderCircle } from 'lucide-react';
import type { Asset } from './types';

let modalCount = 0;
let previousOverflow = '';
export function Modal({ title, children, close, wide = false }: { title: string; children: ReactNode; close: () => void; wide?: boolean }) {
  const panel = useRef<HTMLElement>(null);
  const closeRef = useRef(close);
  closeRef.current = close;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    if (modalCount++ === 0) { previousOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden'; }
    (panel.current?.querySelector<HTMLElement>('input,textarea,select') || panel.current?.querySelector<HTMLElement>('button'))?.focus({preventScroll:true});
    const keyboard = (event: KeyboardEvent) => {
      if (Array.from(document.querySelectorAll('.modal')).at(-1) !== panel.current) return;
      if (event.key === 'Escape') { event.preventDefault(); closeRef.current(); }
      if (event.key !== 'Tab') return;
      const controls = Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled):not([type=hidden]),textarea:not(:disabled),select:not(:disabled),[tabindex="0"]') || []).filter(e => e.getClientRects().length);
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && (document.activeElement === first || !panel.current?.contains(document.activeElement))) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || !panel.current?.contains(document.activeElement))) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener('keydown', keyboard);
    return () => { document.removeEventListener('keydown', keyboard); if (--modalCount === 0) document.body.style.overflow = previousOverflow; if (previous?.isConnected) previous.focus({preventScroll:true}); };
  }, []);
  return <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) close(); }}><section ref={panel} className={'modal ' + (wide ? 'modal-wide' : '')} role="dialog" aria-modal="true" aria-label={title}><header><h2>{title}</h2><button className="icon-button" onClick={close} aria-label="关闭"><X size={20} /></button></header>{children}</section></div>;
}
export function Empty({ title, description, action, icon = <ImagePlus size={30} /> }: { title: string; description: string; action?: ReactNode; icon?: ReactNode }) {
  return <div className="empty"><div className="empty-icon">{icon}</div><h3>{title}</h3><p>{description}</p>{action}</div>;
}
export function AssetVisual({ asset }: { asset: Asset }) {
  return asset.kind === 'image' ? <img src={asset.thumbnail} alt={asset.name} loading="lazy" /> : <div className="video-cover"><Film size={30} /><span>视频素材</span></div>;
}
export function AssetPicker({ assets, selected, toggle, maximum = 6, kind }: { assets: Asset[]; selected: string[]; toggle: (id: string) => void; maximum?: number; kind?: string }) {
  const filtered = assets.filter(a => !kind || a.kind === kind);
  return <div className="picker-grid">{filtered.length ? filtered.map(asset => <button className={'picker-card ' + (selected.includes(asset.id) ? 'selected' : '')} key={asset.id} onClick={() => { if (selected.includes(asset.id) || selected.length < maximum) toggle(asset.id); }} title={asset.name}><AssetVisual asset={asset} /><span>{asset.name}</span><i>{selected.includes(asset.id) ? <Check size={13} /> : null}</i></button>) : <p className="muted">素材库还没有可选择的素材，请先上传。</p>}</div>;
}
export function Loading() { return <div className="loading"><LoaderCircle className="spin" size={25} /><span>正在加载工作台</span></div>; }
