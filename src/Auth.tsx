import { useState } from 'react';
import { Aperture, ArrowRight, Layers3, WandSparkles, Film, LoaderCircle } from 'lucide-react';
import { post } from './api';
import type { User } from './types';

export default function Auth({ setup, signedIn }: { setup: boolean; signedIn: (user: User) => void }) {
  const [register, setRegister] = useState(false);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const creating = setup || register;
  return <div className="auth-page"><aside className="auth-visual"><div className="brand"><Aperture size={31} /><b>商景<span>STUDIO</span></b></div><div><span className="eyebrow">电商视觉创作工作台</span><h1>把商品素材，<br />变成下一次创作。</h1><p>图片、模特与视频，共用一个创作空间。</p><div className="auth-orbit"><div className="orbit-card one"><Layers3 size={28} />素材管理</div><div className="orbit-card two"><WandSparkles size={28} />图片创作</div><div className="orbit-card three"><Film size={28} />视频制作</div></div></div><small>SHANGJING / CREATIVE WORKSPACE</small></aside><main className="auth-form"><div><span className="eyebrow">{setup ? '初次使用' : '欢迎回来'}</span><h2>{setup ? '创建你的工作台' : register ? '注册创作者账号' : '登录商景'}</h2><p className="muted">{setup ? '第一个账号将成为管理员，后续可配置模型与功能价格。' : '继续管理素材与创作任务。'}</p><form onSubmit={async e => { e.preventDefault(); setError(''); setBusy(true); try { signedIn(await post<User>(setup ? '/auth/setup' : register ? '/auth/register' : '/auth/login', { email, password, name: name || '创作者' })); } catch (err) { setError((err as Error).message); } finally { setBusy(false); } }}>
    {creating && <label>称呼<input required placeholder="你的名字或团队名称" value={name} onChange={e => setName(e.target.value)} maxLength={40} /></label>}
    <label>邮箱<input required type="email" autoComplete="username" placeholder="name@example.com" value={email} onChange={e => setEmail(e.target.value)} /></label>
    <label>密码<input required type="password" minLength={creating ? 8 : 1} autoComplete={creating ? 'new-password' : 'current-password'} placeholder={creating ? '至少 8 位密码' : '输入密码'} value={password} onChange={e => setPassword(e.target.value)} /></label>
    {error && <div className="error-text" role="alert">{error}</div>}
    <button className="primary full" disabled={busy}>{busy ? <LoaderCircle size={18} className="spin" /> : <ArrowRight size={18} />}{setup ? '创建工作台' : register ? '注册并进入' : '登录工作台'}</button>
  </form>{!setup && <button className="text-button" onClick={() => { setRegister(!register); setError(''); }}>{register ? '已有账号？去登录' : '没有账号？注册'}</button>}<small className="auth-footnote">模型接口可在进入工作台后配置。</small></div></main></div>;
}
