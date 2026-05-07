"""StockAI — Pydantic Schemas for API responses"""
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.7.0"
    timestamp: str = ""


class StockData(BaseModel):
    symbol: str
    name: str = ""
    price: float = 0.0
    change: float = 0.0
    change_percent: float = 0.0
    volume: int = 0
    market_cap: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    pe_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None


class StockHistoryPoint(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class BollingerBand(BaseModel):
    date: str
    upper: float
    middle: float
    lower: float
    close: float


class PredictionResult(BaseModel):
    symbol: str
    prediction: str
    confidence: float = 0.0
    target_price: Optional[float] = None
    signals: list[dict[str, Any]] = []


class StockListResponse(BaseModel):
    stocks: list[StockData]
    total: int = 0


class ApiResponse(BaseModel):
    success: bool = True
    message: str = ""
    data: Optional[Any] = None
    error: Optional[str] = None
