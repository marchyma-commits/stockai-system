'use client';

import { useState } from 'react';
import { ThemeProvider, useTheme } from '@/components/theme/ThemeProvider';
import { I18nProvider, useI18n, locales } from '@/lib/i18n';

function LoginForm() {
  const { t, locale, setLocale } = useI18n();
  const { theme, toggleTheme } = useTheme();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setTimeout(() => { setLoading(false); window.location.href = '/dashboard'; }, 1000);
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{background: 'var(--bg-primary)'}}>
      {/* Top Controls */}
      <div className="fixed top-4 right-4 flex items-center gap-2 z-50">
        <div className="flex gap-1 rounded-lg p-1" style={{background: 'var(--bg-card)', border: '1px solid var(--border-color)'}}>
          {locales.map(l => (
            <button key={l} onClick={() => setLocale(l)}
              className="px-2 py-1 text-xs rounded-md cursor-pointer transition-all"
              style={{background: locale === l ? 'var(--accent-blue)' : 'transparent', color: locale === l ? '#fff' : 'var(--text-muted)'}}>
              {l === 'zh-hk' ? '繁' : l === 'zh-cn' ? '简' : 'EN'}
            </button>
          ))}
        </div>
        <button onClick={toggleTheme}
          className="px-3 py-1.5 text-xs rounded-lg cursor-pointer border"
          style={{background: 'var(--bg-card)', borderColor: 'var(--border-color)', color: 'var(--text-secondary)'}}>
          {theme === 'dark' ? '☀️' : '🌙'}
        </button>
      </div>

      <div className="w-full max-w-md animate-fade-in">
        <div className="text-center mb-8">
          <div className="text-3xl font-black tracking-wider mb-2">
            <span style={{color: 'var(--accent-green)'}}>STOCK</span><span style={{color: 'var(--accent-blue)'}}>AI</span>
          </div>
          <div className="text-sm" style={{color: 'var(--text-muted)'}}>{t('auth', 'welcomeBack')}</div>
        </div>

        <div className="rounded-2xl p-8 border" style={{background: 'var(--bg-card)', borderColor: 'var(--border-color)'}}>
          <form onSubmit={handleLogin} className="space-y-5">
            <div>
              <label className="block text-sm font-medium mb-2" style={{color: 'var(--text-secondary)'}}>{t('auth', 'email')}</label>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                placeholder="admin@stockai.io" required
                className="w-full px-4 py-3 rounded-xl text-sm outline-none transition-all"
                style={{background: 'var(--bg-primary)', border: '1px solid var(--border-color)', color: 'var(--text-primary)'}} />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2" style={{color: 'var(--text-secondary)'}}>{t('auth', 'password')}</label>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                placeholder="••••••••" required
                className="w-full px-4 py-3 rounded-xl text-sm outline-none transition-all"
                style={{background: 'var(--bg-primary)', border: '1px solid var(--border-color)', color: 'var(--text-primary)'}} />
            </div>
            <div className="flex justify-end">
              <a href="#" className="text-xs hover:underline" style={{color: 'var(--accent-blue)'}}>{t('auth', 'forgotPassword')}</a>
            </div>
            <button type="submit" disabled={loading}
              className="w-full py-3 rounded-xl font-semibold text-white text-sm cursor-pointer transition-all disabled:opacity-60"
              style={{background: 'var(--gradient-accent)'}}>
              {loading ? <span className="flex items-center justify-center gap-2"><span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />{t('auth', 'loginButton')}...</span> : t('auth', 'loginButton')}
            </button>
          </form>
          <div className="mt-6 text-center text-xs" style={{color: 'var(--text-muted)'}}>{t('auth', 'orContinueWith')}</div>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <button className="py-2.5 rounded-xl text-sm font-medium cursor-pointer hover:opacity-80 transition-all"
              style={{background: 'var(--bg-primary)', border: '1px solid var(--border-color)', color: 'var(--text-primary)'}}>Google</button>
            <button className="py-2.5 rounded-xl text-sm font-medium cursor-pointer hover:opacity-80 transition-all"
              style={{background: 'var(--bg-primary)', border: '1px solid var(--border-color)', color: 'var(--text-primary)'}}>Apple</button>
          </div>
          <div className="mt-6 text-center text-xs" style={{color: 'var(--text-muted)'}}>{t('auth', 'createAccount')}</div>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <I18nProvider><ThemeProvider><LoginForm /></ThemeProvider></I18nProvider>
  );
}
