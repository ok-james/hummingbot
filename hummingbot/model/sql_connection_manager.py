import logging
from enum import Enum
from os.path import join
from typing import TYPE_CHECKING, Optional

from sqlalchemy import MetaData, create_engine, inspect
from sqlalchemy.engine.base import Engine
from sqlalchemy.orm import Query, Session, sessionmaker
from sqlalchemy.schema import DropConstraint, ForeignKeyConstraint, Table

from hummingbot import data_path
from hummingbot.logger.logger import HummingbotLogger
from hummingbot.model import get_declarative_base
from hummingbot.model.metadata import Metadata as LocalMetadata
from hummingbot.model.transaction_base import TransactionBase

if TYPE_CHECKING:
    from hummingbot.client.config.config_helpers import ClientConfigAdapter


class SQLConnectionType(Enum):
    TRADE_FILLS = 1


class SQLConnectionManager(TransactionBase):
    _scm_logger: Optional[HummingbotLogger] = None
    _scm_trade_fills_instance: Optional["SQLConnectionManager"] = None

    LOCAL_DB_VERSION_KEY = "local_db_version"
    LOCAL_DB_VERSION_VALUE = "20230516"

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._scm_logger is None:
            cls._scm_logger = logging.getLogger(__name__)
        return cls._scm_logger

    @classmethod
    def get_declarative_base(cls):
        return get_declarative_base()

    @classmethod
    def get_trade_fills_instance(
        cls, client_config_map: "ClientConfigAdapter", db_name: Optional[str] = None
    ) -> "SQLConnectionManager":
        if cls._scm_trade_fills_instance is None:
            cls._scm_trade_fills_instance = SQLConnectionManager(
                client_config_map, SQLConnectionType.TRADE_FILLS, db_name=db_name
            )
        elif cls.create_db_path(db_name=db_name) != cls._scm_trade_fills_instance.db_path:
            cls._scm_trade_fills_instance = SQLConnectionManager(
                client_config_map, SQLConnectionType.TRADE_FILLS, db_name=db_name
            )
        return cls._scm_trade_fills_instance

    @classmethod
    def create_db_path(cls, db_path: Optional[str] = None, db_name: Optional[str] = None) -> str:
        if db_path is not None:
            return db_path
        if db_name is not None:
            return join(data_path(), f"{db_name}.sqlite")
        else:
            return join(data_path(), "hummingbot_trades.sqlite")

    def __init__(self,
                 client_config_map: "ClientConfigAdapter",
                 connection_type: SQLConnectionType,
                 db_path: Optional[str] = None,
                 db_name: Optional[str] = None,
                 called_from_migrator = False):
        db_path = self.create_db_path(db_path, db_name)
        self.db_path = db_path

        if connection_type is SQLConnectionType.TRADE_FILLS:
            self._engine: Engine = create_engine(client_config_map.db_mode.get_url(self.db_path))
            # get_declarative_base() 方法本身返回的是一个管理表的对象，而 metadata 中关联着所有表的信息，详情可以查看 get_declarative_base 方法中的注释
            self._metadata: MetaData = self.get_declarative_base().metadata
            # 创建所有的表，如果数据库中已经有相应的表了，这个表不会被删除并重新创建，而是直接忽略这个表的创建操作。
            self._metadata.create_all(self._engine)

            # SQLite does not enforce foreign key constraint, but for others engines, we need to drop it.
            # See: `hummingbot/market/markets_recorder.py`, at line 213.
            # self._engine.begin() 创建的是一个事务。在 SQLAlchemy 中，事务是一组数据库操作，这些操作要么全部成功，要么全部失败。如果在事务中的任何一个操作失败，那么所有的操作都会被回滚，数据库的状态会恢复到事务开始之前的状态。
            with self._engine.begin() as conn:
                inspector = inspect(conn)
                
                # inspector.get_sorted_table_and_fkc_names() 方法用于获取当前数据库中所有表及其外键约束的信息
                for tname, fkcs in reversed(
                        inspector.get_sorted_table_and_fkc_names()):
                    # 对于每个表，如果它有外键约束（即 fkcs 不为空），则删除这个外键约束， fkcs 是一个列表，列表中的每个元素是一个外键约束的名称
                    if fkcs:
                        if not self._engine.dialect.supports_alter:
                            continue
                        for fkc in fkcs:
                            fk_constraint = ForeignKeyConstraint((), (), name=fkc)
                            # 在 SQLAlchemy 中，要删除一个外键约束，你需要创建一个 ForeignKeyConstraint 对象，然后将这个对象添加到一个 Table 对象中，最后执行 DropConstraint 操作。这是 SQLAlchemy 的工作方式，即使这个外键约束已经存在于数据库中。
                            # ForeignKeyConstraint((), (), name=fkc) 这行代码创建了一个新的 ForeignKeyConstraint 对象，这个对象表示要删除的外键约束。然后，Table(tname, MetaData(), fk_constraint) 这行代码创建了一个新的 Table 对象，并将 fk_constraint 添加到这个 Table 对象中。
                            # 这并不是在数据库中新建一个外键约束，而是在 SQLAlchemy 中创建了一个表示这个外键约束的对象。这个对象只存在于 SQLAlchemy 中，不会影响数据库中的实际数据。
                            # 所以，Table(tname, MetaData(), fk_constraint) 这行代码的作用是在 SQLAlchemy 中创建一个新的 Table 对象，并将要删除的外键约束添加到这个 Table 对象中，以便 SQLAlchemy 能够找到这个外键约束并删除它。
                            Table(tname, MetaData(), fk_constraint)
                            conn.execute(DropConstraint(fk_constraint))

        # sessionmaker(bind=self._engine) 创建的是一个会话工厂。在 SQLAlchemy 中，会话是一个持久化操作的工作空间。它是应用程序和数据库之间的所有对话的中心。会话提供了对数据库的所有 CRUD（创建、读取、更新、删除）操作。
        self._session_cls = sessionmaker(bind=self._engine)

        if connection_type is SQLConnectionType.TRADE_FILLS and (not called_from_migrator):
            self.check_and_migrate_db(client_config_map)

    @property
    def engine(self) -> Engine:
        return self._engine

    def get_new_session(self) -> Session:
        return self._session_cls()

    def get_local_db_version(self, session: Session):
        query: Query = (session.query(LocalMetadata)
                        .filter(LocalMetadata.key == self.LOCAL_DB_VERSION_KEY))
        result: Optional[LocalMetadata] = query.one_or_none()
        return result

    def check_and_migrate_db(self, client_config_map: "ClientConfigAdapter"):
        from hummingbot.model.db_migration.migrator import Migrator
        with self.get_new_session() as session:
            # 这行代码开始了一个新的事务，with 语句块中的所有操作都会在这个事务中执行。如果 with 语句块中的任何一个操作失败，那么整个事务都会被回滚。
            with session.begin():
                local_db_version = self.get_local_db_version(session=session)
                if local_db_version is None:
                    version_info: LocalMetadata = LocalMetadata(key=self.LOCAL_DB_VERSION_KEY,
                                                                value=self.LOCAL_DB_VERSION_VALUE)
                    session.add(version_info)
                    session.commit()
                else:
                    # There's no past db version to upgrade from at this moment. So we'll just update the version value
                    # if needed.
                    if local_db_version.value < self.LOCAL_DB_VERSION_VALUE:
                        was_migration_successful = Migrator().migrate_db_to_version(
                            client_config_map, self, int(local_db_version.value), int(self.LOCAL_DB_VERSION_VALUE)
                        )
                        if was_migration_successful:
                            # Cannot use variable local_db_version because reference is not valid
                            # since Migrator changed it
                            self.get_local_db_version(session=session).value = self.LOCAL_DB_VERSION_VALUE
