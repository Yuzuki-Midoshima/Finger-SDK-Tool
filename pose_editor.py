"""Pose JSON registration and editing UI for Maya."""

import re
from pathlib import Path

import maya.cmds as cmds

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtWidgets

from core import (
    PoseValidationError,
    canonical_pose_joint_key,
    joint_name_match_score,
    load_pose,
    resolve_scene_joint,
    save_pose_data,
    validate_file_stem,
)

AXES = ("rotateX", "rotateY", "rotateZ")
Signal = QtCore.Signal if hasattr(QtCore, "Signal") else QtCore.pyqtSignal


def portable_joint_name(name, side):
    """Remove DAG/namespace paths and the captured side prefix."""
    return canonical_pose_joint_key(name, side)


class PoseForm(QtWidgets.QWidget):
    saved = Signal(str)
    deleted = Signal(str)

    def __init__(self, template_dir, edit_mode=False, parent=None):
        super().__init__(parent)
        self.template_dir = Path(template_dir)
        self.edit_mode = edit_mode
        self._build_ui()
        if edit_mode:
            self.reload_files()

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        if self.edit_mode:
            self.file_combo = QtWidgets.QComboBox()
            self.file_combo.currentIndexChanged.connect(self.load_current)
            form.addRow("編集するJSON", self.file_combo)
        self.file_name = QtWidgets.QLineEdit()
        self.file_name.setPlaceholderText("例: fist.json（半角英数字・_・-）")
        self.file_name.setToolTip(
            "Poseデータを保存するJSONファイルの名前です。拡張子は入力不要です。"
        )
        self.file_name.textEdited.connect(self.ensure_json_extension)
        self.pose_name = QtWidgets.QLineEdit()
        self.pose_name.setPlaceholderText("例: 握り（日本語OK／Pose一覧に表示）")
        self.pose_name.setToolTip(
            "Pose Libraryに表示する、読みやすいポーズ名です。"
        )
        self.driver_attr = QtWidgets.QLineEdit()
        self.driver_attr.setPlaceholderText(
            "例: fist（半角英数字・_／Maya Channel Boxに表示）"
        )
        self.driver_attr.setToolTip(
            "Finger ControllerのChannel Boxに作成する操作Attribute名です。"
        )
        self.driver_type = QtWidgets.QComboBox()
        self.driver_type.addItem("数値（最小／最大）", "number")
        self.driver_type.addItem("2択（名前指定）", "enum")
        self.driver_min = QtWidgets.QDoubleSpinBox()
        self.driver_min.setRange(-1000000.0, 0.0)
        self.driver_min.setDecimals(3)
        self.driver_max = QtWidgets.QDoubleSpinBox()
        self.driver_max.setRange(0.001, 1000000.0)
        self.driver_max.setDecimals(3)
        self.driver_max.setValue(10.0)
        self.driver_off_name = QtWidgets.QLineEdit("OFF")
        self.driver_on_name = QtWidgets.QLineEdit("ON")
        self.driver_type.currentIndexChanged.connect(self.update_driver_fields)
        self.side = QtWidgets.QComboBox()
        self.side.addItems(("L", "R"))
        form.addRow("保存ファイル名", self.file_name)
        form.addRow("Pose一覧の表示名", self.pose_name)
        form.addRow("Channel Boxの属性名", self.driver_attr)
        form.addRow("Attribute Type", self.driver_type)
        form.addRow("最小値", self.driver_min)
        form.addRow("最大値", self.driver_max)
        form.addRow("状態 0 の名前", self.driver_off_name)
        form.addRow("状態 1 の名前", self.driver_on_name)
        form.addRow("取込サイド", self.side)
        root.addLayout(form)
        self.update_driver_fields()

        hint = QtWidgets.QLabel(
            "Mayaで指ジョイントを選択して取り込んでください。"
            "1本だけの更新、またはルート以下の一括取込ができます。"
            "既存行は対応スロットの値で更新されます。"
        )
        hint.setWordWrap(True)
        root.addWidget(hint)
        self.include_terminal_joints = QtWidgets.QCheckBox(
            "end / tip Jointも取り込む"
        )
        self.include_terminal_joints.setChecked(True)
        root.addWidget(self.include_terminal_joints)
        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(("Joint",) + AXES)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        root.addWidget(self.table, 1)

        actions = QtWidgets.QHBoxLayout()
        actions.setSpacing(10)

        capture_group = QtWidgets.QGroupBox("Mayaから取り込む")
        capture_buttons = QtWidgets.QHBoxLayout(capture_group)
        capture_buttons.setContentsMargins(8, 8, 8, 8)
        capture = QtWidgets.QPushButton("選択Joint")
        capture.setToolTip("Mayaで選択中のJointを表へ追加・更新します")
        capture_hierarchy = QtWidgets.QPushButton("ルート階層")
        capture_hierarchy.setToolTip(
            "選択したRoot Jointと、その下のFinger Jointをまとめて取り込みます"
        )
        capture_buttons.addWidget(capture)
        capture_buttons.addWidget(capture_hierarchy)

        edit_group = QtWidgets.QGroupBox("表のデータを編集")
        edit_buttons = QtWidgets.QHBoxLayout(edit_group)
        edit_buttons.setContentsMargins(8, 8, 8, 8)
        update_selected = QtWidgets.QPushButton("選択行を再取得")
        update_selected.setToolTip("選択した行を現在のMaya Sceneの値で更新します")
        update_all = QtWidgets.QPushButton("全行を再取得")
        update_all.setToolTip("すべての行を現在のMaya Sceneの値で更新します")
        remove = QtWidgets.QPushButton("行を削除")
        remove.setToolTip("表で選択した行をPose Dataから取り除きます")
        edit_buttons.addWidget(update_selected)
        edit_buttons.addWidget(update_all)
        edit_buttons.addWidget(remove)

        save = QtWidgets.QPushButton("上書き保存" if self.edit_mode else "新規登録")
        save.setObjectName("primary")
        save.setMinimumSize(110, 44)
        save.setToolTip(
            "編集内容をJSONへ上書きします"
            if self.edit_mode else "入力内容を新しいPose JSONとして登録します"
        )
        capture.clicked.connect(self.capture_selection)
        capture_hierarchy.clicked.connect(self.capture_root_hierarchy)
        update_selected.clicked.connect(self.update_selected_rows)
        update_all.clicked.connect(self.update_all_rows)
        remove.clicked.connect(self.remove_rows)
        save.clicked.connect(self.save)
        actions.addWidget(capture_group)
        actions.addWidget(edit_group, 1)
        if self.edit_mode:
            delete_preset = QtWidgets.QPushButton("プリセット削除")
            delete_preset.setMinimumHeight(44)
            delete_preset.setToolTip("現在選択しているPose JSONを削除します")
            delete_preset.clicked.connect(self.delete_current)
            actions.addWidget(delete_preset)
        actions.addWidget(save)
        root.addLayout(actions)

    def ensure_json_extension(self, text):
        """Keep the generated extension visible inside the filename field."""
        stem = text.strip()
        if stem.lower().endswith(".json"):
            stem = stem[:-5]
        value = stem + ".json" if stem else ""
        self.file_name.blockSignals(True)
        self.file_name.setText(value)
        self.file_name.setCursorPosition(len(stem))
        self.file_name.blockSignals(False)

    def reload_files(self, selected=None):
        self.file_combo.blockSignals(True)
        self.file_combo.clear()
        for path in sorted(self.template_dir.glob("*.json")):
            self.file_combo.addItem(path.name, str(path))
        if selected:
            index = self.file_combo.findText(selected)
            if index >= 0:
                self.file_combo.setCurrentIndex(index)
        self.file_combo.blockSignals(False)
        self.load_current()

    def load_current(self):
        if self.file_combo.currentIndex() < 0:
            self.file_name.clear()
            self.pose_name.clear()
            self.driver_attr.clear()
            self.table.setRowCount(0)
            return
        try:
            path = Path(self.file_combo.currentData())
            pose = load_pose(path)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "JSON読込エラー", str(exc))
            return
        self.file_name.setText(path.name)
        self.file_name.setReadOnly(True)
        self.pose_name.setText(pose.name)
        self.driver_attr.setText(pose.driver_attr)
        type_index = self.driver_type.findData(pose.driver_type)
        self.driver_type.setCurrentIndex(max(type_index, 0))
        self.driver_min.setValue(pose.driver_min)
        self.driver_max.setValue(pose.driver_value)
        self.driver_off_name.setText(pose.driver_off_name)
        self.driver_on_name.setText(pose.driver_on_name)
        self.table.setRowCount(0)
        for joint, values in pose.joints.items():
            self.set_joint_row(joint, values)

    def set_joint_row(self, joint, values):
        row = self.table.rowCount()
        for index in range(row):
            if self.table.item(index, 0).text() == joint:
                row = index
                break
        if row == self.table.rowCount():
            self.table.insertRow(row)
        self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(joint))
        for column, axis in enumerate(AXES, 1):
            value = values.get(axis, 0.0)
            self.table.setItem(row, column, QtWidgets.QTableWidgetItem("{:g}".format(value)))

    def update_driver_fields(self):
        is_number = self.driver_type.currentData() == "number"
        self.driver_min.setEnabled(is_number)
        self.driver_max.setEnabled(is_number)
        self.driver_off_name.setEnabled(not is_number)
        self.driver_on_name.setEnabled(not is_number)
        if not is_number:
            self.driver_min.setValue(0.0)
            self.driver_max.setValue(1.0)

    def capture_selection(self):
        selected = cmds.ls(selection=True, long=True, type="joint") or []
        if not selected:
            QtWidgets.QMessageBox.warning(self, "ジョイント取込", "指ジョイントを選択してください。")
            return
        side = self.side.currentText()
        for joint in selected:
            values = {axis: cmds.getAttr("{}.{}".format(joint, axis)) for axis in AXES}
            self.set_joint_row(portable_joint_name(joint, side), values)

    def capture_root_hierarchy(self):
        selected = cmds.ls(selection=True, long=True, type="joint") or []
        if len(selected) != 1:
            QtWidgets.QMessageBox.warning(
                self, "ルート取込", "ルートJointを1つだけ選択してください。"
            )
            return
        root_joint = selected[0]
        descendants = cmds.listRelatives(
            root_joint, allDescendents=True, type="joint", fullPath=True
        ) or []
        joints = [root_joint] + sorted(
            descendants, key=lambda joint: (joint.count("|"), joint.lower())
        )
        side = self.side.currentText()
        captured = 0
        for joint in joints:
            leaf = joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            leaf_words = re.findall(r"[A-Za-z]+|\d+", leaf.lower())
            is_terminal = any(word in ("end", "tip") for word in leaf_words)
            include_terminal = self.include_terminal_joints.isChecked()
            if is_terminal and not include_terminal:
                continue
            key = portable_joint_name(joint, side)
            is_pose_slot = re.match(
                r"^(?:thumb_palm|thumb\d+|index\d+|middle\d+|ring\d+|pinky\d+)_jnt$",
                key,
            )
            is_finger_terminal = is_terminal and any(
                finger in key.lower()
                for finger in ("thumb", "index", "middle", "ring", "pinky")
            )
            if not is_pose_slot and not (include_terminal and is_finger_terminal):
                continue
            values = {
                axis: cmds.getAttr("{}.{}".format(joint, axis)) for axis in AXES
            }
            self.set_joint_row(key, values)
            captured += 1
        if not captured:
            QtWidgets.QMessageBox.warning(
                self, "ルート取込", "取り込めるJointが見つかりませんでした。"
            )

    def resolve_table_joint(self, key):
        side = self.side.currentText()
        exact = resolve_scene_joint(key, side)
        if exact and cmds.objExists(exact):
            return exact
        candidates = []
        for joint in cmds.ls(type="joint", long=True) or []:
            score = joint_name_match_score(key, joint, side)
            if score:
                candidates.append((score, joint))
        if not candidates:
            return None
        best_score = max(score for score, _joint in candidates)
        best = [joint for score, joint in candidates if score == best_score]
        return best[0] if len(best) == 1 else None

    def update_rows_from_scene(self, rows):
        unresolved = []
        updated = 0
        for row in sorted(set(rows)):
            item = self.table.item(row, 0)
            key = item.text().strip() if item else ""
            joint = self.resolve_table_joint(key) if key else None
            if not joint:
                unresolved.append(key or "行 {}".format(row + 1))
                continue
            for column, axis in enumerate(AXES, 1):
                value = cmds.getAttr("{}.{}".format(joint, axis))
                self.table.setItem(
                    row, column, QtWidgets.QTableWidgetItem("{:g}".format(value))
                )
            updated += 1
        if unresolved:
            QtWidgets.QMessageBox.warning(
                self,
                "Joint更新",
                "対応Jointを特定できませんでした:\n{}".format(
                    "\n".join("- " + key for key in unresolved)
                ),
            )
        return updated

    def update_selected_rows(self):
        rows = [index.row() for index in self.table.selectionModel().selectedRows()]
        if not rows:
            QtWidgets.QMessageBox.warning(
                self, "Joint更新", "更新する行を表から選択してください。"
            )
            return
        self.update_rows_from_scene(rows)

    def update_all_rows(self):
        self.update_rows_from_scene(range(self.table.rowCount()))

    def remove_rows(self):
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        for row in sorted(rows, reverse=True):
            self.table.removeRow(row)

    def pose_data(self):
        joints = {}
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            joint = item.text().strip() if item else ""
            if not joint:
                raise PoseValidationError("joint name cannot be empty")
            rotations = {}
            for column, axis in enumerate(AXES, 1):
                item = self.table.item(row, column)
                try:
                    rotations[axis] = float(item.text())
                except (AttributeError, ValueError):
                    raise PoseValidationError("{}.{} must be numeric".format(joint, axis))
            joints[joint] = rotations
        driver_type = self.driver_type.currentData()
        return {"pose_name": self.pose_name.text().strip(),
                "driver_attr": self.driver_attr.text().strip(),
                "driver_type": driver_type,
                "driver_min": 0 if driver_type == "enum" else self.driver_min.value(),
                "driver_value": 1 if driver_type == "enum" else self.driver_max.value(),
                "driver_off_name": self.driver_off_name.text().strip(),
                "driver_on_name": self.driver_on_name.text().strip(),
                "joints": joints}

    def save(self):
        try:
            file_name = self.file_name.text().strip()
            stem = file_name[:-5] if file_name.lower().endswith(".json") else file_name
            stem = validate_file_stem(stem)
            target = self.template_dir / (stem + ".json")
            overwrite = self.edit_mode
            if not overwrite and target.exists():
                answer = QtWidgets.QMessageBox.question(
                    self, "上書き確認", "{} は既に存在します。上書きしますか？".format(target.name),
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel,
                    QtWidgets.QMessageBox.Cancel)
                if answer != QtWidgets.QMessageBox.Yes:
                    return
                overwrite = True
            save_pose_data(target, self.pose_data(), overwrite=overwrite)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "保存エラー", str(exc))
            return
        QtWidgets.QMessageBox.information(self, "Pose JSON", "{} を保存しました。".format(target.name))
        self.saved.emit(target.name)

    def delete_current(self):
        """Delete the JSON selected in the existing-preset editor."""
        if not self.edit_mode or self.file_combo.currentIndex() < 0:
            return
        path = Path(self.file_combo.currentData()).resolve()
        template_dir = self.template_dir.resolve()
        if path.parent != template_dir or path.suffix.lower() != ".json":
            QtWidgets.QMessageBox.critical(
                self, "削除エラー", "templates内のPose JSONだけを削除できます。"
            )
            return
        answer = QtWidgets.QMessageBox.warning(
            self,
            "プリセット削除",
            "{} を削除しますか？\nこの操作は元に戻せません。".format(path.name),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel,
            QtWidgets.QMessageBox.Cancel,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        try:
            path.unlink()
        except OSError as exc:
            QtWidgets.QMessageBox.critical(self, "削除エラー", str(exc))
            return
        deleted_name = path.name
        self.reload_files()
        self.deleted.emit(deleted_name)


class PoseEditorDialog(QtWidgets.QDialog):
    library_changed = Signal(str)

    def __init__(self, template_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pose JSON 登録・編集")
        self.setWindowFlags(
            self.windowFlags()
            | QtCore.Qt.Window
            | QtCore.Qt.WindowMinimizeButtonHint
            | QtCore.Qt.WindowMaximizeButtonHint
        )
        self.resize(720, 560)
        layout = QtWidgets.QVBoxLayout(self)
        tabs = QtWidgets.QTabWidget()
        self.new_form = PoseForm(template_dir, False, self)
        self.edit_form = PoseForm(template_dir, True, self)
        tabs.addTab(self.new_form, "新規登録")
        tabs.addTab(self.edit_form, "既存編集")
        layout.addWidget(tabs)
        self.new_form.saved.connect(self._saved)
        self.edit_form.saved.connect(self._saved)
        self.edit_form.deleted.connect(self._deleted)

    def _saved(self, file_name):
        self.edit_form.reload_files(file_name)
        self.library_changed.emit(file_name)

    def _deleted(self, file_name):
        self.library_changed.emit(file_name)
