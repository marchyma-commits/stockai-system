/** StockAI v2 — API Client */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api';

export interface StockInfo {
  symbol: string;
  name: string;
  exchange: string;
  currency: string;
  price: number;
  open: number;
  high: number;
  low: number;
  prev_close: number;
  change: number;
  change_percent: number;
  volume: string;
  week_high: number;
  week_low: number;
  market_cap: number;
  pe: number;
  updated_at: string;
}

export interface ApiResponse<T> {
  success: boolean;
  data: T;
  count?: number;
}

async function fetchApi<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getStocks(): Promise<StockInfo[]> {
  const data = await fetchApi<ApiResponse<StockInfo[]>>('/stocks');
  return data.data;
}

export async function getStock(symbol: string): Promise<StockInfo> {
  const data = await fetchApi<ApiResponse<StockInfo>>(`/stock/${symbol}`);
  return data.data;
}

export async function getStockHistory(symbol: string, period = '1mo'): Promise<{x: string; y: number[]}[]> {
  const data = await fetchApi<ApiResponse<{x: string; y: number[]}[]>>(`/stock/${symbol}/history?period=${period}`);
  return data.data;
}

export async function searchStocks(query: string): Promise<StockInfo[]> {
  const data = await fetchApi<ApiResponse<StockInfo[]>>(`/search?q=${encodeURIComponent(query)}`);
  return data.data;
}

export async function getHotStocks(): Promise<StockInfo[]> {
  const data = await fetchApi<ApiResponse<StockInfo[]>>('/hot-stocks');
  return data.data;
}

export async function getBollinger(symbol: string): Promise<{upper: number[]; middle: number[]; lower: number[]; timestamps: string[]}> {
  const data = await fetchApi<ApiResponse<{upper: number[]; middle: number[]; lower: number[]; timestamps: string[]}>>(`/stock/${symbol}/bb`);
  return data.data;
}
