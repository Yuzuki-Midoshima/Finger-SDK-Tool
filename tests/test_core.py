import json
import tempfile
import unittest
from pathlib import Path

from core import PoseValidationError, load_pose, resolve_scene_joint


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


class JointResolutionTests(unittest.TestCase):
    def test_suffix_and_alias(self):
        self.assertEqual(resolve_scene_joint("index1_jnt", "L"), "L_index1_jnt")
        self.assertEqual(resolve_scene_joint("thumb_palm", "R"), "R_thumb_palm_jnt")

    def test_explicit_opposite_side_is_ignored(self):
        self.assertIsNone(resolve_scene_joint("R_index1_jnt", "L"))

    def test_invalid_side(self):
        with self.assertRaises(ValueError):
            resolve_scene_joint("index1_jnt", "C")


if __name__ == "__main__":
    unittest.main()

