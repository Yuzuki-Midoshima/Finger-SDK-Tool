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


try:
    TOOL_ROOT = Path(__file__).resolve().parent
except NameError:
    # Maya shelf commands are evaluated from a string and have no __file__.
    TOOL_ROOT = (
        Path(cmds.internalVar(userAppDir=True))
        / "scripts"
        / "Finger-SDK-Tool"
    )
TEMPLATE_DIR = TOOL_ROOT / "templates"
WINDOW_OBJECT = "FingerSDKTool_Window"

if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

import builder
from core import PoseValidationError, load_pose


def maya_main_window():
    pointer = omui.MQtUtil.mainWindow()
    return wrapInstance(int(pointer), QtWidgets.QWidget) if pointer else None


class MissingJointsDialog(QtWidgets.QDialog):
    """Compact, resizable warning with scrollable joint details."""

    def __init__(self, parent, summary, details, allow_continue):
        super().__init__(parent)
        self.setWindowTitle("Missing Finger Joints")
        self.setModal(True)
        self.setSizeGripEnabled(True)
        self.setMinimumSize(360, 220)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSizeConstraint(QtWidgets.QLayout.SetMinimumSize)

        message_row = QtWidgets.QHBoxLayout()
        icon = QtWidgets.QLabel()
        icon.setPixmap(
            self.style().standardIcon(QtWidgets.QStyle.SP_MessageBoxWarning).pixmap(32, 32)
        )
        icon.setAlignment(QtCore.Qt.AlignTop)
        message = QtWidgets.QLabel(summary)
        message.setWordWrap(True)
        message_row.addWidget(icon)
        message_row.addWidget(message, 1)
        layout.addLayout(message_row)

        details_view = QtWidgets.QPlainTextEdit()
        details_view.setObjectName("missingJointsDetails")
        details_view.setPlainText(details)
        details_view.setReadOnly(True)
        details_view.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        details_view.setMinimumHeight(100)
        layout.addWidget(details_view, 1)

        if allow_continue:
            buttons = QtWidgets.QDialogButtonBox(
                QtWidgets.QDialogButtonBox.Yes | QtWidgets.QDialogButtonBox.Cancel
            )
            buttons.button(QtWidgets.QDialogButtonBox.Yes).setText("続行")
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
        else:
            buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
            buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        visible_lines = min(max(details.count("\n") + 1, 4), 14)
        line_height = details_view.fontMetrics().lineSpacing()
        self.resize(480, min(520, 150 + visible_lines * line_height))


class FingerMappingDialog(QtWidgets.QDialog):
    FINGERS = (
        ("thumb", "親指"),
        ("index", "人差し指"),
        ("middle", "中指"),
        ("ring", "薬指"),
        ("pinky", "小指"),
    )

    def __init__(
        self, mappings, inversions, thumb_modes, controller_rotation_offsets,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Finger Joint 対応")
        self.setWindowFlags(
            self.windowFlags()
            | QtCore.Qt.Window
            | QtCore.Qt.WindowMinimizeButtonHint
        )
        self.setModal(False)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.resize(620, 390)
        self._edits = {}
        self._inversion_checks = {}
        self._thumb_mode_combos = {}
        self._controller_rotation_spins = {}

        root = QtWidgets.QVBoxLayout(self)
        hint = QtWidgets.QLabel(
            "名前で判断できない指だけ設定してください。各指の一番親のJointを選択し、"
            "「選択から取得」を押します。子Jointは階層順に自動対応します。"
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        tabs = QtWidgets.QTabWidget()
        for side in ("L", "R"):
            page = QtWidgets.QWidget()
            grid = QtWidgets.QGridLayout(page)
            grid.setColumnStretch(1, 1)
            for row, (finger, label) in enumerate(self.FINGERS):
                edit = QtWidgets.QLineEdit(mappings.get(side, {}).get(finger, ""))
                edit.setPlaceholderText("未指定（名前から自動判定）")
                clear_button = QtWidgets.QToolButton()
                clear_button.setText("×")
                clear_button.setToolTip("手動対応を解除")
                select_button = QtWidgets.QPushButton("選択から取得")
                select_button.clicked.connect(
                    lambda _checked=False, target=edit, source_side=side,
                    source_finger=finger: self._capture_joint(
                        target, source_side, source_finger
                    )
                )
                clear_button.clicked.connect(edit.clear)
                grid.addWidget(QtWidgets.QLabel(label), row, 0)
                grid.addWidget(edit, row, 1)
                grid.addWidget(select_button, row, 2)
                grid.addWidget(clear_button, row, 3)
                self._edits[(side, finger)] = edit
            thumb_mode = QtWidgets.QComboBox()
            thumb_mode.addItem("自動判定", "auto")
            thumb_mode.addItem("掌Jointから（4段）", "palm")
            thumb_mode.addItem("第1関節から（3段）", "first")
            mode_index = thumb_mode.findData(thumb_modes.get(side, "auto"))
            thumb_mode.setCurrentIndex(max(mode_index, 0))
            grid.addWidget(QtWidgets.QLabel("親指ルート"), len(self.FINGERS), 0)
            grid.addWidget(thumb_mode, len(self.FINGERS), 1, 1, 3)
            self._thumb_mode_combos[side] = thumb_mode

            rotation_row = QtWidgets.QHBoxLayout()
            rotation_row.addWidget(QtWidgets.QLabel("コントローラー向き補正"))
            offsets = controller_rotation_offsets.get(side, (0.0, 0.0, 0.0))
            for index, axis in enumerate("XYZ"):
                rotation_row.addWidget(QtWidgets.QLabel(axis))
                spin = QtWidgets.QDoubleSpinBox()
                spin.setRange(-360.0, 360.0)
                spin.setDecimals(1)
                spin.setSingleStep(90.0)
                spin.setSuffix("°")
                spin.setValue(offsets[index])
                spin.setFixedWidth(78)
                rotation_row.addWidget(spin)
                self._controller_rotation_spins[(side, axis)] = spin
            rotation_row.addStretch(1)
            grid.addLayout(rotation_row, len(self.FINGERS) + 1, 0, 1, 4)

            invert_row = QtWidgets.QHBoxLayout()
            invert_row.addWidget(QtWidgets.QLabel("4指の回転値を反転:"))
            for axis in ("rotateX", "rotateY", "rotateZ"):
                check = QtWidgets.QCheckBox(axis[-1])
                check.setChecked(axis in inversions.get(side, set()))
                invert_row.addWidget(check)
                self._inversion_checks[(side, axis)] = check
            invert_row.addStretch(1)
            grid.addLayout(invert_row, len(self.FINGERS) + 2, 0, 1, 4)
            tabs.addTab(page, "左 (L)" if side == "L" else "右 (R)")
        root.addWidget(tabs, 1)

        self.match_status = QtWidgets.QLabel("")
        self.match_status.setWordWrap(True)
        root.addWidget(self.match_status)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _capture_joint(self, target, side, finger):
        selected = cmds.ls(selection=True, long=True, type="joint") or []
        if len(selected) != 1:
            QtWidgets.QMessageBox.warning(
                self, "Joint選択", "一番親になるJointを1つだけ選択してください。"
            )
            return
        target.setText(selected[0])
        opposite = "R" if side == "L" else "L"
        matched = builder.find_matching_finger_root(selected[0], opposite)
        if matched:
            self._edits[(opposite, finger)].setText(matched)
            label = dict(self.FINGERS)[finger]
            self.match_status.setText(
                "{}を取得し、反対側の{}も自動登録しました。{}タブで確認できます。".format(
                    label, label, "右" if opposite == "R" else "左"
                )
            )
            self.match_status.setStyleSheet("color:#7fd69a;")
        else:
            self.match_status.setText(
                "反対側の同形式Jointを特定できませんでした。反対側タブで手動登録してください。"
            )
            self.match_status.setStyleSheet("color:#e2b86b;")

    def mappings(self):
        result = {"L": {}, "R": {}}
        for (side, finger), edit in self._edits.items():
            value = edit.text().strip()
            if value:
                result[side][finger] = value
        return result

    def inversions(self):
        result = {"L": set(), "R": set()}
        for (side, axis), check in self._inversion_checks.items():
            if check.isChecked():
                result[side].add(axis)
        return result

    def thumb_modes(self):
        return {
            side: combo.currentData()
            for side, combo in self._thumb_mode_combos.items()
        }

    def controller_rotation_offsets(self):
        return {
            side: tuple(
                self._controller_rotation_spins[(side, axis)].value()
                for axis in "XYZ"
            )
            for side in ("L", "R")
        }


class FingerSDKTool(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent or maya_main_window())
        self.setObjectName(WINDOW_OBJECT)
        self.setWindowTitle("Finger SDK Tool")
        self.setWindowFlags(
            self.windowFlags()
            | QtCore.Qt.Window
            | QtCore.Qt.WindowMinimizeButtonHint
            | QtCore.Qt.WindowMaximizeButtonHint
        )
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.resize(820, 600)
        self._poses = {}
        self._pose_editor = None
        self._joint_mapping_dialog = None
        self._finger_roots = {"L": {}, "R": {}}
        self._rotation_inversions = {"L": set(), "R": set()}
        self._thumb_modes = {"L": "auto", "R": "auto"}
        self._controller_rotation_offsets = {
            "L": (0.0, 0.0, 0.0),
            "R": (0.0, 0.0, 0.0),
        }
        self._build_ui()
        self.refresh_library()

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QGridLayout()
        title = QtWidgets.QLabel("FINGER SDK TOOL")
        title.setObjectName("title")
        header.addWidget(title, 0, 0, 1, 4)
        self.joint_mapping_button = QtWidgets.QPushButton("Joint対応…")
        self.joint_mapping_button.setToolTip(
            "名前で判定できないFinger Jointを階層で対応付けます"
        )
        header.addWidget(self.joint_mapping_button, 0, 4)
        description = QtWidgets.QLabel(
            "ポーズを選択し、左右のフィンガーコントローラーへSDKを構築します。"
        )
        header.addWidget(description, 1, 0)
        header.addWidget(QtWidgets.QLabel("左"), 1, 1)
        self.left_controller_name = QtWidgets.QLineEdit("L_fingers_anim")
        self.left_controller_name.setFixedWidth(140)
        header.addWidget(self.left_controller_name, 1, 2)
        header.addWidget(QtWidgets.QLabel("右"), 1, 3)
        self.right_controller_name = QtWidgets.QLineEdit("R_fingers_anim")
        self.right_controller_name.setFixedWidth(140)
        header.addWidget(self.right_controller_name, 1, 4)
        header.setColumnStretch(0, 1)
        root.addLayout(header)

        content = QtWidgets.QHBoxLayout()
        root.addLayout(content, 1)

        library_group = QtWidgets.QGroupBox("POSE LIBRARY")
        library_layout = QtWidgets.QVBoxLayout(library_group)
        self.pose_list = QtWidgets.QListWidget()
        self.pose_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        library_layout.addWidget(self.pose_list)
        self.refresh_button = QtWidgets.QPushButton("ライブラリを更新")
        self.edit_library_button = QtWidgets.QPushButton("ポーズ登録・編集")
        library_buttons = QtWidgets.QHBoxLayout()
        library_buttons.setSpacing(6)
        library_buttons.addWidget(self.refresh_button)
        library_buttons.addWidget(self.edit_library_button)
        library_layout.addLayout(library_buttons)
        content.addWidget(library_group, 1)

        detail_group = QtWidgets.QGroupBox("SELECTION")
        detail_layout = QtWidgets.QVBoxLayout(detail_group)
        self.info = QtWidgets.QPlainTextEdit()
        self.info.setReadOnly(True)
        detail_layout.addWidget(self.info)

        self.hide_transforms = QtWidgets.QCheckBox(
            "移動・回転・スケールを非表示・ロック"
        )
        self.hide_transforms.setChecked(True)
        detail_layout.addWidget(self.hide_transforms)

        inversion_panel = QtWidgets.QFrame()
        inversion_panel.setObjectName("inversionPanel")
        inversion_row = QtWidgets.QHBoxLayout(inversion_panel)
        inversion_row.setContentsMargins(8, 4, 8, 4)
        inversion_row.setSpacing(7)
        inversion_row.addWidget(QtWidgets.QLabel("4指反転"))
        self.main_inversion_checks = {}
        for side in ("L", "R"):
            if side == "R":
                separator = QtWidgets.QFrame()
                separator.setFrameShape(QtWidgets.QFrame.VLine)
                separator.setFrameShadow(QtWidgets.QFrame.Sunken)
                inversion_row.addWidget(separator)
            inversion_row.addWidget(QtWidgets.QLabel("左" if side == "L" else "右"))
            for axis in ("rotateX", "rotateY", "rotateZ"):
                check = QtWidgets.QCheckBox(axis[-1])
                check.setToolTip("{}手の{}回転値を反転".format(side, axis[-1]))
                check.toggled.connect(
                    lambda checked, target_side=side, target_axis=axis:
                    self.set_rotation_inversion(target_side, target_axis, checked)
                )
                inversion_row.addWidget(check)
                self.main_inversion_checks[(side, axis)] = check
        inversion_row.addStretch(1)
        detail_layout.addWidget(inversion_panel)

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
        self.edit_library_button.clicked.connect(self.open_pose_editor)
        self.joint_mapping_button.clicked.connect(self.open_joint_mapping)
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
            QListWidget, QPlainTextEdit, QLineEdit {
                background:#171a1f; border:1px solid #39414a;
                border-radius:4px; padding:6px; }
            QListWidget::item { height:30px; }
            QListWidget::item:selected { background:#22658a; }
            QPushButton { background:#343b44; border:1px solid #4b5662;
                          border-radius:4px; padding:8px 12px; font-weight:600; }
            QPushButton:hover { background:#414b56; }
            QPushButton#primary { background:#1677a8; border-color:#2498cf;
                                  color:#ffffff; }
            QPushButton#primary:hover { background:#1988bf; }
            QPushButton:disabled { color:#6f7780; background:#292e34; }
            QPushButton#primary:disabled { color:#d8e3e9; background:#31566a;
                                           border-color:#416f86; }
            QFrame#inversionPanel { background:#292e34; border-radius:4px; }
            """
        )

    def open_pose_editor(self):
        try:
            if self._pose_editor is None:
                # Keep the optional editor out of the main startup path. This also
                # refreshes editor changes in long-running Maya sessions.
                core_module = importlib.import_module("core")
                importlib.reload(core_module)
                editor_module = importlib.import_module("pose_editor")
                editor_module = importlib.reload(editor_module)
                # Parent both tool windows to Maya instead of nesting the editor
                # under this dialog, so each can be minimized independently.
                self._pose_editor = editor_module.PoseEditorDialog(
                    TEMPLATE_DIR, maya_main_window()
                )
                self._pose_editor.library_changed.connect(
                    lambda _name: self.refresh_library()
                )
            self._pose_editor.show()
            self._pose_editor.raise_()
            self._pose_editor.activateWindow()
        except Exception as exc:
            self.log.appendPlainText("POSE EDITOR ERROR  {}".format(exc))
            QtWidgets.QMessageBox.critical(self, "Pose editor failed", str(exc))

    def open_joint_mapping(self):
        if self._joint_mapping_dialog is None:
            core_module = importlib.import_module("core")
            importlib.reload(core_module)
            importlib.reload(builder)
            dialog = FingerMappingDialog(
                self._finger_roots,
                self._rotation_inversions,
                self._thumb_modes,
                self._controller_rotation_offsets,
                maya_main_window(),
            )
            dialog.accepted.connect(lambda: self.apply_joint_mapping(dialog))
            dialog.destroyed.connect(self.clear_joint_mapping_dialog)
            self._joint_mapping_dialog = dialog
        self._joint_mapping_dialog.show()
        self._joint_mapping_dialog.raise_()
        self._joint_mapping_dialog.activateWindow()

    def apply_joint_mapping(self, dialog):
        self._finger_roots = dialog.mappings()
        core_module = importlib.import_module("core")
        importlib.reload(core_module)
        importlib.reload(builder)
        for source_side, target_side in (("L", "R"), ("R", "L")):
            for finger, root in list(self._finger_roots[source_side].items()):
                if finger in self._finger_roots[target_side]:
                    continue
                matched = builder.find_matching_finger_root(root, target_side)
                if matched:
                    self._finger_roots[target_side][finger] = matched
        self._rotation_inversions = dialog.inversions()
        self._thumb_modes = dialog.thumb_modes()
        self._controller_rotation_offsets = dialog.controller_rotation_offsets()
        self.sync_rotation_inversion_controls()
        count = sum(len(items) for items in self._finger_roots.values())
        self.joint_mapping_button.setText(
            "Joint対応… ({})".format(count) if count else "Joint対応…"
        )

    def clear_joint_mapping_dialog(self, *_args):
        self._joint_mapping_dialog = None

    def set_rotation_inversion(self, side, axis, checked):
        axes = self._rotation_inversions[side]
        if checked:
            axes.add(axis)
        else:
            axes.discard(axis)
        dialog = self._joint_mapping_dialog
        if dialog is not None:
            mirror = dialog._inversion_checks.get((side, axis))
            if mirror is not None and mirror.isChecked() != checked:
                mirror.setChecked(checked)

    def sync_rotation_inversion_controls(self):
        for (side, axis), check in self.main_inversion_checks.items():
            checked = axis in self._rotation_inversions[side]
            check.blockSignals(True)
            check.setChecked(checked)
            check.blockSignals(False)

    def mapped_wrist(self, side):
        """Use a mapped finger root's parent as the controller anchor."""
        for finger, _label in FingerMappingDialog.FINGERS:
            joint = self._finger_roots.get(side, {}).get(finger)
            if joint and cmds.objExists(joint):
                parents = cmds.listRelatives(joint, parent=True, fullPath=True) or []
                if parents:
                    return parents[0]
        return None

    def thumb_mode_for_side(self, side):
        """Only use structural thumb modes after a thumb root was captured."""
        if not self._finger_roots.get(side, {}).get("thumb"):
            return "auto"
        return self._thumb_modes.get(side, "auto")

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
                "{}\nAttribute: {} ({})\nRange: {:g} to {:g}\nJoints: {}".format(
                    pose.name, pose.driver_attr, pose.driver_type,
                    pose.driver_min, pose.driver_value, len(pose.joints)
                )
                for pose in poses
            )
        )

    def confirm_missing_joints(self, poses):
        missing_groups = []
        empty_groups = []
        for pose in poses:
            for side in ("L", "R"):
                targets, missing = builder.resolve_pose_targets(
                    pose,
                    side,
                    self._finger_roots.get(side),
                    self.thumb_mode_for_side(side),
                )
                if not targets:
                    empty_groups.append((pose.name, side, missing))
                elif missing:
                    missing_groups.append((pose.name, side, missing))

        if empty_groups:
            details = []
            for pose_name, side, missing in empty_groups:
                details.append("{} ({})".format(pose_name, side))
                details.extend("- {}".format(joint) for joint in missing)
            MissingJointsDialog(
                self,
                "対象となるFinger JointがScene上に見つかりません。",
                "\n".join(details),
                allow_continue=False,
            ).exec_()
            return False

        if not missing_groups:
            return True

        details = []
        for pose_name, side, missing in missing_groups:
            details.append("{} ({})".format(pose_name, side))
            details.extend("- {}".format(joint) for joint in missing)
            details.append("")
        dialog = MissingJointsDialog(
            self,
            "一部のFinger Jointが見つかりません。\n"
            "存在するJointのみを対象にSDKを構築します。",
            "見つからないJoint:\n{}".format("\n".join(details).rstrip()),
            allow_continue=True,
        )
        return dialog.exec_() == QtWidgets.QDialog.Accepted

    def build_selected(self):
        # The mapping window is modeless so the main tool remains movable and
        # usable. Pull its current values before every build, even if OK has not
        # been pressed yet.
        if self._joint_mapping_dialog is not None:
            self.apply_joint_mapping(self._joint_mapping_dialog)
        poses = self.selected_poses()
        if not poses:
            return
        controller_names = {
            "L": self.left_controller_name.text().strip(),
            "R": self.right_controller_name.text().strip(),
        }
        if not all(controller_names.values()):
            QtWidgets.QMessageBox.warning(
                self, "Controller name", "左右のコントローラー名を入力してください"
            )
            return
        if controller_names["L"] == controller_names["R"]:
            QtWidgets.QMessageBox.warning(
                self, "Controller name", "左右には異なる名前を指定してください"
            )
            return
        answer = QtWidgets.QMessageBox.question(
            self,
            "Build SDK",
            "{}ポーズを左右のリグに構築しますか？\n"
            "選択したPoseに関連する既存SDKを整理して再構築します。".format(
                len(poses)
            ),
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return

        try:
            # Maya keeps imported modules alive between tool launches. Reload the
            # dependency first so builder never imports symbols from stale core.
            core_module = importlib.import_module("core")
            importlib.reload(core_module)
            importlib.reload(builder)
            for side in ("L", "R"):
                builder.validate_controller_target(
                    side, controller_names[side], self.mapped_wrist(side)
                )
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Build failed", str(exc))
            return

        if not self.confirm_missing_joints(poses):
            return

        new_controller_names = {
            name for name in controller_names.values() if not cmds.objExists(name)
        }
        self.build_button.setEnabled(False)
        self.log.clear()
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        results = []
        build_error = None
        chunk_open = False
        try:
            cmds.undoInfo(openChunk=True, chunkName="FingerSDKToolBuild")
            chunk_open = True
            controllers = {
                side: builder.import_finger_controller(
                    side,
                    controller_names[side],
                    self.mapped_wrist(side),
                    self._controller_rotation_offsets.get(side),
                )
                for side in ("L", "R")
            }
            for controller in controllers.values():
                builder.set_transform_channels_hidden(
                    controller, self.hide_transforms.isChecked()
                )
            for side in ("L", "R"):
                disconnected = builder.prepare_pose_rebuild(
                    poses,
                    side,
                    controllers[side],
                    self._finger_roots.get(side),
                    self.thumb_mode_for_side(side),
                )
                if disconnected:
                    line = "CLEANUP  {}  {} residual rotate inputs".format(
                        side, len(disconnected)
                    )
                    results.append(line)
                    self.log.appendPlainText(line)
            for pose in poses:
                for side in ("L", "R"):
                    count = builder.build_pose(
                        pose,
                        side,
                        controllers[side],
                        self._finger_roots.get(side),
                        self._rotation_inversions.get(side),
                        self.thumb_mode_for_side(side),
                        cleanup_existing=False,
                    )
                    line = "OK  {:<18} {}  {} joints".format(pose.name, side, count)
                    results.append(line)
                    self.log.appendPlainText(line)
                    QtWidgets.QApplication.processEvents()
        except Exception as exc:
            build_error = exc
        finally:
            if chunk_open:
                cmds.undoInfo(closeChunk=True)
            if (
                build_error is not None
                and not cmds.undoInfo(query=True, undoQueueEmpty=True)
                and cmds.undoInfo(query=True, undoName=True) == "FingerSDKToolBuild"
            ):
                cmds.undo()
            if build_error is not None:
                leftovers = [
                    name for name in new_controller_names if cmds.objExists(name)
                ]
                if leftovers:
                    undo_enabled = cmds.undoInfo(query=True, state=True)
                    try:
                        cmds.undoInfo(stateWithoutFlush=False)
                        cmds.delete(leftovers)
                    finally:
                        cmds.undoInfo(stateWithoutFlush=undo_enabled)
            QtWidgets.QApplication.restoreOverrideCursor()
            self.build_button.setEnabled(bool(self.selected_poses()))

        if build_error is not None:
            self.log.appendPlainText("ERROR  {}".format(build_error))
            QtWidgets.QMessageBox.critical(
                self,
                "Build failed",
                "{}\n\n変更をロールバックしました。".format(build_error),
            )
            return

        QtWidgets.QMessageBox.information(
            self, "Finger SDK Tool", "Build complete\n\n" + "\n".join(results)
        )


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
