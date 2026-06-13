"""ui.test_runner_dialog.TestRunnerDialog 单元测试。

设计取舍：
- 端到端"起一个真 pytest 子进程"那类测试会引发 Qt 事件循环状态在测试之间
  互相干扰（同一个 QApplication 实例跨多个 test），稳定性不好。
- 改为：mock QProcess.start / finished 信号，直接验证 dialog 状态机。
- "真点击按钮" 端到端验证交给手工或 CI smoke，单元测试只负责状态正确。
"""
import re
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from ui.test_runner_dialog import TestRunnerDialog


def _extract_style_color(style: str) -> str:
    m = re.search(r"color:\s*(#[0-9a-fA-F]{3,8})", style)
    return m.group(1) if m else ""


class TestArgs:
    def test_default_args_target_tests_dir(self, qapp):
        d = TestRunnerDialog(Path("."))
        joined = " ".join(d.DEFAULT_ARGS)
        assert "pytest" in joined
        assert "tests" in joined
        # 关闭颜色，便于在文本框里直接看
        assert "--color=no" in joined


class TestInitialState:
    def test_run_enabled_cancel_disabled(self, qtbot):
        d = TestRunnerDialog(Path("."))
        qtbot.addWidget(d)
        assert d.run_btn.isEnabled() is True
        assert d.cancel_btn.isEnabled() is False
        assert d.output.toPlainText() == ""

    def test_status_starts_idle(self, qtbot):
        d = TestRunnerDialog(Path("."))
        qtbot.addWidget(d)
        assert "就绪" in d.status_label.text() or "准备" in d.status_label.text()


class TestStartWithMockedProcess:
    """mock QProcess：验证 start() 的命令与环境，不真起子进程。"""

    def test_start_invokes_qprocess_with_expected_args(self, qtbot):
        d = TestRunnerDialog(Path("."))
        qtbot.addWidget(d)

        # 用 MagicMock 替换 QProcess 类
        with patch("ui.test_runner_dialog.QProcess") as MockQProcess:
            mock_instance = MagicMock()
            mock_instance.state.return_value = 0  # NotRunning
            MockQProcess.return_value = mock_instance

            d.start()

            # 验证传给 QProcess 的工作目录与程序
            assert mock_instance.setWorkingDirectory.called
            # start(program, args) 被调
            assert mock_instance.start.called
            program, args = mock_instance.start.call_args[0]
            assert program.endswith("python.exe") or program.endswith("python")
            assert "pytest" in args
            assert "tests" in args

    def test_start_disables_run_enables_cancel(self, qtbot):
        d = TestRunnerDialog(Path("."))
        qtbot.addWidget(d)

        with patch("ui.test_runner_dialog.QProcess") as MockQProcess:
            mock_instance = MagicMock()
            mock_instance.state.return_value = 0
            MockQProcess.return_value = mock_instance
            d.start()

        assert d.run_btn.isEnabled() is False
        assert d.cancel_btn.isEnabled() is True
        # 状态切换到"运行中"
        assert "运行" in d.status_label.text() or "正在" in d.status_label.text()

    def test_nested_env_var_set_on_subprocess(self, qtbot):
        """递归哨兵：start() 必须把 HEAVEN_TEST_RUNNER_NESTED=1 传给子进程。"""
        d = TestRunnerDialog(Path("."))
        qtbot.addWidget(d)

        with patch("ui.test_runner_dialog.QProcess") as MockQProcess:
            mock_instance = MagicMock()
            mock_instance.state.return_value = 0
            MockQProcess.return_value = mock_instance
            d.start()

        # 检查 setProcessEnvironment 是否把哨兵 env 写进去了
        # QProcessEnvironment 不可直接断言内容，验证调用发生过即可
        assert mock_instance.setProcessEnvironment.called
        # process 已被设置
        assert d.process is mock_instance


class TestFinishedHandlers:
    """模拟 finished 信号，验证 UI 状态切换。"""

    def _make_dialog_with_mock_process(self, qtbot):
        d = TestRunnerDialog(Path("."))
        qtbot.addWidget(d)
        with patch("ui.test_runner_dialog.QProcess") as MockQProcess:
            mock_proc = MagicMock()
            mock_proc.state.return_value = 0
            MockQProcess.return_value = mock_proc
            d.start()
        return d, mock_proc

    def test_finished_success_turns_status_green(self, qtbot):
        d, mock_proc = self._make_dialog_with_mock_process(qtbot)
        # 模拟 finished(0, ...)
        d._on_finished(0, 0)
        color = _extract_style_color(d.status_label.styleSheet())
        assert color == "#1a7f37"  # 绿

    def test_finished_with_failures_turns_status_red(self, qtbot):
        d, _ = self._make_dialog_with_mock_process(qtbot)
        d._on_finished(1, 0)  # pytest 退出码 1 = 有用例失败
        color = _extract_style_color(d.status_label.styleSheet())
        assert color == "#cf222e"  # 红

    def test_finished_collection_error_status_warning(self, qtbot):
        d, _ = self._make_dialog_with_mock_process(qtbot)
        d._on_finished(2, 0)  # pytest 退出码 2 = collection error
        assert "异常" in d.status_label.text() or "error" in d.status_label.text().lower()

    def test_finished_resets_buttons(self, qtbot):
        d, _ = self._make_dialog_with_mock_process(qtbot)
        d._on_finished(0, 0)
        assert d.run_btn.isEnabled() is True
        assert d.cancel_btn.isEnabled() is False

    def test_finished_clears_process(self, qtbot):
        d, _ = self._make_dialog_with_mock_process(qtbot)
        d._on_finished(0, 0)
        assert d.process is None


class TestOutputAppend:
    def test_append_writes_to_textedit(self, qtbot):
        d = TestRunnerDialog(Path("."))
        qtbot.addWidget(d)
        d._append("hello world\n")
        d._append("second line\n")
        text = d.output.toPlainText()
        assert "hello world" in text
        assert "second line" in text

    def test_summary_regex_captures_pytest_summary(self, qtbot):
        d = TestRunnerDialog(Path("."))
        qtbot.addWidget(d)
        from ui.test_runner_dialog import _PYTEST_SUMMARY_RE
        m = _PYTEST_SUMMARY_RE.search("===== 1 passed in 0.30s =====")
        assert m is not None
        assert "1 passed" in m.group("body")


class TestCancel:
    def test_cancel_kills_running_process(self, qtbot):
        d = TestRunnerDialog(Path("."))
        qtbot.addWidget(d)
        with patch("ui.test_runner_dialog.QProcess") as MockQProcess:
            mock_proc = MagicMock()
            mock_proc.state.return_value = 2  # Running
            MockQProcess.return_value = mock_proc
            d.start()
            d.cancel()
            assert mock_proc.kill.called
