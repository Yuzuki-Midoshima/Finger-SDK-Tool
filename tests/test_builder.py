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

    def test_manual_finger_root_resolves_by_hierarchy(self):
        hierarchy = {
            "|hand|fingerA": ["|hand|fingerA|segmentA"],
            "|hand|fingerA|segmentA": ["|hand|fingerA|segmentA|segmentB"],
            "|hand|fingerA|segmentA|segmentB": [],
        }
        self.builder.cmds.objExists = lambda name: name in hierarchy
        self.builder.cmds.ls = lambda **kwargs: []
        self.builder.cmds.listRelatives = lambda node, **kwargs: hierarchy[node]

        targets, missing = self.builder.resolve_pose_targets(
            self.make_pose(), "L", {"index": "|hand|fingerA"}
        )

        self.assertEqual(targets[0][0], "|hand|fingerA")
        self.assertEqual(missing, ["L_ring3_jnt", "L_pinky2_jnt"])

    def test_three_joint_thumb_does_not_shift_second_joint(self):
        hierarchy = {
            "|hand|thumbA": ["|hand|thumbA|thumbB"],
            "|hand|thumbA|thumbB": ["|hand|thumbA|thumbB|thumbC"],
            "|hand|thumbA|thumbB|thumbC": [],
        }
        pose = Pose(
            name="thumb",
            driver_attr="thumb",
            driver_value=10.0,
            joints={
                "thumb_palm_jnt": {"rotateZ": 1.0},
                "thumb1_jnt": {"rotateZ": 2.0},
                "thumb2_jnt": {"rotateZ": 3.0},
                "thumb3_jnt": {"rotateZ": 4.0},
            },
            source=Path("thumb.json"),
        )
        self.builder.cmds.objExists = lambda name: name in hierarchy
        self.builder.cmds.ls = lambda **kwargs: []
        self.builder.cmds.listRelatives = lambda node, **kwargs: hierarchy[node]

        targets, missing = self.builder.resolve_pose_targets(
            pose, "L", {"thumb": "|hand|thumbA"}
        )

        self.assertEqual(
            [joint for joint, _values in targets],
            [
                "|hand|thumbA",
                "|hand|thumbA",
                "|hand|thumbA|thumbB",
                "|hand|thumbA|thumbB|thumbC",
            ],
        )
        self.assertEqual(missing, [])

    def test_three_joint_thumb_combines_palm_and_first_rotation(self):
        hierarchy = {
            "|hand|thumbA": ["|hand|thumbA|thumbB"],
            "|hand|thumbA|thumbB": ["|hand|thumbA|thumbB|thumbC"],
            "|hand|thumbA|thumbB|thumbC": [],
        }
        pose = Pose(
            name="thumb",
            driver_attr="thumb",
            driver_value=10.0,
            joints={
                "thumb_palm_jnt": {"rotateZ": -10.0},
                "thumb1_jnt": {"rotateZ": -30.0},
            },
            source=Path("thumb.json"),
        )
        driven_keys = []
        self.builder.cmds.objExists = lambda name: name in hierarchy or name == "ctrl"
        self.builder.cmds.ls = lambda **kwargs: []
        self.builder.cmds.listRelatives = lambda node, **kwargs: hierarchy[node]
        self.builder.cmds.attributeQuery = lambda *args, **kwargs: True
        self.builder.cmds.listConnections = lambda *args, **kwargs: []
        self.builder.cmds.setAttr = lambda *args, **kwargs: None
        self.builder.cmds.setDrivenKeyframe = (
            lambda plug, **kwargs: driven_keys.append((plug, kwargs))
        )

        count = self.builder.build_pose(
            pose, "L", "ctrl", {"thumb": "|hand|thumbA"}
        )

        self.assertEqual(count, 1)
        self.assertTrue(
            any(kwargs.get("value") == -40.0 for _plug, kwargs in driven_keys)
        )

    def test_thumb_one_root_ignores_end_joint_when_mapping_thumb_two(self):
        hierarchy = {
            "|hand|L_thumb_1_jnt": ["|hand|L_thumb_1_jnt|L_thumb_2_jnt"],
            "|hand|L_thumb_1_jnt|L_thumb_2_jnt": [
                "|hand|L_thumb_1_jnt|L_thumb_2_jnt|L_thumb_3_jnt"
            ],
            "|hand|L_thumb_1_jnt|L_thumb_2_jnt|L_thumb_3_jnt": [
                "|hand|L_thumb_1_jnt|L_thumb_2_jnt|L_thumb_3_jnt|L_thumb_end_jnt"
            ],
            "|hand|L_thumb_1_jnt|L_thumb_2_jnt|L_thumb_3_jnt|L_thumb_end_jnt": [],
        }
        pose = Pose(
            name="thumb",
            driver_attr="thumb",
            driver_value=10.0,
            joints={"thumb2_jnt": {"rotateZ": -20.0}},
            source=Path("thumb.json"),
        )
        self.builder.cmds.objExists = lambda name: name in hierarchy
        self.builder.cmds.ls = lambda **kwargs: []
        self.builder.cmds.listRelatives = lambda node, **kwargs: hierarchy[node]

        targets, missing = self.builder.resolve_pose_targets(
            pose, "L", {"thumb": "|hand|L_thumb_1_jnt"}
        )

        self.assertEqual(targets[0][0], "|hand|L_thumb_1_jnt|L_thumb_2_jnt")
        self.assertEqual(missing, [])

    def test_thumb_mapping_can_force_four_level_palm_mode(self):
        hierarchy = {
            "|hand|L_thumb_1_jnt": ["|hand|L_thumb_1_jnt|L_thumb_2_jnt"],
            "|hand|L_thumb_1_jnt|L_thumb_2_jnt": [
                "|hand|L_thumb_1_jnt|L_thumb_2_jnt|L_thumb_3_jnt"
            ],
            "|hand|L_thumb_1_jnt|L_thumb_2_jnt|L_thumb_3_jnt": [],
        }
        pose = Pose(
            name="thumb",
            driver_attr="thumb",
            driver_value=10.0,
            joints={"thumb1_jnt": {"rotateZ": -20.0}},
            source=Path("thumb.json"),
        )
        self.builder.cmds.objExists = lambda name: name in hierarchy
        self.builder.cmds.ls = lambda **kwargs: []
        self.builder.cmds.listRelatives = lambda node, **kwargs: hierarchy[node]

        targets, missing = self.builder.resolve_pose_targets(
            pose, "L", {"thumb": "|hand|L_thumb_1_jnt"}, "palm"
        )

        self.assertEqual(targets[0][0], "|hand|L_thumb_1_jnt|L_thumb_2_jnt")
        self.assertEqual(missing, [])

    def test_axis_inversion_does_not_flip_mapped_thumb(self):
        hierarchy = {"|hand|thumbA": []}
        pose = Pose(
            name="thumb",
            driver_attr="thumb",
            driver_value=10.0,
            joints={"thumb1_jnt": {"rotateZ": -38.0}},
            source=Path("thumb.json"),
        )
        driven_keys = []
        self.builder.cmds.objExists = lambda name: name in hierarchy or name == "ctrl"
        self.builder.cmds.ls = lambda **kwargs: []
        self.builder.cmds.listRelatives = lambda node, **kwargs: hierarchy[node]
        self.builder.cmds.attributeQuery = lambda *args, **kwargs: True
        self.builder.cmds.listConnections = lambda *args, **kwargs: []
        self.builder.cmds.setAttr = lambda *args, **kwargs: None
        self.builder.cmds.setDrivenKeyframe = (
            lambda plug, **kwargs: driven_keys.append((plug, kwargs))
        )

        self.builder.build_pose(
            pose, "L", "ctrl", {"thumb": "|hand|thumbA"}, {"rotateZ"}
        )

        self.assertTrue(
            any(kwargs.get("value") == -38.0 for _plug, kwargs in driven_keys)
        )

    def test_same_named_opposite_root_is_found_from_dag_path(self):
        self.builder.cmds.ls = lambda **kwargs: [
            "|character|L_hand|thumb_01_jnt",
            "|character|R_hand|thumb_01_jnt",
        ]

        result = self.builder.find_matching_finger_root(
            "|character|L_hand|thumb_01_jnt", "R"
        )

        self.assertEqual(result, "|character|R_hand|thumb_01_jnt")

    def test_side_token_variant_is_found_as_same_naming_format(self):
        self.builder.cmds.ls = lambda **kwargs: [
            "|character|L_hand|L_index_01_jnt",
            "|character|R_hand|R_index_01_jnt",
        ]

        result = self.builder.find_matching_finger_root(
            "|character|L_hand|L_index_01_jnt", "R"
        )

        self.assertEqual(result, "|character|R_hand|R_index_01_jnt")

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

    def test_build_can_invert_selected_rotation_axes(self):
        builder = self.builder
        driven_keys = []
        builder.cmds.objExists = lambda name: True
        builder.cmds.attributeQuery = lambda *args, **kwargs: True
        builder.cmds.listConnections = lambda *args, **kwargs: []
        builder.cmds.setAttr = lambda *args, **kwargs: None
        builder.cmds.setDrivenKeyframe = (
            lambda plug, **kwargs: driven_keys.append((plug, kwargs))
        )

        builder.build_pose(
            self.make_pose(), "L", "L_fingers_anim", inverted_axes={"rotateZ"}
        )

        self.assertTrue(
            any(
                plug == "L_index1_jnt.rotateZ"
                and kwargs.get("driverValue") == 10.0
                and kwargs.get("value") == 75.0
                for plug, kwargs in driven_keys
            )
        )

    def test_rebuild_does_not_set_connected_driven_attributes(self):
        builder = self.builder
        builder.cmds.objExists = lambda name: True
        builder.cmds.attributeQuery = lambda *args, **kwargs: True
        builder.cmds.listConnections = lambda *args, **kwargs: ["old_sdk_curve"]
        builder.cmds.delete = lambda *args, **kwargs: None
        builder.cmds.setAttr = lambda plug, *args, **kwargs: (
            None
            if plug == "L_fingers_anim.fist"
            else self.fail("Rebuild must not set a possibly connected driven plug")
        )
        builder.cmds.setDrivenKeyframe = lambda *args, **kwargs: None

        builder.build_pose(self.make_pose(), "L", "L_fingers_anim")

    def test_rebuild_removes_disconnected_blend_input(self):
        builder = self.builder
        removed = []

        def connections(plug, **kwargs):
            if plug == "ctrl.fist":
                return ["fist_curve"]
            if plug == "fist_curve.output":
                return ["finger_blend.input[3]"]
            return []

        builder.cmds.listConnections = connections
        builder.cmds.delete = lambda nodes: None
        builder.cmds.nodeType = lambda node: "blendWeighted"
        builder.cmds.objExists = lambda plug: True
        builder.cmds.removeMultiInstance = lambda plug, **kwargs: removed.append(plug)

        builder._delete_driver_curves("ctrl.fist")

        self.assertEqual(removed, ["finger_blend.input[3]"])

    def test_prepare_rebuild_disconnects_residual_unit_conversion_inputs(self):
        builder = self.builder
        pose = self.make_pose()
        residual = {
            "L_index1_jnt.rotateX": ["unitConversion2027.output"],
            "L_index1_jnt.rotateY": ["unitConversion2030.output"],
            "L_index1_jnt.rotateZ": ["unitConversion2033.output"],
        }
        disconnected = []
        builder.cmds.objExists = lambda name: name.startswith("L_")
        builder.cmds.ls = lambda **kwargs: []

        def connections(plug, **kwargs):
            if kwargs.get("type") == "animCurve":
                return []
            return list(residual.get(plug, []))

        def disconnect(source, destination):
            disconnected.append((source, destination))
            residual[destination].remove(source)

        builder.cmds.listConnections = connections
        builder.cmds.disconnectAttr = disconnect

        result = builder.prepare_pose_rebuild(
            [pose], "L", "L_fingers_anim"
        )

        self.assertEqual(result, disconnected)
        self.assertEqual(len(disconnected), 3)
        self.assertTrue(all(not values for values in residual.values()))

        repeated = builder.prepare_pose_rebuild(
            [pose], "L", "L_fingers_anim"
        )
        self.assertEqual(repeated, [])
        self.assertEqual(len(disconnected), 3)

    def test_prepare_rebuild_only_inspects_selected_pose_targets(self):
        builder = self.builder
        inspected = []
        builder.cmds.objExists = lambda name: name.startswith("L_")
        builder.cmds.ls = lambda **kwargs: []

        def connections(plug, **kwargs):
            if ".rotate" in plug:
                inspected.append(plug)
            return []

        builder.cmds.listConnections = connections
        builder.cmds.disconnectAttr = lambda *args: None

        builder.prepare_pose_rebuild(
            [self.make_pose()], "L", "L_fingers_anim"
        )

        self.assertEqual(
            set(inspected),
            {
                "L_index1_jnt.rotateX", "L_index1_jnt.rotateY", "L_index1_jnt.rotateZ",
                "L_ring3_jnt.rotateX", "L_ring3_jnt.rotateY", "L_ring3_jnt.rotateZ",
                "L_pinky2_jnt.rotateX", "L_pinky2_jnt.rotateY", "L_pinky2_jnt.rotateZ",
            },
        )

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

    def test_existing_controller_does_not_require_named_wrist(self):
        builder = self.builder
        builder.cmds.objExists = lambda name: name == "R_fingers_anim"

        result = builder.validate_controller_target("R", "R_fingers_anim")

        self.assertEqual(result, "R_fingers_anim")


if __name__ == "__main__":
    unittest.main()
