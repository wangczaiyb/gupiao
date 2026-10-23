"""
AKShare 数据源适配器
覆盖沪深北全市场 (主板、创业板、科创板、北交所)
针对性处理：
1. Windows 代理异常自动跳过 (Bypass ProxyError)
2. AKShare 成交量单位【手】向标准系统单位【股】严格换算 (* 100)
3. 异常数据清洗、字段缺失填补与日期重排
"""

import os
from typing import Any, Dict, List, Optional
import pandas as pd
from data_provider.base import BaseDataProvider, StockQuoteItem
from core.rules import classify_symbol


class AKShareFetcher(BaseDataProvider):
    """基于 AKShare 的免费公开行情抓取器"""

    def __init__(self):
        super().__init__(name="AKShare (东方财富/开源接口)")
        # 确保国内金融数据接口不被死代理干扰 (彻底绕行 Windows 注册表中可能存在的死代理)
        try:
            import requests
            old_init = requests.sessions.Session.__init__
            def new_init(session_self, *args, **kwargs):
                old_init(session_self, *args, **kwargs)
                session_self.trust_env = False
            requests.sessions.Session.__init__ = new_init
        except Exception:
            pass

    def is_available(self) -> bool:
        try:
            import akshare as ak
            return True
        except ImportError:
            return False

    def get_stock_list(self) -> List[Dict[str, Any]]:
        """获取沪深北全市场股票清单"""
        try:
            import akshare as ak
            df = ak.stock_info_a_code_name()
            results = []
            for _, row in df.iterrows():
                sym = str(row.get("code", "")).strip()
                name = str(row.get("name", "")).strip()
                if not sym or not sym.isdigit():
                    continue
                board_key, exchange, board_name = classify_symbol(sym)
                results.append({
                    "symbol": sym,
                    "name": name,
                    "exchange": exchange,
                    "board_key": board_key,
                    "board_name": board_name,
                })
            return results
        except Exception:
            return []

    def get_daily_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """
        获取历史日线并严格将成交量由【手】换算为【股】
        """
        clean_sym = symbol.strip().upper()
        if clean_sym.startswith(("SH", "SZ", "BJ")):
            clean_sym = clean_sym[2:].strip(".")
        elif "." in clean_sym:
            parts = clean_sym.split(".")
            clean_sym = parts[0] if parts[0].isdigit() else parts[1]

        # 格式化日期为 YYYYMMDD
        s_date = start_date.replace("-", "")[:8]
        e_date = end_date.replace("-", "")[:8]

        try:
            import akshare as ak
            df = ak.stock_zh_a_hist(
                symbol=clean_sym,
                period="daily",
                start_date=s_date,
                end_date=e_date,
                adjust=adjust,
            )
            if df is not None and len(df) > 0:
                rename_map = {
                    "日期": "date",
                    "开盘": "open",
                    "收盘": "close",
                    "最高": "high",
                    "最低": "low",
                    "成交量": "volume_lots",  # AKShare东财此处为手
                    "成交额": "amount",
                    "涨跌幅": "pct_chg",
                    "换手率": "turnover",
                }
                res = df.rename(columns=rename_map)
                if "volume_lots" in res.columns:
                    res["volume"] = pd.to_numeric(res["volume_lots"], errors="coerce").fillna(0.0) * 100.0
                elif "volume" not in res.columns:
                    res["volume"] = 0.0
                res["symbol"] = clean_sym
                res["date"] = pd.to_datetime(res["date"]).dt.strftime("%Y-%m-%d")

                numeric_cols = ["open", "high", "low", "close", "volume", "amount", "pct_chg", "turnover"]
                for col in numeric_cols:
                    if col in res.columns:
                        res[col] = pd.to_numeric(res[col], errors="coerce").fillna(0.0)
                    else:
                        res[col] = 0.0

                res = res.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
                res = res[(res["close"] > 0) & (res["open"] > 0)].reset_index(drop=True)
                if len(res) > 0:
                    return res[["date", "symbol", "open", "high", "low", "close", "volume", "amount", "pct_chg", "turnover"]]
        except Exception:
            pass

        # 降级尝试 AKShare 新浪源 (stock_zh_a_daily，高稳定性且全面覆盖沪深北全市场)
        try:
            import akshare as ak
            board_key, exchange, _ = classify_symbol(clean_sym)
            prefix = "sh" if exchange == "SH" else ("sz" if exchange == "SZ" else "bj")
            sina_sym = f"{prefix}{clean_sym}"

            df_sina = ak.stock_zh_a_daily(
                symbol=sina_sym,
                start_date=s_date,
                adjust=adjust,
            )
            if df_sina is not None and len(df_sina) > 0:
                res = df_sina.copy()
                res["symbol"] = clean_sym
                res["date"] = pd.to_datetime(res["date"]).dt.strftime("%Y-%m-%d")
                if "pct_chg" not in res.columns:
                    res["pct_chg"] = res["close"].pct_change().fillna(0.0) * 100.0
                if "turnover" not in res.columns:
                    res["turnover"] = 0.0

                numeric_cols = ["open", "high", "low", "close", "volume", "amount", "pct_chg", "turnover"]
                for col in numeric_cols:
                    if col in res.columns:
                        res[col] = pd.to_numeric(res[col], errors="coerce").fillna(0.0)
                    else:
                        res[col] = 0.0

                res = res.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
                res = res[(res["close"] > 0) & (res["open"] > 0)].reset_index(drop=True)
                if len(res) > 0:
                    return res[["date", "symbol", "open", "high", "low", "close", "volume", "amount", "pct_chg", "turnover"]]
        except Exception:
            pass

        return pd.DataFrame()

    def get_spot_quote(self, symbol: str) -> Optional[StockQuoteItem]:
        """获取个股最新快照行情"""
        clean_sym = symbol.strip()
        try:
            import akshare as ak
            board_key, _, _ = classify_symbol(clean_sym)
            if board_key == "BSE":
                df = ak.stock_bj_a_spot_em()
            else:
                # 尝试获取个股实时分时最后行情或简版实时行情
                df = ak.stock_zh_a_spot_em()

            match = df[df["代码"].astype(str) == clean_sym]
            if len(match) == 0:
                return None

            row = match.iloc[0]
            vol_lots = float(row.get("成交量", 0.0))
            return StockQuoteItem(
                symbol=clean_sym,
                name=str(row.get("名称", "")),
                price=float(row.get("最新价", 0.0)),
                pct_chg=float(row.get("涨跌幅", 0.0)),
                volume_shares=vol_lots * 100.0,
                amount=float(row.get("成交额", 0.0)),
                turnover_rate=float(row.get("换手率", 0.0)),
                pe_ratio=float(row.get("市盈率-动态", 0.0)) if "市盈率-动态" in row else None,
                market_cap=float(row.get("总市值", 0.0)) if "总市值" in row else None,
                update_time=str(row.get("更新时间", "")),
                source="AKShare",
            )
        except Exception:
            return None
