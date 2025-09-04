#!/usr/bin/python
# -*- coding: UTF-8 -*-

import redis
import logging

class RedisClient:

    def __init__(self, host='localhost', port=6379, db=0, password=None, logger: logging.Logger = None, **kwargs):
        """
        初始化一个新的 Redis 客户端实例和连接池。

        :param host: Redis 主机地址
        :param port: Redis 端口
        :param db: 数据库编号
        :param password: 密码
        :param logger: 日志记录器实例
        :param kwargs: 其他传递给 ConnectionPool 的参数
        """
        self.logger = logger or logging.getLogger(__name__)
        self.client = None
        self.pool = None
        
        try:
            # 创建连接池
            self.pool = redis.ConnectionPool(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=True,  # 自动将 bytes 解码为 utf-8
                **kwargs
            )
            # 基于连接池创建 StrictRedis 客户端
            self.client = redis.StrictRedis(connection_pool=self.pool)
            # 检查连接是否成功
            self.client.ping()
            self.logger.info("Redis client initialized successfully.")
        except redis.exceptions.ConnectionError as e:
            self.logger.error(f"Error connecting to Redis: {e}")
            # 向上抛出异常，让调用者知道连接失败
            raise

    def close(self):
        """
        关闭 Redis 连接，断开连接池。
        """
        if self.pool:
            self.pool.disconnect()
            self.logger.info("Redis connection pool disconnected.")

    def __enter__(self):
        """上下文管理器 entry 方法，返回客户端实例本身。"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器 exit 方法，自动关闭连接。"""
        self.close()

    def get_client(self):
        """
        返回底层的 redis 客户端实例，以便调用未被封装的方法。
        """
        return self.client

    # --- 常用命令的封装 (以下方法无需修改) ---

    def set(self, name, value, ex=None, px=None, nx=False, xx=False):
        """
        设置键值。

        :param name: 键名
        :param value: 键值
        :param ex: (int) 过期时间（秒）
        :param px: (int) 过期时间（毫秒）
        :param nx: (bool) 如果键不存在则设置
        :param xx: (bool) 如果键已存在则设置
        :return: (bool) 是否设置成功
        """
        return self.client.set(name, value, ex=ex, px=px, nx=nx, xx=xx)

    def get(self, name):
        """
        获取键值。

        :param name: 键名
        :return: (str or None) 键的值，如果键不存在则返回 None
        """
        return self.client.get(name)

    def delete(self, *names):
        """
        删除一个或多个键。

        :param names: 一个或多个键名
        :return: (int) 被删除的键的数量
        """
        return self.client.delete(*names)

    def exists(self, name):
        """
        检查键是否存在。

        :param name: 键名
        :return: (int) 1 如果键存在，0 如果不存在
        """
        return self.client.exists(name)
    
    def hset(self, name, key, value):
        """
        在哈希表中设置一个字段的值。

        :param name: 哈希表的键名
        :param key: 字段名
        :param value: 字段值
        :return: (int) 1 如果是新建字段，0 如果是更新已有字段
        """
        return self.client.hset(name, key, value)

    def hget(self, name, key):
        """
        从哈希表中获取一个字段的值。

        :param name: 哈希表的键名
        :param key: 字段名
        :return: (str or None) 字段的值，如果不存在则返回 None
        """
        return self.client.hget(name, key)

    def hgetall(self, name):
        """
        获取哈希表中的所有字段和值。

        :param name: 哈希表的键名
        :return: (dict) 包含字段和值的字典
        """
        return self.client.hgetall(name)

    def incr(self, name, amount=1):
        """
        将键的值增加指定的整数。

        :param name: 键名
        :param amount: (int) 增加的数量
        :return: (int) 增加后的值
        """
        return self.client.incr(name, amount)

    def decr(self, name, amount=1):
        """
        将键的值减少指定的整数。

        :param name: 键名
        :param amount: (int) 减少的数量
        :return: (int) 减少后的值
        """
        return self.client.decr(name, amount)
