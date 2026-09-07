import json
import tempfile
import unittest
from pathlib import Path

from core import (
    canonical_pose_joint_key,
    PoseValidationError,
    load_pose,
    joint_name_match_score,
    resolve_scene_joint,
    save_pose_data,
    validate_file_stem,
)


class PoseTests(unittest.TestCase):
    def write_pose(self, data):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "pose.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_loads_valid_pose(self):
        path = self.write_pose(
            {
                "pose_name": "Fist",
                "driver_attr": "fist",
                "driver_value": 10,
                "joints": {"index1_jnt": {"rotateZ": -75}},
            }
        )
        pose = load_pose(path)
        self.assertEqual(pose.name, "Fist")
        self.assertEqual(pose.joints["index1_jnt"]["rotateZ"], -75.0)

    def test_rejects_invalid_attribute(self):
        path = self.write_pose(
            {"driver_attr": "bad attr", "joints": {"index1_jnt": {"rotateZ": 1}}}
        )
        with self.assertRaises(PoseValidationError):
            load_pose(path)

    def test_rejects_unknown_channel(self):
        path = self.write_pose(
            {"driver_attr": "fist", "joints": {"index1_jnt": {"translateX": 1}}}
        )
        with self.assertRaises(PoseValidationError):
            load_pose(path)

    def test_loads_numeric_range(self):
        path = self.write_pose(
            {"driver_attr": "curl", "driver_type": "number",
             "driver_min": -10, "driver_value": 10,
             "joints": {"index1_jnt": {"rotateZ": 1}}}
        )
        pose = load_pose(path)
        self.assertEqual((pose.driver_min, pose.driver_value), (-10.0, 10.0))

    def test_legacy_bool_driver_becomes_two_name_enum(self):
        path = self.write_pose(
            {"driver_attr": "spreadOn", "driver_type": "bool",
             "joints": {"index1_jnt": {"rotateZ": 1}}}
        )
        pose = load_pose(path)
        self.assertEqual((pose.driver_type, pose.driver_min, pose.driver_value),
                         ("enum", 0.0, 1.0))

    def test_loads_custom_enum_names(self):
        path = self.write_pose(
            {"driver_attr": "visibilityMode", "driver_type": "enum",
             "driver_off_name": "Hide", "driver_on_name": "Show",
             "joints": {"index1_jnt": {"rotateZ": 1}}}
        )
        pose = load_pose(path)
        self.assertEqual((pose.driver_off_name, pose.driver_on_name),
                         ("Hide", "Show"))


class JointResolutionTests(unittest.TestCase):
    def test_canonicalizes_single_maya_joint_for_existing_pose_row(self):
        self.assertEqual(
            canonical_pose_joint_key("|rig|L_thumb_02_jnt", "L"),
            "thumb2_jnt",
        )
        self.assertEqual(
            canonical_pose_joint_key("char:L_indexFinger_01_skn_joint", "L"),
            "index1_jnt",
        )

    def test_suffix_and_alias(self):
        self.assertEqual(resolve_scene_joint("index1_jnt", "L"), "L_index1_jnt")
        self.assertEqual(resolve_scene_joint("thumb_palm", "R"), "R_thumb_palm_jnt")

    def test_explicit_opposite_side_is_ignored(self):
        self.assertIsNone(resolve_scene_joint("R_index1_jnt", "L"))

    def test_invalid_side(self):
        with self.assertRaises(ValueError):
            resolve_scene_joint("index1_jnt", "C")

    def test_flexible_scene_joint_names(self):
        self.assertGreater(
            joint_name_match_score("index1_jnt", "|rig|char:L_index_01_bind_jnt", "L"),
            0,
        )
        self.assertEqual(
            joint_name_match_score("index1_jnt", "R_index_01_bind_jnt", "L"),
            0,
        )


class PoseSaveTests(unittest.TestCase):
    def test_saves_valid_pose_and_prevents_accidental_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "peace.json"
            data = {
                "pose_name": "Peace",
                "driver_attr": "peace",
                "driver_value": 10,
                "joints": {"index1_jnt": {"rotateZ": 5}},
            }
            pose = save_pose_data(path, data)
            self.assertEqual(pose.name, "Peace")
            with self.assertRaises(FileExistsError):
                save_pose_data(path, data)

    def test_rejects_unsafe_file_stem(self):
        with self.assertRaises(PoseValidationError):
            validate_file_stem("../pose")


if __name__ == "__main__":
    unittest.main()
