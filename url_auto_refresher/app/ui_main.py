from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QSettings, QTimer, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app_info import APP_VERSION, RELEASES_URL
from browser_runner import RefreshConfig
from refresh_worker import RefreshWorker
from update_checker import UpdateCheckerWorker, UpdateCheckResult
from utils import validate_url


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.worker: RefreshWorker | None = None
        self.update_worker: UpdateCheckerWorker | None = None
        self._total_tasks = 0
        self._update_check_is_manual = False
        self.settings = QSettings("Authorized Test Tools", "URL Auto Refresher")

        self.setWindowTitle(f"URL Auto Refresher v{APP_VERSION} - 授权网址刷新测试器")
        self.setMinimumSize(880, 680)
        self._build_ui()
        self._apply_style()
        self._set_status("准备中")
        QTimer.singleShot(1200, self._maybe_auto_check_updates)

    def _build_ui(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        title = QLabel("URL Auto Refresher", self)
        title.setObjectName("TitleLabel")
        subtitle = QLabel(
            "仅限自有或已授权网址测试使用，请勿用于刷访问量或干扰第三方网站。",
            self,
        )
        subtitle.setObjectName("SubtitleLabel")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)

        update_row = QHBoxLayout()
        self.version_label = QLabel(f"当前版本：v{APP_VERSION}", self)
        self.version_label.setObjectName("VersionLabel")
        self.auto_update_checkbox = QCheckBox("启动时自动检查更新", self)
        self.auto_update_checkbox.setChecked(self._auto_update_enabled())
        self.auto_update_checkbox.toggled.connect(self._save_auto_update_enabled)
        self.update_button = QPushButton("检查更新", self)
        self.update_button.setObjectName("SecondaryButton")
        self.update_button.clicked.connect(lambda: self._check_for_updates(manual=True))
        update_row.addWidget(self.version_label)
        update_row.addStretch(1)
        update_row.addWidget(self.auto_update_checkbox)
        update_row.addWidget(self.update_button)
        layout.addLayout(update_row)

        form_box = QGroupBox("测试参数", self)
        form_layout = QGridLayout(form_box)
        form_layout.setContentsMargins(18, 20, 18, 18)
        form_layout.setHorizontalSpacing(14)
        form_layout.setVerticalSpacing(12)

        self.url_input = QLineEdit(self)
        self.url_input.setPlaceholderText("https://example.com/test")
        self.url_input.setClearButtonEnabled(True)

        self.interval_spin = QSpinBox(self)
        self.interval_spin.setRange(1, 86_400)
        self.interval_spin.setValue(5)
        self.interval_spin.setSuffix(" 秒")

        self.page_count_spin = QSpinBox(self)
        self.page_count_spin.setRange(1, 100)
        self.page_count_spin.setValue(5)

        self.refresh_count_spin = QSpinBox(self)
        self.refresh_count_spin.setRange(1, 1_000_000)
        self.refresh_count_spin.setValue(2)

        self.headless_checkbox = QCheckBox("后台运行", self)
        self.auth_checkbox = QCheckBox("我确认该网址为自有或已授权测试网址", self)

        form_layout.addWidget(QLabel("网址：", self), 0, 0)
        form_layout.addWidget(self.url_input, 0, 1, 1, 3)
        form_layout.addWidget(QLabel("刷新秒数：", self), 1, 0)
        form_layout.addWidget(self.interval_spin, 1, 1)
        form_layout.addWidget(QLabel("同时运行网页数量：", self), 1, 2)
        form_layout.addWidget(self.page_count_spin, 1, 3)
        form_layout.addWidget(QLabel("刷新次数：", self), 2, 0)
        form_layout.addWidget(self.refresh_count_spin, 2, 1)
        form_layout.addWidget(self.headless_checkbox, 2, 2)
        form_layout.addWidget(self.auth_checkbox, 2, 3)
        form_layout.setColumnStretch(1, 1)
        form_layout.setColumnStretch(3, 1)
        layout.addWidget(form_box)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.start_button = QPushButton("开始运行", self)
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.clicked.connect(self._start_clicked)
        self.stop_button = QPushButton("停止运行", self)
        self.stop_button.setObjectName("DangerButton")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop_clicked)
        button_row.addWidget(self.start_button)
        button_row.addWidget(self.stop_button)
        layout.addLayout(button_row)

        progress_box = QGroupBox("运行进度：", self)
        progress_layout = QVBoxLayout(progress_box)
        progress_layout.setContentsMargins(18, 20, 18, 18)
        progress_layout.setSpacing(10)

        status_row = QHBoxLayout()
        self.progress_text = QLabel("当前进度：0 / 0", self)
        self.status_label = QLabel("状态：准备中", self)
        self.status_label.setObjectName("StatusBadge")
        status_row.addWidget(self.progress_text)
        status_row.addStretch(1)
        status_row.addWidget(self.status_label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)

        progress_layout.addLayout(status_row)
        progress_layout.addWidget(self.progress_bar)
        layout.addWidget(progress_box)

        log_label = QLabel("运行日志：", self)
        log_label.setObjectName("SectionLabel")
        self.log_text = QTextEdit(self)
        self.log_text.setReadOnly(True)
        self.log_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.log_text.document().setMaximumBlockCount(1000)
        self.log_text.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        layout.addWidget(log_label)
        layout.addWidget(self.log_text, 1)

        footer_line = QFrame(self)
        footer_line.setFrameShape(QFrame.Shape.HLine)
        footer_line.setObjectName("FooterLine")
        layout.addWidget(footer_line)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: #f5f7fb;
                color: #172033;
                font-family: "Microsoft YaHei", "Segoe UI", Arial;
                font-size: 14px;
            }
            QLabel#TitleLabel {
                color: #102033;
                font-size: 26px;
                font-weight: 700;
            }
            QLabel#SubtitleLabel {
                color: #526074;
                font-size: 13px;
            }
            QLabel#VersionLabel {
                color: #526074;
                font-size: 12px;
            }
            QLabel#SectionLabel {
                color: #28364d;
                font-weight: 600;
            }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #dbe3ef;
                border-radius: 8px;
                color: #26364f;
                font-weight: 600;
                margin-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
            }
            QLineEdit, QSpinBox {
                background: #ffffff;
                border: 1px solid #cfd8e6;
                border-radius: 6px;
                min-height: 34px;
                padding: 4px 8px;
                selection-background-color: #2f80ed;
            }
            QLineEdit:focus, QSpinBox:focus {
                border: 1px solid #2f80ed;
            }
            QCheckBox {
                color: #324258;
                spacing: 8px;
            }
            QPushButton {
                border: 0;
                border-radius: 7px;
                min-width: 112px;
                min-height: 36px;
                padding: 6px 16px;
                font-weight: 600;
            }
            QPushButton#PrimaryButton {
                color: #ffffff;
                background: #1f7a5f;
            }
            QPushButton#PrimaryButton:hover {
                background: #17684f;
            }
            QPushButton#DangerButton {
                color: #ffffff;
                background: #c2413d;
            }
            QPushButton#DangerButton:hover {
                background: #a93633;
            }
            QPushButton#SecondaryButton {
                color: #28364d;
                background: #e7edf5;
                border: 1px solid #ccd6e3;
            }
            QPushButton#SecondaryButton:hover {
                background: #dbe4ef;
            }
            QPushButton:disabled {
                color: #8b97a8;
                background: #d9e0ea;
            }
            QLabel#StatusBadge {
                border-radius: 6px;
                padding: 6px 10px;
                min-width: 110px;
                qproperty-alignment: AlignCenter;
                font-weight: 700;
            }
            QProgressBar {
                background: #e7edf5;
                border: 0;
                border-radius: 6px;
                height: 14px;
            }
            QProgressBar::chunk {
                background: #2f80ed;
                border-radius: 6px;
            }
            QTextEdit {
                background: #0f1725;
                color: #d8e1ef;
                border: 1px solid #202c40;
                border-radius: 8px;
                padding: 10px;
                font-family: Consolas, "Microsoft YaHei UI";
                font-size: 13px;
            }
            QFrame#FooterLine {
                color: #dbe3ef;
            }
            """
        )

    def _start_clicked(self) -> None:
        ok, url_or_message = validate_url(self.url_input.text())
        if not ok:
            QMessageBox.warning(self, "URL 格式错误", url_or_message)
            return

        if not self.auth_checkbox.isChecked():
            QMessageBox.warning(
                self,
                "授权确认",
                "请先确认该网址为自有或已授权测试网址。",
            )
            return

        config = RefreshConfig(
            url=url_or_message,
            interval_seconds=self.interval_spin.value(),
            page_count=self.page_count_spin.value(),
            refresh_count=self.refresh_count_spin.value(),
            headless=self.headless_checkbox.isChecked(),
        )
        self._total_tasks = config.total_tasks
        self.log_text.clear()
        self._append_log("开始创建刷新任务")
        self._set_progress(0, self._total_tasks)
        self._set_status("准备中")
        self._set_running_state(True)

        self.worker = RefreshWorker(config)
        self.worker.log_signal.connect(self._append_log)
        self.worker.progress_signal.connect(self._set_progress)
        self.worker.status_signal.connect(self._set_status)
        self.worker.completed_signal.connect(self._worker_completed)
        self.worker.start()

    def _stop_clicked(self) -> None:
        if self.worker is None:
            return
        self._append_log("正在停止任务并关闭浏览器...")
        self._set_status("已停止")
        self.stop_button.setEnabled(False)
        self.worker.stop()

    def _auto_update_enabled(self) -> bool:
        return bool(self.settings.value("updates/auto_check", True, type=bool))

    def _save_auto_update_enabled(self, enabled: bool) -> None:
        self.settings.setValue("updates/auto_check", enabled)

    def _maybe_auto_check_updates(self) -> None:
        if self.auto_update_checkbox.isChecked():
            self._check_for_updates(manual=False)

    def _check_for_updates(self, manual: bool = True) -> None:
        if self.update_worker is not None and self.update_worker.isRunning():
            if manual:
                QMessageBox.information(self, "检查更新", "正在检查更新，请稍候。")
            return

        self._update_check_is_manual = manual
        if manual:
            self._append_log("正在检查更新...")

        self.update_button.setEnabled(False)
        self.update_button.setText("检查中...")
        self.update_worker = UpdateCheckerWorker(parent=self)
        self.update_worker.result_signal.connect(self._update_check_finished)
        self.update_worker.error_signal.connect(self._update_check_failed)
        self.update_worker.finished.connect(self._cleanup_update_worker)
        self.update_worker.start()

    def _update_check_finished(self, result: UpdateCheckResult) -> None:
        self._append_log(result.message)
        if not result.update_available:
            if self._update_check_is_manual:
                QMessageBox.information(self, "检查更新", result.message)
            return

        target_url = result.download_url or result.release_url or RELEASES_URL
        message = (
            f"发现新版本 v{result.latest_version}。\n"
            f"当前版本 v{result.current_version}。\n\n"
            "是否打开下载页面？"
        )
        choice = QMessageBox.question(
            self,
            "发现新版本",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if choice == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl(target_url))

    def _update_check_failed(self, message: str) -> None:
        full_message = f"检查更新失败：{message}"
        self._append_log(full_message)
        if self._update_check_is_manual:
            QMessageBox.warning(self, "检查更新失败", full_message)

    def _cleanup_update_worker(self) -> None:
        self.update_button.setEnabled(True)
        self.update_button.setText("检查更新")
        if self.update_worker is not None:
            self.update_worker.deleteLater()
            self.update_worker = None

    def _worker_completed(self, status: str) -> None:
        self._set_status(status)
        self._set_running_state(False)
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None

    def _set_running_state(self, running: bool) -> None:
        for widget in (
            self.url_input,
            self.interval_spin,
            self.page_count_spin,
            self.refresh_count_spin,
            self.headless_checkbox,
            self.auth_checkbox,
        ):
            widget.setEnabled(not running)
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)

    def _set_progress(self, current: int, total: int) -> None:
        self._total_tasks = total
        self.progress_text.setText(f"当前进度：{current} / {total}")
        percent = int((current / total) * 100) if total else 0
        self.progress_bar.setValue(max(0, min(100, percent)))

    def _set_status(self, status: str) -> None:
        self.status_label.setText(f"状态：{status}")
        colors = {
            "准备中": ("#e7edf5", "#31445f"),
            "运行中": ("#dff5ec", "#116149"),
            "已完成": ("#dcfce7", "#166534"),
            "已停止": ("#fff1d6", "#8a4b10"),
            "发生错误": ("#fee2e2", "#991b1b"),
        }
        background, color = colors.get(status, ("#e7edf5", "#31445f"))
        self.status_label.setStyleSheet(
            f"background: {background}; color: {color};"
        )

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(5000)
        if self.update_worker is not None and self.update_worker.isRunning():
            self.update_worker.wait(10000)
        event.accept()
