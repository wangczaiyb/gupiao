"""
数据管理器与清洗归一化单元测试
"""

import pandas as pd
from data_provider.csv_fetcher import CSVFetcher
from data_provider.manager import DataManager


def test_csv_fetcher_column_normalization_and_units(tmp_path):
    """测试 CSV 导入不同中英文字段映射与数据清洗"""
    csv_file = tmp_path / "test_stock.csv"
    csv_file.write_text(
        "日期,开盘价,最高价,最低价,收盘价,成交股数,成交金额\n"
        "2024-01-02,10.0,10.5,9.8,10.2,50000,510000\n"
        "2024-01-03,10.3,10.8,10.1,10.6,60000,636000\n",
        encoding="utf-8",
    )

    fetcher = CSVFetcher(data_dir=str(tmp_path))
    df = fetcher.load_from_file(str(csv_file), symbol="TEST01")

    assert len(df) == 2
    assert list(df.columns) == ["date", "symbol", "open", "high", "low", "close", "volume", "amount", "pct_chg", "turnover"]
    assert df["volume"].iloc[0] == 50000.0
    assert df["close"].iloc[1] == 10.6


def test_data_manager_watchlist_crud(tmp_path):
    """测试自选股的增删查改"""
    db_file = tmp_path / "test_mgr.db"
    cache_dir = tmp_path / "cache"

    mgr = DataManager(db_path=str(db_file), cache_dir=str(cache_dir))

    # 添加自定义股票
    mgr.add_to_watchlist("688981", "中芯国际", "科创板芯片龙头")
    watchlist = mgr.get_watchlist()
    symbols = [w["symbol"] for w in watchlist]
    assert "688981" in symbols

    # 移除自选
    mgr.remove_from_watchlist("688981")
    watchlist_after = mgr.get_watchlist()
    symbols_after = [w["symbol"] for w in watchlist_after]
    assert "688981" not in symbols_after
