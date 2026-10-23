"""
A 股交易规则与费率配置模块
严格依据交易所、财政部、中国证券登记结算有限责任公司 (中国结算) 官方规则实现
覆盖主板、创业板、科创板与北交所的交易规则与按日期生效的税费结构
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Tuple


@dataclass(frozen=True)
class BoardRules:
    board_name: str
    exchange: str  # 'SH', 'SZ', 'BJ'
    min_buy_qty: int  # 最小买入数量 (股)
    qty_step: int  # 买入申报递增单位 (股)
    price_limit_ratio: float  # 标准涨跌幅限制 (例如 0.10, 0.20, 0.30)
    st_price_limit_ratio: float  # 风险警示股票涨跌幅 (例如 0.05)
    unlimited_days_ipo: int  # 新股上市无涨跌幅限制交易日数 (主板已改为注册制前5日，科创/创业板5日，北交所首日)
    allow_odd_lot_sell: bool = True  # 允许零股一次性卖出


# 分板块官方规则定义
BOARD_RULES = {
    "SH_MAIN": BoardRules(
        board_name="沪市主板",
        exchange="SH",
        min_buy_qty=100,
        qty_step=100,
        price_limit_ratio=0.10,
        st_price_limit_ratio=0.05,
        unlimited_days_ipo=5,  # 2023全面注册制后主板前5个交易日不设涨跌幅
    ),
    "SZ_MAIN": BoardRules(
        board_name="深市主板",
        exchange="SZ",
        min_buy_qty=100,
        qty_step=100,
        price_limit_ratio=0.10,
        st_price_limit_ratio=0.05,
        unlimited_days_ipo=5,
    ),
    "STAR": BoardRules(
        board_name="科创板",
        exchange="SH",
        min_buy_qty=200,  # 上交所科创板规则：单笔申报不得小于200股
        qty_step=1,  # 超过200股部分可以以1股为单位递增
        price_limit_ratio=0.20,
        st_price_limit_ratio=0.20,  # 科创板ST股票涨跌幅同为20%
        unlimited_days_ipo=5,  # 上市前5个交易日不设涨跌幅限制
    ),
    "CHINEXT": BoardRules(
        board_name="创业板",
        exchange="SZ",
        min_buy_qty=100,
        qty_step=100,  # 创业板买入按100股整数倍递增
        price_limit_ratio=0.20,
        st_price_limit_ratio=0.20,  # 创业板ST股票涨跌幅同为20%
        unlimited_days_ipo=5,  # 上市前5个交易日不设涨跌幅限制
    ),
    "BSE": BoardRules(
        board_name="北交所",
        exchange="BJ",
        min_buy_qty=100,  # 北交所单笔申报不得低于100股
        qty_step=1,  # 超过100股可以按1股递增
        price_limit_ratio=0.30,  # 北交所涨跌幅限制为 30%
        st_price_limit_ratio=0.30,
        unlimited_days_ipo=1,  # 北交所上市首日不设涨跌幅限制
    ),
}


def classify_symbol(symbol: str) -> Tuple[str, str, str]:
    """
    根据股票代码精确识别板块与交易所
    返回: (board_key, exchange, display_name)
    """
    clean_sym = symbol.strip().upper()
    if clean_sym.startswith(("SH", "SZ", "BJ")):
        clean_sym = clean_sym[2:].strip(".")
    elif "." in clean_sym:
        parts = clean_sym.split(".")
        if len(parts[0]) == 6 and parts[0].isdigit():
            clean_sym = parts[0]
        elif len(parts[1]) == 6 and parts[1].isdigit():
            clean_sym = parts[1]

    if not clean_sym.isdigit():
        return "UNKNOWN", "UNKNOWN", "未知证券"

    # 上交所科创板: 688xxx, 689xxx
    if clean_sym.startswith(("688", "689")):
        return "STAR", "SH", "科创板"
    # 上交所主板: 600xxx, 601xxx, 603xxx, 605xxx
    elif clean_sym.startswith(("600", "601", "603", "605")):
        return "SH_MAIN", "SH", "沪市主板"
    # 深交所创业板: 300xxx, 301xxx
    elif clean_sym.startswith(("300", "301")):
        return "CHINEXT", "SZ", "创业板"
    # 深交所主板: 000xxx, 001xxx, 002xxx, 003xxx
    elif clean_sym.startswith(("000", "001", "002", "003")):
        return "SZ_MAIN", "SZ", "深市主板"
    # 北交所: 920xxx, 83xxxx, 87xxxx, 88xxxx, 43xxxx
    elif clean_sym.startswith(("920", "83", "87", "88", "43")):
        return "BSE", "BJ", "北交所"
    else:
        return "UNKNOWN", "UNKNOWN", "其他A股"


def get_board_rules(symbol: str) -> BoardRules:
    """获取指定代码对应的板块交易规则，未知代码明确抛出 ValueError，不静默当作沪市主板"""
    board_key, _, _ = classify_symbol(symbol)
    if board_key not in BOARD_RULES:
        raise ValueError(f"未知或无法识别的证券代码: '{symbol}'，无法按沪市主板等特定规则静默处理")
    return BOARD_RULES[board_key]


def round_trade_quantity(qty: int, symbol: str, is_buy: bool = True) -> int:
    """
    按照板块规则规范化申报数量
    - 买入必须满足最小申报股数与递增单位
    - 卖出若持有零股可全额卖出
    - 若代码无法识别则返回 0，杜绝静默按主板成交
    """
    if qty <= 0:
        return 0

    try:
        rules = get_board_rules(symbol)
    except ValueError:
        return 0

    if is_buy:
        if qty < rules.min_buy_qty:
            return 0  # 未达到最小申报量
        # 按照递增单位截断
        excess = qty - rules.min_buy_qty
        steps = excess // rules.qty_step
        return rules.min_buy_qty + steps * rules.qty_step
    else:
        # 卖出：允许零股全额卖出，正常情况下整手卖出
        return int(qty)


def get_stamp_tax_rate(trade_date: Optional[date] = None) -> float:
    """
    获取指定日期的卖出印花税率 (仅对卖方单边征收)
    - 2023年8月28日起：证券交易印花税减半征收，为 0.05% (万分之五)
    - 2008年9月19日至2023年8月27日：单边征收 0.10% (千分之一)
    """
    if trade_date is None:
        return 0.0005

    if isinstance(trade_date, str):
        trade_date = datetime.strptime(trade_date, "%Y-%m-%d").date()
    elif isinstance(trade_date, datetime):
        trade_date = trade_date.date()

    cutoff_date = date(2023, 8, 28)
    if trade_date >= cutoff_date:
        return 0.0005
    return 0.0010


def get_transfer_fee_rate(trade_date: Optional[date] = None) -> float:
    """
    获取中国结算证券交易过户费率 (双向征收)
    - 2022年4月29日起：股票交易过户费总体下调50%，统一下调为成交金额的 0.001% (万分之零点一 / 0.01‰)
    - 2015年8月1日至2022年4月28日：为成交金额的 0.002% (0.02‰)
    """
    if trade_date is None:
        return 0.00001

    if isinstance(trade_date, str):
        trade_date = datetime.strptime(trade_date, "%Y-%m-%d").date()
    elif isinstance(trade_date, datetime):
        trade_date = trade_date.date()

    cutoff_date = date(2022, 4, 29)
    if trade_date >= cutoff_date:
        return 0.00001
    return 0.00002


@dataclass
class TradeFeeDetail:
    commission: float  # 券商佣金 (含规费)
    min_commission_applied: bool  # 是否触发最低5元佣金限制
    stamp_tax: float  # 卖出印花税
    transfer_fee: float  # 证券交易过户费 (双向)
    total_fee: float  # 总费用
    slippage_cost: float  # 预估滑点成本


def calculate_trade_cost(
    amount: float,
    is_buy: bool,
    trade_date: Optional[date] = None,
    commission_rate: float = 0.00025,  # 万 2.5
    min_commission: float = 5.0,  # 最低佣金 5 元
    slippage_rate: float = 0.0005,  # 滑点 0.05%
) -> TradeFeeDetail:
    """
    精确计算交易费用
    amount: 成交总金额 (元)
    is_buy: 是否买入
    trade_date: 交易日期 (用于按历史政策匹配印花税与过户费率)
    """
    if amount <= 0:
        return TradeFeeDetail(0.0, False, 0.0, 0.0, 0.0, 0.0)

    # 1. 券商佣金
    raw_commission = amount * commission_rate
    min_applied = False
    if raw_commission < min_commission:
        commission = min_commission
        min_applied = True
    else:
        commission = round(raw_commission, 2)

    # 2. 印花税 (仅卖方单边征收)
    if not is_buy:
        tax_rate = get_stamp_tax_rate(trade_date)
        stamp_tax = round(amount * tax_rate, 2)
    else:
        stamp_tax = 0.0

    # 3. 过户费 (双向征收)
    tf_rate = get_transfer_fee_rate(trade_date)
    transfer_fee = round(amount * tf_rate, 2)

    # 4. 滑点折算成本 (用于实盘估算或扣除)
    slippage_cost = round(amount * slippage_rate, 2)

    total_fee = round(commission + stamp_tax + transfer_fee, 2)
    return TradeFeeDetail(
        commission=commission,
        min_commission_applied=min_applied,
        stamp_tax=stamp_tax,
        transfer_fee=transfer_fee,
        total_fee=total_fee,
        slippage_cost=slippage_cost,
    )


def calculate_price_limits(
    prev_close: float,
    symbol: str,
    is_st: bool = False,
    is_ipo_unlimited: bool = False,
) -> Tuple[float, float]:
    """
    计算股票当日涨跌停价 (依据价格四舍五入精确到分)
    返回: (limit_up_price, limit_down_price)
    """
    if prev_close <= 0:
        return 0.0, 0.0

    if is_ipo_unlimited:
        return round(prev_close * 10.0, 2), 0.01

    try:
        rules = get_board_rules(symbol)
    except ValueError:
        return 0.0, 0.0

    ratio = rules.st_price_limit_ratio if is_st else rules.price_limit_ratio

    # A 股涨跌停价格依据中国结算规范：精确到0.01元，四舍五入
    limit_up = round(prev_close * (1.0 + ratio), 2)
    limit_down = round(prev_close * (1.0 - ratio), 2)
    return limit_up, limit_down


def is_trade_restricted(
    current_open: float,
    limit_up: float,
    limit_down: float,
    is_buy: bool,
    is_suspended: bool = False,
) -> Tuple[bool, str]:
    """
    检查涨跌停与停牌导致的无法成交约束
    - 停牌不能买卖
    - 一字涨停无法买入 (以开盘价触及涨停判定保守不可成交)
    - 一字跌停无法卖出 (以开盘价触及跌停判定保守不可退出)
    """
    if is_suspended:
        return True, "标的停牌，无法委托交易"

    if is_buy and limit_up > 0 and current_open >= limit_up:
        return True, f"开盘触及涨停价 ({limit_up:.2f})，买盘封死无法买入成交"

    if not is_buy and limit_down > 0 and current_open <= limit_down:
        return True, f"开盘触及跌停价 ({limit_down:.2f})，卖盘封死无法平仓退出"

    return False, ""
