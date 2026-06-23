"""HTTP 下载客户端适配器（适配器模式 + 工厂方法）。

负责代理、请求头、超时等基础设施配置；对外暴露单一的
``download_stream`` 接口。下载器只与该接口耦合，不直接依赖 requests，
方便将来替换实现（urllib3 / httpx 等）。
"""
import os
from typing import Optional

import requests
import urllib3

from utils.config import Config
from utils.logger import logger

# 禁用 SSL 警告（下载器对自签 CDN 不验证书）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _build_proxies() -> Optional[dict]:
    """根据环境变量构造 requests 代理字典；未配置则返回 None（直连）。"""
    http_proxy = Config.PROXY_HTTP or os.getenv("PROXY_HTTP", "")
    https_proxy = Config.PROXY_HTTPS or os.getenv("PROXY_HTTPS", "")
    # 兼容旧行为：只配了 PROXY_HTTP 时同时用于 http/https
    if http_proxy and not https_proxy:
        https_proxy = http_proxy
    if not http_proxy and not https_proxy:
        return None
    return {"http": http_proxy, "https": https_proxy}


def build_default_headers() -> dict:
    """构造下载请求头（从 Config 读取，便于在 .env 覆盖 UA/Referer）。"""
    return {
        "User-Agent": Config.DOWNLOAD_USER_AGENT,
        "Referer": Config.DOWNLOAD_REFERER,
    }


class HttpClient:
    """HTTP 客户端适配器。

    封装 requests.get(stream=True)，由工厂创建实例时注入代理和头。
    使用方式::

        client = create_http_client()
        resp = client.download_stream(url)
    """

    def __init__(self, proxies: Optional[dict] = None,
                 headers: Optional[dict] = None,
                 timeout: int = 20,
                 verify_ssl: bool = False):
        self.proxies = proxies
        self.headers = headers or build_default_headers()
        self.timeout = timeout
        self.verify_ssl = verify_ssl

    def download_stream(self, url: str):
        """发起流式下载请求；返回 requests.Response 或抛 RequestException。"""
        logger.debug(f"HTTP GET stream url={url} timeout={self.timeout}s")
        return requests.get(
            url,
            proxies=self.proxies,
            headers=self.headers,
            timeout=self.timeout,
            verify=self.verify_ssl,
            stream=True,
        )


def create_http_client(timeout: int = 20, verify_ssl: bool = False) -> HttpClient:
    """工厂方法：创建注入默认代理/请求头的 HTTP 客户端实例。"""
    return HttpClient(
        proxies=_build_proxies(),
        headers=build_default_headers(),
        timeout=timeout,
        verify_ssl=verify_ssl,
    )
