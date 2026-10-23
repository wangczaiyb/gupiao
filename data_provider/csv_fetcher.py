"""
本地 CSV 与 Excel 数据导入适配器
允许用户导入自定义个股、指数或回测样本历史日线
自动匹配中英文表头、统一日期格式并执行数据有效性清洗
"""

from typing import Any, Dict, List, Optional
import os
import pandas as pd
from data_provider.base import BaseDataProvider, StockQuoteItem


class CSVFetcher(BaseDataProvider):
    """支持本地 CSV / Excel 文件导入的数据适配器"""

    def __init__(self, data_dir: str = "data/imports"):
        super().__init__(name="本地 CSV/Excel 导入")
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)

    def is_available(self) -> bool:
        return True

    def get_stock_list(self) -> List[Dict[str, Any]]:
        """遍历导入目录下的所有 CSV 文件"""
        stocks = []
        if not os.path.exists(self.data_dir):
            return stocks
        for f in os.listdir(self.data_dir):
            if f.endswith((".csv", ".xlsx", ".xls")):
                sym = os.path.splitext(f)[0]
                stocks.append({
                    "symbol": sym,
                    "name": f"本地文件_{sym}",
                    "exchange": "LOCAL",
                    "board_key": "LOCAL",
                    "board_name": "本地数据",
                })
        return stocks

    def load_from_file(self, filepath_or_buffer: Any, symbol: str = "CUSTOM") -> pd.DataFrame:
        """从文件或 Streamlit 上传组件加载并标准化数据"""
        try:
            if isinstance(filepath_or_buffer, str) and filepath_or_buffer.endswith((".xlsx", ".xls")):
                df = pd.read_excel(filepath_or_buffer)
            else:
                df = pd.read_csv(filepath_or_buffer)

            # 表头兼容映射
            rename_dict = {}
            for col in df.columns:
                c_str = str(col).strip().lower()
                if c_str in ("date", "日期", "交易日期", "time"):
                    rename_dict[col] = "date"
                elif c_str in ("open", "开盘", "开盘价"):
                    rename_dict[col] = "open"
                elif c_str in ("high", "最高", "最高价"):
                    rename_dict[col] = "high"
                elif c_str in ("low", "最低", "最低价"):
                    rename_dict[col] = "low"
                elif c_str in ("close", "收盘", "收盘价"):
                    rename_dict[col] = "close"
                elif c_str in ("volume", "vol", "成交量", "成交股数"):
                    rename_dict[col] = "volume"
                elif c_str in ("amount", "amt", "成交额", "成交金额"):
                    rename_dict[col] = "amount"
                elif c_str in ("pct_chg", "涨跌幅", "pctchg", "change"):
                    rename_dict[col] = "pct_chg"
                elif c_str in ("turnover", "换手率", "turn"):
                    rename_dict[col] = "turnover"

            df = df.rename(columns=rename_dict)

            # 校验核心字段
            required = ["date", "open", "high", "low", "close"]
            for r in required:
                if r not in df.columns:
                    return pd.DataFrame()

            if "volume" not in df.columns:
                df["volume"] = 0.0
            if "amount" not in df.columns:
                df["amount"] = df["close"] * df["volume"]
            if "pct_chg" not in df.columns:
                df["pct_chg"] = df["close"].pct_change().fillna(0.0) * 100.0
            if "turnover" not in df.columns:
                df["turnover"] = 0.0

            df["symbol"] = symbol
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

            numeric_cols = ["open", "high", "low", "close", "volume", "amount", "pct_chg", "turnover"]
            for col in numeric_cols:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

            df = df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
            df = df[(df["close"] > 0) & (df["open"] > 0)].reset_index(drop=True)

            return df[["date", "symbol", "open", "high", "low", "close", "volume", "amount", "pct_chg", "turnover"]]
        except Exception:
            return pd.DataFrame()

    def get_daily_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """从本地存储的 CSV 文件中查找"""
        filepath = os.path.join(self.data_dir, f"{symbol}.csv")
        if not os.path.exists(filepath):
            return pd.DataFrame()
        df = self.load_from_file(filepath, symbol)
        if len(df) == 0:
            return df
        return df[(df["date"] >= start_date[:10]) & (df["date"] <= end_date[:10])].reset_index(drop=True)

    def get_spot_quote(self, symbol: str) -> Optional[StockQuoteItem]:
        return None
