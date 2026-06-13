"""测试运行对话框。

异步调起 pytest 子进程，实时把 stdout / stderr 写到只读文本框；
不阻塞 UI，不让用户面对死等。

设计要点：
- 用 QProcess（Qt 原生）而不是 subprocess.Popen，stdout/stderr 通过信号异步回流，
  不会卡住 GUI 主循环。
- 进程路径用 sys.executable，避免"系统 python 装了 pytest 但 venv 没装"导致的跑不起来。
- 工作目录切到项目根（让 pytest 找到 pytest.ini / conftest.py）。
- 用 offscreen 平台变量导出给子进程，避免子进程尝试弹窗。
- 末尾给一个 [通过/失败/错误] 总结条，按 ESC 或关闭按钮退出。
"""
import os
import re
import sys
from pathlib import Path

from PyQt5.QtCore import Qt, QProcess, QProcessEnvironment
from PyQt5.QtGui import QFont, QTextCursor
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


# pytest 末尾的 "=== 1 passed in 0.12s ===" / "=== 1 failed, 2 passed in 0.30s ==="
# 用这条作为最终汇总的视觉锚
_PYTEST_SUMMARY_RE = re.compile(
    r"=+\s*(?P<body>.+?)\s*in\s+[\d.]+s\s*=+",
    re.IGNORECASE,
)


class TestRunnerDialog(QDialog):
    """测试运行对话框：异步跑 pytest，实时打印 + 总结。"""

    # 默认跑的命令行参数
    DEFAULT_ARGS = [
        "-m", "pytest",
        "tests",
        "-v",
        "--tb=short",
        "--color=no",  # 关闭 ANSI 颜色，避免在文本框里看到乱码
    ]

    def __init__(self, project_root: Path, parent=None):
        super().__init__(parent)
        self.project_root = Path(project_root)
        self.process: QProcess = None
        self._summary = ""  # 缓存 pytest 输出的最后一段汇总
        self._has_failed = False

        self.setWindowTitle("运行测试")
        self.resize(900, 600)
        self.setModal(True)

        # ----- UI -----
        layout = QVBoxLayout(self)

        # 顶部状态行
        self.status_label = QLabel("准备就绪")
        self.status_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.status_label)

        # 输出文本框
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(10)
        self.output.setFont(mono)
        self.output.setLineWrapMode(QTextEdit.NoWrap)
        layout.addWidget(self.output, stretch=1)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.run_btn = QPushButton("▶ 运行")
        self.run_btn.clicked.connect(self.start)
        self.cancel_btn = QPushButton("✕ 取消")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel)
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.run_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.close_btn)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # 启动 / 取消
    # ------------------------------------------------------------------
    def start(self):
        """启动 pytest 子进程。"""
        if self.process is not None and self.process.state() != QProcess.NotRunning:
            return  # 已经在跑

        self.output.clear()
        self._summary = ""
        self._has_failed = False
        self._set_status("正在运行…", running=True)
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

        # 命令与参数
        program = sys.executable
        arguments = list(self.DEFAULT_ARGS)

        # QProcess + 子进程环境
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)  # stdout + stderr 合并
        self.process.setWorkingDirectory(str(self.project_root))

        env = QProcessEnvironment.systemEnvironment()
        env.insert("QT_QPA_PLATFORM", "offscreen")  # 强制子进程无头
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUNBUFFERED", "1")  # 关键：让 pytest 不缓冲
        # 反递归哨兵：子进程 pytest 看到这变量时应当跳过 TestRunnerDialog
        # 自身的元测试，避免无限子进程。
        env.insert("HEAVEN_TEST_RUNNER_NESTED", "1")
        self.process.setProcessEnvironment(env)

        # 信号
        self.process.readyReadStandardOutput.connect(self._on_output)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_error)

        # 启动
        self.process.start(program, arguments)

    def cancel(self):
        """温和地取消：先 kill pytest，让它自己清理。"""
        if self.process is None or self.process.state() == QProcess.NotRunning:
            return
        self._set_status("正在取消…")
        self.process.kill()

    # ------------------------------------------------------------------
    # 进程事件
    # ------------------------------------------------------------------
    def _on_output(self):
        """stdout 流入：append 到文本框，捕获最后一段作为 summary。"""
        if self.process is None:
            return
        chunk = bytes(self.process.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        )
        if not chunk:
            return
        self._append(chunk)
        # 记录最后一行看起来像 summary 的行
        for line in chunk.splitlines():
            m = _PYTEST_SUMMARY_RE.search(line)
            if m:
                self._summary = line.strip()

    def _on_finished(self, exit_code: int, exit_status):
        """pytest 退出。"""
        if exit_code == 0:
            self._set_status("✓ 全部通过", running=False, success=True)
        elif exit_code == 1:
            # 1 = 有用例失败（不是 crash）
            self._has_failed = True
            self._set_status("✗ 有用例失败", running=False, success=False)
        elif exit_code == 2:
            # 2 = pytest 自身报错（collection error 等）
            self._set_status(
                f"⚠ pytest 异常退出（exit={exit_code}）", running=False, success=False
            )
        else:
            # 5 = 没收集到用例；其他 = signal / 中断
            self._set_status(
                f"⚠ 进程退出（exit={exit_code}）", running=False, success=False
            )

        # 把收集到的 summary 拼到状态条
        if self._summary:
            self.status_label.setText(
                f"{self.status_label.text()}    {self._summary}"
            )

        self._reset_buttons()
        self._delete_process()

    def _on_error(self, err):
        """QProcess 自身错误（启动失败等）。"""
        self._set_status(f"⚠ 启动失败: {err}", running=False, success=False)
        self._reset_buttons()
        self._delete_process()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _append(self, text: str):
        """往输出框追加，并自动滚到底。"""
        self.output.moveCursor(QTextCursor.End)
        self.output.insertPlainText(text)
        self.output.moveCursor(QTextCursor.End)

    def _set_status(self, msg: str, running: bool = False, success: bool = None):
        """更新顶部状态。颜色根据 success 切换。"""
        self.status_label.setText(msg)
        if success is True:
            self.status_label.setStyleSheet(
                "font-weight: bold; color: #1a7f37; background: #dafbe1; padding: 4px;"
            )
        elif success is False:
            self.status_label.setStyleSheet(
                "font-weight: bold; color: #cf222e; background: #ffebe9; padding: 4px;"
            )
        else:
            color = "#0969da" if running else "#57606a"
            self.status_label.setStyleSheet(
                f"font-weight: bold; color: {color}; padding: 4px;"
            )

    def _reset_buttons(self):
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def _delete_process(self):
        if self.process is not None:
            self.process.deleteLater()
            self.process = None

    # ------------------------------------------------------------------
    # 关闭：兜底 kill
    # ------------------------------------------------------------------
    def reject(self):
        """按 ESC / 关闭按钮时，先 kill 子进程再退出。"""
        if self.process is not None and self.process.state() != QProcess.NotRunning:
            self.process.kill()
            self.process.waitForFinished(2000)
        super().reject()

    def closeEvent(self, event):
        if self.process is not None and self.process.state() != QProcess.NotRunning:
            self.process.kill()
            self.process.waitForFinished(2000)
        super().closeEvent(event)
