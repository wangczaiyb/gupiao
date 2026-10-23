"""
Baostock 数据源适配器 (备用数据源)
覆盖沪深主板、创业板、科创板 (注意：Baostock 暂未覆盖北交所)
特性：
1. 规范连接登录与登出状态管理
2. 历史日线数据直接为【股】，字段与主数据源严格统一
3. 当且仅当为主数据源超时或受限时，无缝承接备用抓取
"""

from typing import Any, Dict, List, Optional
import pandas as pd
from data_provider.base import BaseDataProvider, StockQuoteItem
from core.rules import classify_symbol


class BaostockFetcher(BaseDataProvider):
    """基于 Baostock 的稳定历史日线备用数据源"""

    def __init__(self):
        super().__init__(name="Baostock (证券宝/备用接口)")

    def is_available(self) -> bool:
        try:
            import baostock as bs
            return True
        except ImportError:
            return False

    def _to_bs_code(self, symbol: str) -> Optional[str]:
        """将纯数字代码转换为 Baostock 标准代码 (sh.600519, sz.000001)"""
        clean_sym = symbol.strip()
        board_key, exchange, _ = classify_symbol(clean_sym)
        if exchange == "SH":
            return f"sh.{clean_sym}"
        elif exchange == "SZ":
            return f"sz.{clean_sym}"
        # Baostock 不支持 BJ 北交所
        return None

    def get_stock_list(self) -> List[Dict[str, Any]]:
        """Baostock 不适合全量遍历股票列表，返回空由主数据源提供"""
        return []

    def get_daily_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """
        获取历史日线
        adjustflag: '1'为后复权，'2'为前复权，'3'为不复权
        """
        bs_code = self._to_bs_code(symbol)
        if not bs_code:
            return pd.DataFrame()  # 北交所不支持，直接返回空由其他数据源处理

        adjust_map = {"qfq": "2", "hfq": "1", "none": "3"}
        flag = adjust_map.get(adjust, "2")

        try:
            import baostock as bs
            lg = bs.login()
            if lg.error_code != "0":
                return pd.DataFrame()

            fields = "date,code,open,high,low,close,volume,amount,pctChg,turn"
            rs = bs.query_history_k_data_plus(
                code=bs_code,
                fields=fields,
                start_date=start_date[:10],
                end_date=end_date[:10],
                frequency="d",
                adjustflag=flag,
            )

            data_list = []
            while (rs.error_code == "0") and rs.next():
                data_list.append(rs.get_row_data())

            bs.logout()

            if not data_list:
                return pd.DataFrame()

            df = pd.DataFrame(data_list, columns=rs.fields)
            df = df.rename(columns={"pctChg": "pct_chg", "turn": "turnover"})

            # 清洗并统一类型
            # Baostock 中的 volume 已经是【股】，单位一致
            numeric_cols = ["open", "high", "low", "close", "volume", "amount", "pct_chg", "turnover"]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

            clean_sym = symbol.strip()
            df["symbol"] = clean_sym
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

            # 去重、排序并过滤脏数据
            df = df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
            df = df[(df["close"] > 0) & (df["open"] > 0)].reset_index(drop=True)

            return df[["date", "symbol", "open", "high", "low", "close", "volume", "amount", "pct_chg", "turnover"]]

        except Exception:
            return pd.DataFrame()

    def get_spot_quote(self, symbol: str) -> Optional[StockQuoteItem]:
        """Baostock 不提供盘中毫秒级快照，返回 None"""
        return None
