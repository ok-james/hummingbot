from sqlalchemy.ext.declarative import declarative_base

# declarative_base 是 SQLAlchemy 的一个函数，用于创建一个基础类，这个基础类的子类可以自动与一个表在数据库中关联。
HummingbotBase = declarative_base()


def get_declarative_base():
    # 这里的这些类都是用于创建数据库表的，比如 MarketState 类用于创建 MarketState 表，他们都继承自 HummingbotBase
    # 导入这些类后，会自动把这个表信息写入到 HummingbotBase.metadata 中，这样就可以通过 HummingbotBase.metadata.create_all(engine) 创建表了
    from .market_state import MarketState  # noqa: F401
    from .metadata import Metadata  # noqa: F401
    from .order import Order  # noqa: F401
    from .order_status import OrderStatus  # noqa: F401
    from .range_position_collected_fees import RangePositionCollectedFees  # noqa: F401
    from .range_position_update import RangePositionUpdate  # noqa: F401
    from .trade_fill import TradeFill  # noqa: F401

    return HummingbotBase
