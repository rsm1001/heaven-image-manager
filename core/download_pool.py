"""下载线程池模块 - 进程级单例 + 工厂。

通过工厂函数获取/重建线程池，模块间不直接共享可变状态；
只暴露 shutdown 接口给 main 进程退出阶段调用。
"""
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

# 默认线程数（暴露为常量便于测试与配置覆盖）
DEFAULT_MAX_WORKERS = 5

# 进程内单例
_thread_pool: Optional[ThreadPoolExecutor] = None
_pool_lock = threading.Lock()


def get_download_pool(max_workers: int = DEFAULT_MAX_WORKERS) -> ThreadPoolExecutor:
    """获取或创建全局下载线程池（工厂：进程内单例）。"""
    global _thread_pool
    with _pool_lock:
        if _thread_pool is None:
            _thread_pool = ThreadPoolExecutor(max_workers=max_workers)
        return _thread_pool


def shutdown_download_pool() -> None:
    """关闭全局线程池（应用退出时调用）。"""
    global _thread_pool
    with _pool_lock:
        if _thread_pool is not None:
            _thread_pool.shutdown(wait=True)
            _thread_pool = None


def create_pool(max_workers: int = DEFAULT_MAX_WORKERS) -> ThreadPoolExecutor:
    """工厂方法：创建一个全新的独立线程池（不写入单例）。

    适用于短期任务或希望完全独立于全局池的场景。
    """
    return ThreadPoolExecutor(max_workers=max_workers)
