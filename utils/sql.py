#!/usr/bin/python
# -*- coding: UTF-8 -*-

import pymysql
import logging
import re
from pymysql.cursors import DictCursor
from typing import List, Dict, Any, Optional, Tuple, Union

from dbutils.pooled_db import PooledDB

# --- 数据库管理器，全局持有一个实例 ---
class DatabaseManager:
    """
    管理数据库连接池的静态类。
    在应用程序启动时，应调用 initialize_pool()。
    """
    _pool = None

    @classmethod
    def initialize_pool(cls, **kwargs):
        """
        在程序启动时调用一次，初始化连接池。
        """
        if cls._pool is None:
            logging.info("Initializing database connection pool...")
            try:
                cls._pool = PooledDB(
                    creator=pymysql,
                    maxconnections=10,
                    mincached=2,
                    maxcached=5,
                    blocking=True,
                    ping=1,
                    cursorclass=DictCursor,
                    **kwargs
                )
                logging.info("Database connection pool initialized successfully.")
            except Exception as e:
                logging.error(f"Failed to initialize database pool: {e}")
                raise

    @classmethod
    def get_connection(cls):
        """从池中获取一个连接。"""
        if cls._pool is None:
            raise ConnectionError("Database pool has not been initialized. Call initialize_pool() first.")
        return cls._pool.connection()

class SQL:
    """
    数据库操作类，使用上下文管理器来确保连接的正确获取和释放。
    通过参数化处理数据值和验证处理SQL标识符来防止SQL注入。
    """
    # 用于验证SQL标识符（表/列名）的正则表达式
    # 只允许字母、数字和下划线，防止注入。
    _VALID_IDENTIFIER_RE = re.compile(r'^[a-zA-Z0-9_]+$')

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._conn = None
        self._cursor = None

    def __enter__(self):
        self._conn = DatabaseManager.get_connection()
        self._cursor = self._conn.cursor()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._cursor:
            self._cursor.close()
        if self._conn:
            if exc_type:
                self.logger.warning(f"An exception occurred. Rolling back transaction. Error: {exc_val}")
                self._conn.rollback()
            else:
                self._conn.commit()
            self._conn.close()

    def validate_indentifier_part(self, identifier: str) -> bool:
        return self._VALID_IDENTIFIER_RE.match(identifier) is not None

    def _validate_identifiers(self, *identifiers: str):
        """
        【安全关键】验证SQL标识符（表名、列名）是否安全。
        这是防止标识符注入的核心。
        """
        for identifier in identifiers:
            # 允许 'database.table' 这种格式，分别校验各部分
            parts = identifier.split('.')
            if len(parts) > 2:
                raise ValueError(f"Invalid SQL identifier format: {identifier}")
            for part in parts:
                if not self.validate_indentifier_part(part):
                    raise ValueError(f"Potentially unsafe SQL identifier detected: '{identifier}'")

    def _format_table_name(self, table: str) -> str:
        """
        正确地为表名加反引号，能处理 'database.table' 格式。
        注意：此函数只做格式化，不做安全检查，安全检查由 _validate_identifiers 完成。
        """
        if '.' in table:
            return '.'.join([f"`{part}`" for part in table.split('.', 1)])
        else:
            return f"`{table}`"

    def _execute(self, sql: str, params: Optional[Union[Tuple, List, Dict]] = None) -> int:
        """执行SQL语句的核心方法。"""
        try:
            # 使用参数化查询来防止数据注入
            return self._cursor.execute(sql, params)
        except pymysql.MySQLError as e:
            self.logger.error(f"SQL Execution Error: {e}\nQuery: {self._cursor.mogrify(sql, params)}")
            raise

    def fetch_one(self, table: str, conditions: Dict[str, Any], columns: Union[List[str], str] = '*') -> Optional[Dict[str, Any]]:
        """查询满足条件的单条记录。"""
        # --- 安全：验证表名和列名 ---
        self._validate_identifiers(table, *conditions.keys())
        
        if isinstance(columns, list):
            self._validate_identifiers(*columns)
            cols = ', '.join([f"`{col}`" for col in columns])
        else:
            cols = '*'  # '*' 是安全的，无需验证

        formatted_table = self._format_table_name(table)
        where_clause = ' AND '.join([f"`{key}` = %s" for key in conditions])
        sql = f"SELECT {cols} FROM {formatted_table} WHERE {where_clause} LIMIT 1"
        
        # --- 安全：对数据值使用参数化查询 ---
        params = tuple(conditions.values())
        self._execute(sql, params)
        return self._cursor.fetchone()

    def fetch_all(self, table: str, conditions: Optional[Dict[str, Any]] = None, columns: Union[List[str], str] = '*') -> List[Dict[str, Any]]:
        """查询满足条件的所有记录。"""
        # --- 安全：验证表名和列名 ---
        self._validate_identifiers(table)
        
        if isinstance(columns, list):
            self._validate_identifiers(*columns)
            cols = ', '.join([f"`{col}`" for col in columns])
        else:
            cols = '*'
        
        formatted_table = self._format_table_name(table)
        sql = f"SELECT {cols} FROM {formatted_table}"
        params = None

        if conditions:
            self._validate_identifiers(*conditions.keys())
            where_clause = ' AND '.join([f"`{key}` = %s" for key in conditions])
            sql += f" WHERE {where_clause}"
            # --- 安全：对数据值使用参数化查询 ---
            params = tuple(conditions.values())

        self._execute(sql, params)
        return self._cursor.fetchall()

    def insert(self, table: str, data: Dict[str, Any]) -> int:
        """向表中插入一条数据，并返回新插入行的主键 ID。"""
        if not data:
            raise ValueError("Insert data cannot be empty.")
        
        # --- 安全：验证表名和列名 ---
        self._validate_identifiers(table, *data.keys())

        formatted_table = self._format_table_name(table)
        keys = ', '.join([f"`{key}`" for key in data.keys()])
        values_placeholder = ', '.join(['%s'] * len(data))
        sql = f"INSERT INTO {formatted_table} ({keys}) VALUES ({values_placeholder})"
        
        # --- 安全：对数据值使用参数化查询 ---
        params = tuple(data.values())
        self._execute(sql, params)
        return self._cursor.lastrowid

    def update(self, table: str, data: Dict[str, Any], conditions: Dict[str, Any]) -> int:
        """更新表中的数据，并返回受影响的行数。"""
        if not data:
            raise ValueError("Update data cannot be empty.")
        if not conditions:
            raise ValueError("Update conditions cannot be empty to prevent updating all rows.")

        # --- 安全：验证表名和列名 ---
        self._validate_identifiers(table, *data.keys(), *conditions.keys())

        formatted_table = self._format_table_name(table)
        set_clause = ', '.join([f"`{key}` = %s" for key in data.keys()])
        where_clause = ' AND '.join([f"`{key}` = %s" for key in conditions.keys()])
        sql = f"UPDATE {formatted_table} SET {set_clause} WHERE {where_clause}"

        # --- 安全：对数据值使用参数化查询 ---
        params = tuple(data.values()) + tuple(conditions.values())
        return self._execute(sql, params)

    def delete(self, table: str, conditions: Dict[str, Any]) -> int:
        """从表中删除数据，并返回受影响的行数。"""
        if not conditions:
            raise ValueError("Delete conditions cannot be empty to prevent deleting all rows.")
            
        # --- 安全：验证表名和列名 ---
        self._validate_identifiers(table, *conditions.keys())

        formatted_table = self._format_table_name(table)
        where_clause = ' AND '.join([f"`{key}` = %s" for key in conditions.keys()])
        sql = f"DELETE FROM {formatted_table} WHERE {where_clause}"

        # --- 安全：对数据值使用参数化查询 ---
        params = tuple(conditions.values())
        return self._execute(sql, params)

    def execute_query(self, sql: str, params: Optional[Union[Tuple, List, Dict]] = None) -> List[Dict[str, Any]]:
        """
        【慎用】执行自定义的 SELECT 查询。
        调用者需确保SQL字符串本身是安全的，不包含来自用户输入的表名或列名。
        """
        self._execute(sql, params)
        return self._cursor.fetchall()

    def execute_update(self, sql: str, params: Optional[Union[Tuple, List, Dict]] = None) -> int:
        """
        【慎用】执行自定义的 INSERT, UPDATE, DELETE 等修改性操作。
        调用者需确保SQL字符串本身是安全的，不包含来自用户输入的表名或列名。
        """
        return self._execute(sql, params)