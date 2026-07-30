"""Finger SDK Tool UI for Autodesk Maya."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import maya.OpenMayaUI as omui
import maya.cmds as cmds

try:
    from PySide6 import QtCore, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtCore, QtWidgets
    from shiboken2 import wrapInstance


TOOL_ROOT = Path(__file__).resolve().parent
TEMPLATE_DIR = TOOL_ROOT / "templates"
WINDOW_OBJECT = "FingerSDKTool_Window"

if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

import builder
from core import PoseValidationError, load_pose


def maya_main_window():
    pointer = omui.MQtUtil.mainWindow()
    return wrapInstance(int(pointer), QtWidgets.QWidget) if pointer else None


class FingerSDKTool(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent or maya_main_window())
        self.setObjectName(WINDOW_OBJECT)
        self.setWindowTitle("Finger SDK Tool")
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.resize(820, 600)
        self._poses = {}
        self._build_ui()
        self.refresh_library()

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("FINGER SDK TOOL")
        title.setObjectName("title")
        root.addWidget(title)
        root.addWidget(
            QtWidgets.QLabel(
                "ポーズを選択し、左右のフィンガーコントローラーへSDKを構築します。"
            )
        )

        content = QtWidgets.QHBoxLayout()
        root.addLayout(content, 1)

        library_group = QtWidgets.QGroupBox("POSE LIBRARY")
        library_layout = QtWidgets.QVBoxLayout(library_group)
        self.pose_list = QtWidgets.QListWidget()
        self.pose_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        library_layout.addWidget(self.pose_list)
        self.refresh_button = QtWidgets.QPushButton("ライブラリを更新")
        library_layout.addWidget(self.refresh_button)
        content.addWidget(library_group, 1)

        detail_group = QtWidgets.QGroupBox("SELECTION")
        detail_layout = QtWidgets.QVBoxLayout(detail_group)
        self.info = QtWidgets.QPlainTextEdit()
        self.info.setReadOnly(True)
        detail_layout.addWidget(self.info)
        self.build_button = QtWidgets.QPushButton("BUILD SDK")
        self.build_button.setObjectName("primary")
        self.build_button.setMinimumHeight(44)
        detail_layout.addWidget(self.build_button)
        content.addWidget(detail_group, 1)

        log_group = QtWidgets.QGroupBox("BUILD LOG")
        log_layout = QtWidgets.QVBoxLayout(log_group)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(200)
        self.log.setFixedHeight(130)
        log_layout.addWidget(self.log)
        root.addWidget(log_group)

        self.refresh_button.clicked.connect(self.refresh_library)
        self.pose_list.itemSelectionChanged.connect(self.update_selection_info)
        self.build_button.clicked.connect(self.build_selected)
        self.setStyleSheet(
            """
            QDialog { background:#20242a; color:#e9edf2;
                      font-family:'Segoe UI','Yu Gothic UI'; }
            QLabel#title { font-size:20px; font-weight:700; color:#8dd8ff; }
            QGroupBox { border:1px solid #3d4650; border-radius:6px;
                        margin-top:10px; padding-top:10px; font-weight:600; }
            QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 5px; }
            QListWidget, QPlainTextEdit { background:#171a1f; border:1px solid #39414a;
                                         border-radius:4px; padding:6px; }
            QListWidget::item { height:30px; }
            QListWidget::item:selected { background:#22658a; }
            QPushButton { background:#343b44; border:1px solid #4b5662;
                          border-radius:4px; padding:8px 12px; font-weight:600; }
            QPushButton:hover { background:#414b56; }
            QPushButton#primary { background:#1677a8; border-color:#2498cf; }
            QPushButton#primary:hover { background:#1988bf; }
            QPushButton:disabled { color:#6f7780; background:#292e34; }
            """
        )

    def selected_poses(self):
        return [
            self._poses[item.data(QtCore.Qt.UserRole)]
            for item in self.pose_list.selectedItems()
            if item.data(QtCore.Qt.UserRole) in self._poses
        ]

    def refresh_library(self):
        selected = {
            item.data(QtCore.Qt.UserRole) for item in self.pose_list.selectedItems()
        }
        self.pose_list.clear()
        self._poses.clear()
        errors = []
        for path in sorted(TEMPLATE_DIR.glob("*.json")):
            try:
                pose = load_pose(path)
                self._poses[path.name] = pose
                item = QtWidgets.QListWidgetItem(pose.name)
                item.setData(QtCore.Qt.UserRole, path.name)
                item.setToolTip(path.name)
                self.pose_list.addItem(item)
                item.setSelected(path.name in selected)
            except PoseValidationError as exc:
                errors.append(str(exc))
        self.log.setPlainText(
            "{} poses loaded{}".format(
                len(self._poses), "\n" + "\n".join(errors) if errors else ""
            )
        )
        self.update_selection_info()

    def update_selection_info(self):
        poses = self.selected_poses()
        self.build_button.setEnabled(bool(poses))
        self.info.setPlainText(
            "\n\n".join(
                "{}\nAttribute: {}\nDriver value: {:g}\nJoints: {}".format(
                    pose.name, pose.driver_attr, pose.driver_value, len(pose.joints)
                )
                for pose in poses
            )
        )

    def build_selected(self):
        poses = self.selected_poses()
        if not poses:
            return
        answer = QtWidgets.QMessageBox.question(
            self,
            "Build SDK",
            "{}ポーズを左右のリグに構築しますか？\n"
            "既存のツール管理SDKは置き換えられます。".format(len(poses)),
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return

        self.build_button.setEnabled(False)
        self.log.clear()
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        cmds.undoInfo(openChunk=True, chunkName="FingerSDKToolBuild")
        build_failed = False
        try:
            importlib.reload(builder)
            controllers = {
                side: builder.import_finger_controller(side) for side in ("L", "R")
            }
            for controller in controllers.values():
                builder.cleanup_unselected_template_attrs(controller, poses)
            results = []
            for pose in poses:
                for side in ("L", "R"):
                    count = builder.build_pose(pose, side, controllers[side])
                    line = "OK  {:<18} {}  {} joints".format(pose.name, side, count)
                    results.append(line)
                    self.log.appendPlainText(line)
                    QtWidgets.QApplication.processEvents()
            QtWidgets.QMessageBox.information(
                self, "Finger SDK Tool", "Build complete\n\n" + "\n".join(results)
            )
        except Exception as exc:
            build_failed = True
            self.log.appendPlainText("ERROR  {}".format(exc))
            QtWidgets.QMessageBox.critical(
                self, "Build failed", "{}\n\n変更をロールバックしました。".format(exc)
            )
        finally:
            cmds.undoInfo(closeChunk=True)
            if build_failed:
                cmds.undo()
            QtWidgets.QApplication.restoreOverrideCursor()
            self.build_button.setEnabled(bool(self.selected_poses()))


_ui = None


def show():
    global _ui
    if cmds.window(WINDOW_OBJECT, exists=True):
        cmds.deleteUI(WINDOW_OBJECT)
    _ui = FingerSDKTool()
    _ui.show()
    _ui.raise_()
    _ui.activateWindow()
    return _ui
