'use client';
import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
type Theme = 'dark' | 'light';
interface Ctx { theme: Theme; toggleTheme: () => void; }
const C = createContext<Ctx>({ theme: 'dark', toggleTheme: () => {} });
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>('dark');
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
    const stored = localStorage.getItem('stockai-theme') as Theme | null;
    if (stored) { setTheme(stored); document.documentElement.setAttribute('data-theme', stored); }
    else { document.documentElement.setAttribute('data-theme', 'dark'); }
  }, []);
  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    localStorage.setItem('stockai-theme', next);
    document.cookie = `theme=${next};path=/;max-age=31536000`;
    document.documentElement.setAttribute('data-theme', next);
  };
  if (!mounted) return <div style={{visibility:'hidden'}}>{children}</div>;
  return <C.Provider value={{ theme, toggleTheme }}>{children}</C.Provider>;
}
export const useTheme = () => useContext(C);
