"""core.downloader DownloadWorker 集成测试。

用 responses 拦截 18comic CDN 的 HTTP 调用，用 pytest-qt 的 qtbot 驱动 QThread 信号。

约束：
- 仓库根 .env 没有代理；通过 monkeypatch env 显式清空 PROXY_HTTP / PROXY_HTTPS，
  避免 downloader 拿默认 127.0.0.1:7897 真去连。
- 全部 *_DELAY 用 autouse fixture 改成 0/1，CI 跑得动。
- shutdown_download_pool 在每个测试结束后清理全局线程池。
"""
import io
import json
import os
import threading
import time
from pathlib import Path

import pytest
import responses as responses_lib
from PIL import Image

from core.downloader import (
    DownloadRecord,
    DownloadWorker,
    get_download_pool,
    shutdown_download_pool,
)
from utils import config as config_mod
from utils.logger import logger
from tests.fixtures.jsons import write_json


# ----------------------------------------------------------------------
# 全局 fixture：清代理、清延迟，每个测试后清线程池
# ----------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _fast_delays(monkeypatch):
    monkeypatch.setattr(config_mod.Config, "RETRY_TIMES", 1)
    monkeypatch.setattr(config_mod.Config, "RETRY_DELAY", 0)
    monkeypatch.setattr(config_mod.Config, "REQUEST_DELAY", 0)
    monkeypatch.setattr(config_mod.Config, "PROXY_RETRY_TIMES", 1)
    monkeypatch.setattr(config_mod.Config, "PROXY_RETRY_DELAY", 0)
    monkeypatch.setenv("PROXY_HTTP", "")
    monkeypatch.setenv("PROXY_HTTPS", "")
    yield
    # 清理全局线程池，避免下一个测试继承状态
    shutdown_download_pool()


@pytest.fixture
def mocked_responses():
    """responses 上下文，assert_all_requests_are_fired=False 让我们可以注册多余响应。"""
    with responses_lib.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        yield rsps


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _url_for(img_id: int) -> str:
    return config_mod.Config.BASE_URL.format(img_id)


def _jpg_bytes(size_kb: int = 4) -> bytes:
    """生成至少 size_kb KB 的 JPEG 字节流，足以让 ImageValidator 视为合法。"""
    img = Image.new("RGB", (32, 32), (255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    raw = buf.getvalue()
    # 填充到 size_kb KB
    if len(raw) < size_kb * 1024:
        raw = raw + b"\x00" * (size_kb * 1024 - len(raw))
    return raw


# ======================================================================
# DownloadRecord 单元子测试（不需要 QThread）
# ======================================================================
class TestDownloadRecord:
    def test_load_no_file(self, download_records_path):
        assert DownloadRecord.load_records() == {}

    def test_load_corrupted(self, download_records_path):
        download_records_path.write_text("{ bad json", encoding="utf-8")
        assert DownloadRecord.load_records() == {}

    def test_load_normalizes_int_keys(self, download_records_path):
        download_records_path.write_text(
            json.dumps({"1": {"status": "success"}, "2": {"status": "failed"}}),
            encoding="utf-8",
        )
        loaded = DownloadRecord.load_records()
        assert set(loaded.keys()) == {1, 2}

    def test_save_no_trim_under_cap(self, download_records_path):
        records = {i: {"status": "success", "downloaded_time": "2026-01-01"} for i in range(3)}
        assert DownloadRecord.save_records(records) is True
        assert len(DownloadRecord.load_records()) == 3

    def test_save_trims_to_cap_failed_first(self, download_records_path, monkeypatch):
        monkeypatch.setattr(config_mod.Config, "MAX_DOWNLOAD_RECORD_COUNT", 2)
        records = {}
        for i in range(5):
            if i < 3:
                records[i] = {"status": "failed", "failed_time": f"2026-01-01 00:00:0{i}"}
            else:
                records[i] = {"status": "success", "downloaded_time": f"2026-01-01 00:00:0{i}"}
        DownloadRecord.save_records(records)
        loaded = DownloadRecord.load_records()
        # 排序：failed 优先 + 时间升序；保留最后 2 条 = 时间最晚的 2 个 success
        assert set(loaded.keys()) == {3, 4}
        assert all(loaded[k]["status"] == "success" for k in loaded)

    def test_get_completed_ids(self, download_records_path):
        write_json(download_records_path, {
            "1": {"status": "success"},
            "2": {"status": "failed"},
            "3": {"status": "success"},
        })
        assert DownloadRecord.get_completed_ids() == {1, 3}

    def test_get_existing_file_ids(self, config_paths):
        comic = config_paths["comic"]
        # 写 2 张数字 stem
        (comic / "100.jpg").write_bytes(_jpg_bytes())
        (comic / "200.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        # 非数字 stem
        (comic / "abc.jpg").write_bytes(b"x")
        ids = DownloadRecord.get_existing_file_ids()
        assert ids == {100, 200}


# ======================================================================
# 线程池单例
# ======================================================================
class TestThreadPool:
    def test_get_download_pool_is_singleton(self):
        a = get_download_pool()
        b = get_download_pool()
        assert a is b

    def test_shutdown_then_get_returns_new(self):
        a = get_download_pool()
        shutdown_download_pool()
        b = get_download_pool()
        assert a is not b
        shutdown_download_pool()


# ======================================================================
# DownloadWorker.run() 集成测试
# ======================================================================
class TestDownloadWorker:
    def test_happy_path_three_images(
        self, mocked_responses, qtbot, config_paths, download_records_path
    ):
        ids = [9001, 9002, 9003]
        body = _jpg_bytes(4)
        for i in ids:
            mocked_responses.add(
                responses_lib.GET, _url_for(i), body=body, status=200
            )
        worker = DownloadWorker(start_id=ids[0], count=len(ids), max_workers=2)
        with qtbot.waitSignal(worker.completed_signal, timeout=15000) as blocker:
            worker.start()
        result = blocker.args[0]

        assert result["success"] is True
        assert result["success_count"] == 3
        assert result["fail_count"] == 0
        assert result["cancelled"] is False
        for i in ids:
            assert (config_paths["comic"] / f"{i}.jpg").exists()
            assert (config_paths["comic"] / f"{i}.jpg").stat().st_size > 0

        records = DownloadRecord.load_records()
        assert len(records) == 3
        for i in ids:
            assert records[i]["status"] == "success"
            assert "downloaded_time" in records[i]
            assert records[i]["file_size"] > 0

    def test_skip_existing_file(
        self, mocked_responses, qtbot, config_paths, download_records_path
    ):
        (config_paths["comic"] / "9001.jpg").write_bytes(_jpg_bytes())
        worker = DownloadWorker(start_id=9001, count=1, max_workers=1)
        with qtbot.waitSignal(worker.completed_signal, timeout=10000) as blocker:
            worker.start()
        result = blocker.args[0]
        assert result["success_count"] == 0
        assert 9001 in result["skipped"]
        # 没有 HTTP 调用
        assert len(mocked_responses.calls) == 0

    def test_skip_already_completed(
        self, mocked_responses, qtbot, config_paths, download_records_path
    ):
        write_json(download_records_path, {
            "9001": {"status": "success", "downloaded_time": "2026-01-01 00:00:00"}
        })
        worker = DownloadWorker(start_id=9001, count=1, max_workers=1)
        with qtbot.waitSignal(worker.completed_signal, timeout=10000) as blocker:
            worker.start()
        result = blocker.args[0]
        assert result["success_count"] == 0
        assert 9001 in result["skipped"]
        assert len(mocked_responses.calls) == 0

    def test_partial_failure_500(
        self, mocked_responses, qtbot, config_paths
    ):
        mocked_responses.add(responses_lib.GET, _url_for(9001), body=_jpg_bytes(), status=200)
        mocked_responses.add(responses_lib.GET, _url_for(9002), body="err", status=500)
        mocked_responses.add(responses_lib.GET, _url_for(9003), body=_jpg_bytes(), status=200)
        worker = DownloadWorker(start_id=9001, count=3, max_workers=2)
        with qtbot.waitSignal(worker.completed_signal, timeout=15000) as blocker:
            worker.start()
        result = blocker.args[0]
        assert result["success_count"] == 2
        assert result["fail_count"] == 1
        assert 9002 in result["fail_ids"]
        # 磁盘：9001 / 9003 存在，9002 不存在
        assert (config_paths["comic"] / "9001.jpg").exists()
        assert not (config_paths["comic"] / "9002.jpg").exists()
        assert (config_paths["comic"] / "9003.jpg").exists()
        # records：9002 标 failed
        records = DownloadRecord.load_records()
        assert records[9001]["status"] == "success"
        assert records[9002]["status"] == "failed"
        assert "failed_time" in records[9002]
        assert records[9003]["status"] == "success"

    def test_502_then_200_retries(
        self, mocked_responses, qtbot, config_paths, monkeypatch
    ):
        # 让 RETRY_TIMES=2 走重试路径
        monkeypatch.setattr(config_mod.Config, "RETRY_TIMES", 2)
        mocked_responses.add(responses_lib.GET, _url_for(9001), body="bad", status=502)
        mocked_responses.add(responses_lib.GET, _url_for(9001), body=_jpg_bytes(), status=200)
        worker = DownloadWorker(start_id=9001, count=1, max_workers=1)
        with qtbot.waitSignal(worker.completed_signal, timeout=15000) as blocker:
            worker.start()
        result = blocker.args[0]
        assert result["success_count"] == 1
        assert result["fail_count"] == 0
        assert len(mocked_responses.calls) == 2
        assert (config_paths["comic"] / "9001.jpg").exists()

    def test_retries_exhausted_502(
        self, mocked_responses, qtbot, config_paths, monkeypatch
    ):
        monkeypatch.setattr(config_mod.Config, "RETRY_TIMES", 2)
        mocked_responses.add(responses_lib.GET, _url_for(9001), body="bad", status=502)
        mocked_responses.add(responses_lib.GET, _url_for(9001), body="bad", status=502)
        worker = DownloadWorker(start_id=9001, count=1, max_workers=1)
        with qtbot.waitSignal(worker.completed_signal, timeout=15000) as blocker:
            worker.start()
        result = blocker.args[0]
        assert result["success_count"] == 0
        assert result["fail_count"] == 1
        assert 9001 in result["fail_ids"]
        assert len(mocked_responses.calls) == 2

    def test_all_skipped_emits_completed(
        self, mocked_responses, qtbot, download_records_path
    ):
        write_json(download_records_path, {
            str(i): {"status": "success", "downloaded_time": "2026-01-01"}
            for i in range(9001, 9006)
        })
        worker = DownloadWorker(start_id=9001, count=5, max_workers=1)
        with qtbot.waitSignal(worker.completed_signal, timeout=10000) as blocker:
            worker.start()
        result = blocker.args[0]
        assert result["success_count"] == 0
        assert result["fail_count"] == 0
        assert result["total"] == 5
        assert len(result["skipped"]) == 5

    def test_progress_signal_emitted(
        self, mocked_responses, qtbot, config_paths
    ):
        ids = [9101, 9102, 9103]
        for i in ids:
            mocked_responses.add(
                responses_lib.GET, _url_for(i), body=_jpg_bytes(), status=200
            )
        worker = DownloadWorker(start_id=ids[0], count=len(ids), max_workers=1)

        progress = []
        worker.progress_signal.connect(lambda cur, status: progress.append((cur, status)))

        with qtbot.waitSignal(worker.completed_signal, timeout=15000):
            worker.start()

        # 3 张图，进度 1..3 各一次
        assert len(progress) == 3
        assert [p[0] for p in progress] == [1, 2, 3]
        # 状态文本以"成功"/"失败"开头
        for _, status in progress:
            assert status.startswith("成功") or status.startswith("失败")

    def test_cancel(
        self, mocked_responses, qtbot, config_paths
    ):
        """在请求进行中取消，应得到 cancelled=True 的 completed_signal。"""
        def slow(request):
            time.sleep(0.5)
            return (200, {}, _jpg_bytes())

        mocked_responses.add_callback(
            responses_lib.GET, _url_for(9001), callback=slow
        )
        worker = DownloadWorker(start_id=9001, count=1, max_workers=1)
        with qtbot.waitSignal(worker.completed_signal, timeout=15000) as blocker:
            worker.start()
            # 给 worker 一点时间把请求发出去
            qtbot.wait(100)
            worker.cancel_download()
        result = blocker.args[0]
        assert result["cancelled"] is True
        # 取消时请求未完成，success_count 应当为 0
        assert result["success_count"] == 0
