'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react';

type Locale = 'zh-hk' | 'zh-cn' | 'en';

const messages: Record<string, Record<string, Record<string, string>>> = {
  'zh-hk': {
    nav: { dashboard: '📊 儀表板', analysis: '🔍 個股分析', capitalFlow: '💰 資金流向', strategy: '📈 策略', reports: '📋 報告' },
    auth: { login: '登入', email: '電子郵件', password: '密碼', forgotPassword: '忘記密碼？', loginButton: '一次性登入', welcomeBack: '歡迎回來', createAccount: '建立新帳戶', orContinueWith: '或使用以下方式繼續' },
    dashboard: { watchlist: '自選股', stocks: '隻', addStock: '+ 新增自選股', capitalFlow: '大市資金流向', today: '今日', mainInflow: '主力淨流入', retailInflow: '散戶淨流入', northbound: '北向資金', southbound: '南向資金', sectorRotation: '板塊資金輪動', days5: '5日', stockDetail: '個股資金細節', realtime: '即時', aiSignals: 'AI 信號', hotNews: '熱門新聞', quickActions: '快速操作', loading: '載入中...', mainForce: '主力淨額', mainRatio: '主力佔比', quota: '今日 AI 分析配額', remaining: '還剩', times: '次' },
    compliance: { disclaimer: '免責聲明：本系統提供之分析數據僅供參考，不構成任何投資建議。投資涉及風險，過去表現並不保證未來回報。', copyright: '© 2026 StockAI. All rights reserved. 證監會合規框架 v2.0', dataSource: '數據來源：模擬數據 · 僅供演示用途', privacy: '私隱政策', terms: '服務條款', contact: '聯絡我們' },
    theme: { light: '☀️ 淺色模式', dark: '🌙 深色模式' },
    language: { zhHk: '繁體中文', zhCn: '简体中文', en: 'English' },
  },
  'zh-cn': {
    nav: { dashboard: '📊 仪表板', analysis: '🔍 个股分析', capitalFlow: '💰 资金流向', strategy: '📈 策略', reports: '📋 报告' },
    auth: { login: '登录', email: '电子邮件', password: '密码', forgotPassword: '忘记密码？', loginButton: '一次性登录', welcomeBack: '欢迎回来', createAccount: '创建新账户', orContinueWith: '或使用以下方式继续' },
    dashboard: { watchlist: '自选股', stocks: '只', addStock: '+ 新增自选股', capitalFlow: '大市资金流向', today: '今日', mainInflow: '主力净流入', retailInflow: '散户净流入', northbound: '北向资金', southbound: '南向资金', sectorRotation: '板块资金轮动', days5: '5日', stockDetail: '个股资金细节', realtime: '实时', aiSignals: 'AI 信号', hotNews: '热门新闻', quickActions: '快速操作', loading: '加载中...', mainForce: '主力净额', mainRatio: '主力占比', quota: '今日 AI 分析配额', remaining: '还剩', times: '次' },
    compliance: { disclaimer: '免责声明：本系统提供的分析数据仅供参考，不构成任何投资建议。投资涉及风险，过去表现并不保证未来回报。', copyright: '© 2026 StockAI. All rights reserved. 证监会合规框架 v2.0', dataSource: '数据来源：模拟数据 · 仅供演示用途', privacy: '隐私政策', terms: '服务条款', contact: '联系我们' },
    theme: { light: '☀️ 浅色模式', dark: '🌙 深色模式' },
    language: { zhHk: '繁體中文', zhCn: '简体中文', en: 'English' },
  },
  'en': {
    nav: { dashboard: '📊 Dashboard', analysis: '🔍 Analysis', capitalFlow: '💰 Capital Flow', strategy: '📈 Strategy', reports: '📋 Reports' },
    auth: { login: 'Login', email: 'Email', password: 'Password', forgotPassword: 'Forgot Password?', loginButton: 'Sign In', welcomeBack: 'Welcome Back', createAccount: 'Create Account', orContinueWith: 'Or continue with' },
    dashboard: { watchlist: 'Watchlist', stocks: 'stocks', addStock: '+ Add Stock', capitalFlow: 'Market Capital Flow', today: 'Today', mainInflow: 'Main Force Inflow', retailInflow: 'Retail Inflow', northbound: 'Northbound', southbound: 'Southbound', sectorRotation: 'Sector Rotation', days5: '5D', stockDetail: 'Stock Detail', realtime: 'Real-time', aiSignals: 'AI Signals', hotNews: 'Hot News', quickActions: 'Quick Actions', loading: 'Loading...', mainForce: 'Main Force Net', mainRatio: 'Main Ratio', quota: 'Daily AI Quota', remaining: 'Remaining', times: 'times' },
    compliance: { disclaimer: 'Disclaimer: Analysis data is for reference only. Not investment advice.', copyright: '© 2026 StockAI. All rights reserved. SFC Compliance Framework v2.0', dataSource: 'Data Source: Simulated Data', privacy: 'Privacy Policy', terms: 'Terms of Service', contact: 'Contact Us' },
    theme: { light: '☀️ Light Mode', dark: '🌙 Dark Mode' },
    language: { zhHk: '繁體中文', zhCn: '简体中文', en: 'English' },
  },
};

const Ctx = createContext<any>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>('zh-hk');
  useEffect(() => {
    const s = localStorage.getItem('stockai-lang') as Locale | null;
    if (s && messages[s]) setLocale(s);
  }, []);
  const setL = useCallback((l: Locale) => { setLocale(l); localStorage.setItem('stockai-lang', l); }, []);
  const t = useCallback((ns: string, key: string): string => {
    const m = messages[locale];
    return m && m[ns] && m[ns][key] ? m[ns][key] : key;
  }, [locale]);

  return React.createElement(Ctx.Provider, { value: { locale, setLocale: setL, t } }, children);
}

export function useI18n() {
  const c = useContext(Ctx);
  if (!c) return { locale: 'zh-hk' as Locale, setLocale: (_l: Locale) => {}, t: (_ns: string, _k: string) => _k };
  return c as { locale: Locale; setLocale: (l: Locale) => void; t: (ns: string, key: string) => string };
}

export const locales: Locale[] = ['zh-hk', 'zh-cn', 'en'];
export type { Locale };
