"""
模拟交易与复盘记账模块 (Paper Trading & Review Journal)
支持订单状态流转 (PENDING, FILLED, UNFILLED, CANCELLED)
记录信号生成时间戳、当时指标快照、策略版本、成交假设与实际手续费
使用 SQLite 本地数据库进行持久化，支持持仓查询与 CSV 导出
"""

from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional
import pandas as pd

from core.calendar import get_t_plus_n_date, to_date_obj
from core.rules import calculate_trade_cost, round_trade_quantity


class OrderStatus(Enum):
    PENDING = "PENDING"  # 待成交
    FILLED = "FILLED"  # 已完全成交
    UNFILLED = "UNFILLED"  # 委托未成交 (如涨跌停买不进卖不出)
    CANCELLED = "CANCELLED"  # 已撤单


class OrderDirection(Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class PaperOrder:
    order_id: str
    symbol: str
    direction: str  # 'BUY' 或 'SELL'
    requested_shares: int
    requested_price: float
    order_time: str
    strategy_name: str
    strategy_version: str
    status: str  # OrderStatus.value
    filled_shares: int = 0
    filled_price: float = 0.0
    filled_time: Optional[str] = None
    fee: float = 0.0
    reason: str = ""
    snapshot_json: str = "{}"


@dataclass
class PaperPosition:
    symbol: str
    shares: int  # 总持股数
    available_shares: int  # T+1 可卖股数
    avg_cost_price: float  # 保本持仓均价 (含买入费用折算)
    last_price: float  # 最新市价
    market_value: float  # 最新市值
    unrealized_pnl: float  # 浮动盈亏 (元)
    unrealized_pnl_pct: float  # 浮动盈亏比例
    first_buy_date: str  # 初次建仓日期


class PaperAccountManager:
    """模拟账户与交易日志存储管理器 (基于 SQLite)"""

    def __init__(self, db_path: str = "data/stock_analysis.db", initial_capital: float = 100000.0):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db(initial_capital)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self, initial_capital: float):
        with self._get_connection() as conn:
            cur = conn.cursor()
            # 账户资金表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS account_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    initial_capital REAL NOT NULL,
                    cash REAL NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            # 如果不存在则插入初始资金
            cur.execute("SELECT id FROM account_state WHERE id = 1")
            if not cur.fetchone():
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cur.execute(
                    "INSERT INTO account_state (id, initial_capital, cash, updated_at) VALUES (1, ?, ?, ?)",
                    (initial_capital, initial_capital, now_str),
                )

            # 持仓表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    symbol TEXT PRIMARY KEY,
                    shares INTEGER NOT NULL,
                    available_shares INTEGER NOT NULL,
                    cost_basis REAL NOT NULL,
                    first_buy_date TEXT NOT NULL,
                    can_sell_date TEXT NOT NULL
                )
            """)

            # 订单表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    requested_shares INTEGER NOT NULL,
                    requested_price REAL NOT NULL,
                    order_time TEXT NOT NULL,
                    strategy_name TEXT NOT NULL,
                    strategy_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    filled_shares INTEGER DEFAULT 0,
                    filled_price REAL DEFAULT 0.0,
                    filled_time TEXT,
                    fee REAL DEFAULT 0.0,
                    reason TEXT,
                    snapshot_json TEXT
                )
            """)

            # 交易明细复盘表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trade_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    shares INTEGER NOT NULL,
                    price REAL NOT NULL,
                    fee REAL NOT NULL,
                    trade_time TEXT NOT NULL,
                    pnl REAL DEFAULT 0.0,
                    note TEXT
                )
            """)
            conn.commit()

    def get_account_summary(self, current_prices: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """获取账户总览：现金、市值、总资产、收益率"""
        current_prices = current_prices or {}
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT initial_capital, cash, updated_at FROM account_state WHERE id = 1")
            row = cur.fetchone()
            init_cap = float(row["initial_capital"])
            cash = float(row["cash"])

            cur.execute("SELECT symbol, shares, available_shares, cost_basis, first_buy_date FROM positions")
            pos_rows = cur.fetchall()

        total_market_value = 0.0
        positions = []
        for p in pos_rows:
            sym = p["symbol"]
            shares = int(p["shares"])
            cost = float(p["cost_basis"])
            px = current_prices.get(sym, cost / shares if shares > 0 else 0.0)
            mv = shares * px
            total_market_value += mv
            pnl = mv - cost
            pnl_pct = pnl / cost if cost > 0 else 0.0

            positions.append(
                PaperPosition(
                    symbol=sym,
                    shares=shares,
                    available_shares=int(p["available_shares"]),
                    avg_cost_price=round(cost / shares, 2) if shares > 0 else 0.0,
                    last_price=round(px, 2),
                    market_value=round(mv, 2),
                    unrealized_pnl=round(pnl, 2),
                    unrealized_pnl_pct=round(pnl_pct, 4),
                    first_buy_date=p["first_buy_date"],
                )
            )

        total_equity = cash + total_market_value
        net_pnl = total_equity - init_cap
        ret_pct = net_pnl / init_cap if init_cap > 0 else 0.0

        return {
            "initial_capital": init_cap,
            "cash": round(cash, 2),
            "market_value": round(total_market_value, 2),
            "total_equity": round(total_equity, 2),
            "net_pnl": round(net_pnl, 2),
            "return_pct": round(ret_pct, 4),
            "positions_count": len(positions),
            "positions": positions,
        }

    def place_order(
        self,
        symbol: str,
        direction: OrderDirection,
        shares: int,
        price: float,
        strategy_name: str = "手动模拟",
        strategy_version: str = "1.0.0",
        snapshot: Optional[Dict[str, Any]] = None,
        reason: str = "波段买入信号执行",
    ) -> PaperOrder:
        """提交模拟委托并根据规则执行撮合"""
        clean_shares = round_trade_quantity(shares, symbol, is_buy=(direction == OrderDirection.BUY))
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        today_str = datetime.now().strftime("%Y-%m-%d")
        order_id = f"ORD_{datetime.now().strftime('%Y%m%d%H%M%S')}_{symbol}"

        order = PaperOrder(
            order_id=order_id,
            symbol=symbol,
            direction=direction.value,
            requested_shares=clean_shares,
            requested_price=round(price, 2),
            order_time=now_str,
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            status=OrderStatus.PENDING.value,
            reason=reason,
            snapshot_json=json.dumps(snapshot or {}, ensure_ascii=False),
        )

        if clean_shares <= 0 or price <= 0:
            order.status = OrderStatus.CANCELLED.value
            order.reason = "委托股数未达申报起点或委托价格非法"
            self._save_order(order)
            return order

        # 撮合逻辑
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT cash FROM account_state WHERE id = 1")
            cash = float(cur.fetchone()["cash"])

            if direction == OrderDirection.BUY:
                gross_amt = clean_shares * price
                fee_detail = calculate_trade_cost(gross_amt, is_buy=True, trade_date=date.today())
                total_required = gross_amt + fee_detail.total_fee

                if cash < total_required:
                    order.status = OrderStatus.UNFILLED.value
                    order.reason = f"可用现金不足 (需 {total_required:.2f} 元，可用 {cash:.2f} 元)"
                    self._save_order(order)
                    return order

                # 扣款并更新持仓
                new_cash = cash - total_required
                cur.execute("UPDATE account_state SET cash = ?, updated_at = ? WHERE id = 1", (new_cash, now_str))

                # T+1 可卖日期计算
                can_sell_date = get_t_plus_n_date(date.today(), n=1).strftime("%Y-%m-%d")

                cur.execute("SELECT shares, available_shares, cost_basis FROM positions WHERE symbol = ?", (symbol,))
                existing_pos = cur.fetchone()
                if existing_pos:
                    new_shares = int(existing_pos["shares"]) + clean_shares
                    # 当日买入股份当日不可卖 (T+1)
                    new_avail = int(existing_pos["available_shares"])
                    new_cost = float(existing_pos["cost_basis"]) + total_required
                    cur.execute(
                        "UPDATE positions SET shares = ?, available_shares = ?, cost_basis = ?, can_sell_date = ? WHERE symbol = ?",
                        (new_shares, new_avail, new_cost, can_sell_date, symbol),
                    )
                else:
                    cur.execute(
                        "INSERT INTO positions (symbol, shares, available_shares, cost_basis, first_buy_date, can_sell_date) VALUES (?, ?, 0, ?, ?, ?)",
                        (symbol, clean_shares, total_required, today_str, can_sell_date),
                    )

                # 记录成交
                order.status = OrderStatus.FILLED.value
                order.filled_shares = clean_shares
                order.filled_price = price
                order.filled_time = now_str
                order.fee = fee_detail.total_fee

                cur.execute(
                    "INSERT INTO trade_history (order_id, symbol, direction, shares, price, fee, trade_time, pnl, note) VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, ?)",
                    (order_id, symbol, direction.value, clean_shares, price, fee_detail.total_fee, now_str, reason),
                )
                conn.commit()

            elif direction == OrderDirection.SELL:
                cur.execute("SELECT shares, available_shares, cost_basis FROM positions WHERE symbol = ?", (symbol,))
                pos = cur.fetchone()
                if not pos or int(pos["available_shares"]) < clean_shares:
                    avail = int(pos["available_shares"]) if pos else 0
                    order.status = OrderStatus.UNFILLED.value
                    order.reason = f"T+1 可卖股数不足 (需卖 {clean_shares} 股，当前可用 {avail} 股)"
                    self._save_order(order)
                    return order

                gross_amt = clean_shares * price
                fee_detail = calculate_trade_cost(gross_amt, is_buy=False, trade_date=date.today())
                net_revenue = gross_amt - fee_detail.total_fee

                # 计算平仓盈亏
                cur_shares = int(pos["shares"])
                cur_cost = float(pos["cost_basis"])
                portion_cost = (cur_cost / cur_shares) * clean_shares
                pnl = net_revenue - portion_cost

                # 更新现金与持仓
                new_cash = cash + net_revenue
                cur.execute("UPDATE account_state SET cash = ?, updated_at = ? WHERE id = 1", (new_cash, now_str))

                rem_shares = cur_shares - clean_shares
                rem_avail = int(pos["available_shares"]) - clean_shares
                if rem_shares <= 0:
                    cur.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
                else:
                    rem_cost = max(0.0, cur_cost - portion_cost)
                    cur.execute(
                        "UPDATE positions SET shares = ?, available_shares = ?, cost_basis = ? WHERE symbol = ?",
                        (rem_shares, rem_avail, rem_cost, symbol),
                    )

                order.status = OrderStatus.FILLED.value
                order.filled_shares = clean_shares
                order.filled_price = price
                order.filled_time = now_str
                order.fee = fee_detail.total_fee

                cur.execute(
                    "INSERT INTO trade_history (order_id, symbol, direction, shares, price, fee, trade_time, pnl, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (order_id, symbol, direction.value, clean_shares, price, fee_detail.total_fee, now_str, pnl, reason),
                )
                conn.commit()

        self._save_order(order)
        return order

    def _save_order(self, order: PaperOrder):
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO orders (
                    order_id, symbol, direction, requested_shares, requested_price,
                    order_time, strategy_name, strategy_version, status,
                    filled_shares, filled_price, filled_time, fee, reason, snapshot_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order.order_id, order.symbol, order.direction, order.requested_shares, order.requested_price,
                order.order_time, order.strategy_name, order.strategy_version, order.status,
                order.filled_shares, order.filled_price, order.filled_time, order.fee, order.reason, order.snapshot_json
            ))
            conn.commit()

    def get_trade_history_df(self) -> pd.DataFrame:
        """获取交易明细 DataFrame，方便复盘与导出"""
        with self._get_connection() as conn:
            df = pd.read_sql_query("SELECT * FROM trade_history ORDER BY id DESC", conn)
        return df

    def get_orders_df(self) -> pd.DataFrame:
        """获取全部委托单 DataFrame"""
        with self._get_connection() as conn:
            df = pd.read_sql_query("SELECT * FROM orders ORDER BY order_time DESC", conn)
        return df

    def export_trade_history_csv(self, target_filepath: str = "data/exports/trade_history.csv") -> str:
        """导出交易复盘记录为 CSV 文件"""
        os.makedirs(os.path.dirname(target_filepath), exist_ok=True)
        df = self.get_trade_history_df()
        df.to_csv(target_filepath, index=False, encoding="utf-8-sig")
        return target_filepath

    def reset_account(self, new_capital: float = 100000.0):
        """重置模拟账户与清空历史模拟持仓"""
        with self._get_connection() as conn:
            cur = conn.cursor()
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute("UPDATE account_state SET initial_capital = ?, cash = ?, updated_at = ? WHERE id = 1", (new_capital, new_capital, now_str))
            cur.execute("DELETE FROM positions")
            cur.execute("DELETE FROM orders")
            cur.execute("DELETE FROM trade_history")
            conn.commit()
