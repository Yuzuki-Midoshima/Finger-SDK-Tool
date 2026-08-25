import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from core import Pose


class BuildCleanupTests(unittest.TestCase):
    def setUp(self):
        maya_module = types.ModuleType("maya")
        cmds_module = types.ModuleType("maya.cmds")
        maya_module.cmds = cmds_module

        with mock.patch.dict(
            sys.modules, {"maya": maya_module, "maya.cmds": cmds_module}
        ):
            sys.modules.pop("builder", None)
            self.builder = importlib.import_module("builder")

    @staticmethod
    def make_pose():
        return Pose(
            name="fist",
            driver_attr="fist",
            driver_value=10.0,
            joints={
                "index1_jnt": {"rotateZ": -75.0},
                "ring3_jnt": {"rotateZ": -80.0},
                "pinky2_jnt": {"rotateZ": -85.0},
            },
            source=Path("fist.json"),
        )

    def test_resolve_pose_targets_when_all_joints_exist(self):
        self.builder.cmds.objExists = lambda name: True

        targets, missing = self.builder.resolve_pose_targets(
            self.make_pose(), "L"
        )

        self.assertEqual(len(targets), 3)
        self.assertEqual(missing, [])

    def test_resolve_pose_targets_reports_partial_missing_joints(self):
        missing_names = {"L_ring3_jnt"}
        self.builder.cmds.objExists = lambda name: name not in missing_names

        targets, missing = self.builder.resolve_pose_targets(
            self.make_pose(), "L"
        )

        self.assertEqual(len(targets), 2)
        self.assertEqual(missing, ["L_ring3_jnt"])

    def test_resolve_pose_targets_reports_zero_found_joints(self):
        self.builder.cmds.objExists = lambda name: False

        targets, missing = self.builder.resolve_pose_targets(
            self.make_pose(), "L"
        )

        self.assertEqual(targets, [])
        self.assertEqual(
            missing, ["L_index1_jnt", "L_ring3_jnt", "L_pinky2_jnt"]
        )

    def test_rebuild_only_deletes_curves_for_selected_driver_attribute(self):
        builder = self.builder

        calls = []
        builder.cmds.objExists = lambda name: True
        builder.cmds.attributeQuery = lambda *args, **kwargs: True
        builder.cmds.listConnections = lambda plug, **kwargs: (
            ["fist_sdk_curve"] if plug == "L_fingers_anim.fist" else []
        )
        builder.cmds.delete = lambda nodes: calls.append(("delete", nodes))
        builder.cmds.setAttr = lambda *args, **kwargs: None
        builder.cmds.setDrivenKeyframe = lambda *args, **kwargs: None
        builder.cmds.listAttr = lambda *args, **kwargs: self.fail(
            "Rebuild must not enumerate unrelated user-defined attributes"
        )
        builder.cmds.deleteAttr = lambda *args, **kwargs: self.fail(
            "Rebuild must not delete driver attributes"
        )

        count = builder.build_pose(self.make_pose(), "L", "L_fingers_anim")

        self.assertEqual(count, 3)
        self.assertEqual(calls, [("delete", ["fist_sdk_curve"])])

    def test_partial_build_only_keys_existing_joints(self):
        builder = self.builder
        missing_name = "L_ring3_jnt"
        keyed_plugs = []
        builder.cmds.objExists = lambda name: name != missing_name
        builder.cmds.attributeQuery = lambda *args, **kwargs: True
        builder.cmds.listConnections = lambda *args, **kwargs: []
        builder.cmds.setAttr = lambda *args, **kwargs: None
        builder.cmds.setDrivenKeyframe = lambda plug, **kwargs: keyed_plugs.append(plug)

        count = builder.build_pose(self.make_pose(), "L", "L_fingers_anim")

        self.assertEqual(count, 2)
        self.assertFalse(any(plug.startswith(missing_name + ".") for plug in keyed_plugs))

    def test_zero_found_build_raises_before_scene_changes(self):
        builder = self.builder
        builder.cmds.objExists = lambda name: False
        builder.cmds.attributeQuery = lambda *args, **kwargs: self.fail(
            "Driver attributes must not be inspected when no target joints exist"
        )
        builder.cmds.setAttr = lambda *args, **kwargs: self.fail(
            "Scene must not change when no target joints exist"
        )

        with self.assertRaisesRegex(RuntimeError, "No matching L finger joints"):
            builder.build_pose(self.make_pose(), "L", "L_fingers_anim")


if __name__ == "__main__":
    unittest.main()
