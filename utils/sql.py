#!/usr/bin/python
# -*- coding: UTF-8 -*-

import pymysql
import logging
from pymysql.cursors import DictCursor
from typing import List, Dict, Any, Optional, Tuple, Union

from dbutils.pooled_db import PooledDB

# --- 数据库管理器，全局持有一个实例 ---
class DatabaseManager:
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
                    creator=pymysql,  # 指定使用pymysql作为连接库
                    maxconnections=10,  # 池中最大连接数
                    mincached=2,      # 启动时初始化的连接数
                    maxcached=5,      # 池中最多空闲连接数
                    blocking=True,    # 连接池无可用连接时是否阻塞等待
                    ping=1,           # 在获取连接之前检查连接是否可用 (0=None, 1=default, 2=when_needed, 4=always, 7=never)
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
    """
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._conn = None
        self._cursor = None

    def __enter__(self):
        """上下文管理器 entry 方法，从连接池获取连接。"""
        self._conn = DatabaseManager.get_connection()
        self._cursor = self._conn.cursor()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        上下文管理器 exit 方法，将连接归还给池。
        如果发生异常，则回滚事务；否则，提交事务。
        """
        if self._cursor:
            self._cursor.close()
        if self._conn:
            if exc_type:
                self.logger.warning(f"An exception occurred. Rolling back transaction. Error: {exc_val}")
                self._conn.rollback()
            else:
                self._conn.commit()
            # 对于 PooledDB， close() 方法意味着将连接放回池中，而不是真正关闭它
            self._conn.close()

    def _format_table_name(self, table: str) -> str:
        """
        正确地为表名加反引号，能处理 'database.table' 格式。
        """
        if '.' in table:
            # e.g., 'information_schema.TABLES' becomes `information_schema`.`TABLES`
            return '.'.join([f"`{part}`" for part in table.split('.', 1)])
        else:
            # e.g., 'users' becomes `users`
            return f"`{table}`"

    def _execute(self, sql: str, params: Optional[Union[Tuple, List, Dict]] = None) -> int:
        """执行SQL语句的核心方法。"""
        try:
            return self._cursor.execute(sql, params)
        except pymysql.MySQLError as e:
            self.logger.error(f"SQL Execution Error: {e}\nQuery: {sql}\nParams: {params}")
            raise

    def fetch_one(self, table: str, conditions: Dict[str, Any], columns: Union[List[str], str] = '*') -> Optional[Dict[str, Any]]:
        """查询满足条件的单条记录。"""
        if isinstance(columns, list):
            cols = ', '.join([f"`{col}`" for col in columns])
        else:
            cols = '*'

        formatted_table = self._format_table_name(table)
        where_clause = ' AND '.join([f"`{key}` = %s" for key in conditions])
        sql = f"SELECT {cols} FROM {formatted_table} WHERE {where_clause} LIMIT 1"
        
        params = tuple(conditions.values())
        self._execute(sql, params)
        return self._cursor.fetchone()

    def fetch_all(self, table: str, conditions: Optional[Dict[str, Any]] = None, columns: Union[List[str], str] = '*') -> List[Dict[str, Any]]:
        """查询满足条件的所有记录。"""
        if isinstance(columns, list):
            cols = ', '.join([f"`{col}`" for col in columns])
        else:
            cols = '*'
        
        formatted_table = self._format_table_name(table)
        sql = f"SELECT {cols} FROM {formatted_table}"
        params = None

        if conditions:
            where_clause = ' AND '.join([f"`{key}` = %s" for key in conditions])
            sql += f" WHERE {where_clause}"
            params = tuple(conditions.values())

        self._execute(sql, params)
        return self._cursor.fetchall()

    def insert(self, table: str, data: Dict[str, Any]) -> int:
        """向表中插入一条数据，并返回新插入行的主键 ID。"""
        formatted_table = self._format_table_name(table)
        keys = ', '.join([f"`{key}`" for key in data.keys()])
        values_placeholder = ', '.join(['%s'] * len(data))
        sql = f"INSERT INTO {formatted_table} ({keys}) VALUES ({values_placeholder})"
        
        params = tuple(data.values())
        self._execute(sql, params)
        return self._cursor.lastrowid

    def update(self, table: str, data: Dict[str, Any], conditions: Dict[str, Any]) -> int:
        """更新表中的数据，并返回受影响的行数。"""
        formatted_table = self._format_table_name(table)
        set_clause = ', '.join([f"`{key}` = %s" for key in data.keys()])
        where_clause = ' AND '.join([f"`{key}` = %s" for key in conditions.keys()])
        sql = f"UPDATE {formatted_table} SET {set_clause} WHERE {where_clause}"

        params = tuple(data.values()) + tuple(conditions.values())
        affected_rows = self._execute(sql, params)
        return affected_rows

    def delete(self, table: str, conditions: Dict[str, Any]) -> int:
        """从表中删除数据，并返回受影响的行数。"""
        formatted_table = self._format_table_name(table)
        where_clause = ' AND '.join([f"`{key}` = %s" for key in conditions.keys()])
        sql = f"DELETE FROM {formatted_table} WHERE {where_clause}"

        params = tuple(conditions.values())
        affected_rows = self._execute(sql, params)
        return affected_rows

    def execute_query(self, sql: str, params: Optional[Union[Tuple, List, Dict]] = None) -> List[Dict[str, Any]]:
        """执行自定义的 SELECT 查询并返回所有结果。"""
        self._execute(sql, params)
        return self._cursor.fetchall()

    def execute_update(self, sql: str, params: Optional[Union[Tuple, List, Dict]] = None) -> int:
        """执行自定义的 INSERT, UPDATE, DELETE 等修改性操作。"""
        affected_rows = self._execute(sql, params)
        return affected_rows
