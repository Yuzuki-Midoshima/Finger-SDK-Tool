"""Maya operations for building finger set-driven-key networks."""

from __future__ import annotations

import re
from pathlib import Path

import maya.cmds as cmds

from core import ROTATION_AXES, load_pose, resolve_scene_joint


try:
    TOOL_ROOT = Path(__file__).resolve().parent
except NameError:
    # Support direct execution from Maya's Script Editor or a shelf command.
    TOOL_ROOT = (
        Path(cmds.internalVar(userAppDir=True))
        / "scripts"
        / "Finger-SDK-Tool"
    )
RESOURCE_DIR = TOOL_ROOT / "resources"


def _load_controller_curve(file_path):
    """Read the first NURBS curve definition from a Maya ASCII asset."""
    text = file_path.read_text(encoding="utf-8")
    match = re.search(
        r'setAttr\s+"\.cc"\s+-type\s+"nurbsCurve"\s+(.*?);',
        text,
        re.DOTALL,
    )
    if not match:
        raise RuntimeError("Controller curve data was not found: {}".format(file_path))

    values = match.group(1).split()
    try:
        degree = int(values[0])
        knot_count = int(values[5])
        knot_start = 6
        knot_end = knot_start + knot_count
        knots = [float(value) for value in values[knot_start:knot_end]]
        point_count = int(values[knot_end])
        point_values = [float(value) for value in values[knot_end + 1 :]]
        if len(point_values) != point_count * 3:
            raise ValueError("Unexpected CV count")
        points = [
            tuple(point_values[index : index + 3])
            for index in range(0, len(point_values), 3)
        ]
    except (IndexError, TypeError, ValueError) as exc:
        raise RuntimeError(
            "Invalid controller curve data: {}".format(file_path)
        ) from exc
    return degree, knots, points


def set_transform_channels_hidden(controller, hidden):
    """Hide or show transform channels on a finger controller."""
    if not cmds.objExists(controller):
        raise RuntimeError("Missing controller: {}".format(controller))

    for group in ("translate", "rotate", "scale"):
        for axis in "XYZ":
            plug = "{}.{}{}".format(controller, group, axis)
            cmds.setAttr(plug, lock=hidden, keyable=not hidden, channelBox=False)


def ensure_driver_attr(controller, attr_name, maximum):
    if not cmds.objExists(controller):
        raise RuntimeError("Missing controller: {}".format(controller))
    if not cmds.attributeQuery(attr_name, node=controller, exists=True):
        cmds.addAttr(
            controller,
            longName=attr_name,
            attributeType="double",
            minValue=0,
            maxValue=maximum,
            defaultValue=0,
            keyable=True,
        )


def validate_controller_target(side, controller_name=None):
    """Validate one controller target before scene changes begin."""
    target_name = (
        "{}_fingers_anim".format(side)
        if controller_name is None
        else controller_name.strip()
    )
    if not target_name:
        raise ValueError("Controller name cannot be empty")

    file_path = RESOURCE_DIR / "fingers_anim.ma"
    wrist = "{}_wrist_skn_jnt".format(side)
    if not file_path.is_file():
        raise RuntimeError("Missing controller asset: {}".format(file_path))
    if not cmds.objExists(wrist):
        raise RuntimeError("Missing wrist joint: {}".format(wrist))
    return target_name


def import_finger_controller(side, controller_name=None):
    """Return an existing controller or import and place a new one."""
    target_name = validate_controller_target(side, controller_name)
    if cmds.objExists(target_name):
        return target_name

    file_path = RESOURCE_DIR / "fingers_anim.ma"
    wrist = "{}_wrist_skn_jnt".format(side)

    degree, knots, points = _load_controller_curve(file_path)
    controller = cmds.curve(
        degree=degree,
        knot=knots,
        point=points,
        name=target_name,
    )
    cmds.delete(cmds.parentConstraint(wrist, controller, maintainOffset=False))
    cmds.parent(controller, wrist)
    cmds.setAttr(controller + ".scale", 10, 10, 10, type="double3")

    if side == "L":
        cmds.setAttr(controller + ".rotateY", -90)
        cmds.setAttr(controller + ".translateY", 3)
    else:
        cmds.setAttr(controller + ".rotateX", 180)
        cmds.setAttr(controller + ".rotateY", 90)
        cmds.setAttr(controller + ".translateY", -4)

    cmds.makeIdentity(controller, apply=True, translate=True, rotate=True, scale=True)
    return controller


def resolve_pose_targets(pose, side):
    """Return existing targets and missing resolved joint names for one pose/side."""
    targets = []
    missing = []
    for key, values in pose.joints.items():
        joint = resolve_scene_joint(key, side)
        if not joint:
            continue
        if cmds.objExists(joint):
            targets.append((joint, values))
        else:
            missing.append(joint)
    return targets, missing


def build_pose(pose, side, driver_ctrl):
    targets, _missing = resolve_pose_targets(pose, side)
    if not targets:
        raise RuntimeError("No matching {} finger joints found".format(side))
    ensure_driver_attr(driver_ctrl, pose.driver_attr, pose.driver_value)
    driver_plug = "{}.{}".format(driver_ctrl, pose.driver_attr)

    # Rebuilding must replace, not stack, the existing network.
    curves = cmds.listConnections(
        driver_plug, source=False, destination=True, type="animCurve"
    ) or []
    if curves:
        cmds.delete(list(set(curves)))

    cmds.setAttr(driver_plug, 0)
    for joint, _ in targets:
        for axis in ROTATION_AXES:
            plug = "{}.{}".format(joint, axis)
            cmds.setAttr(plug, 0)
            cmds.setDrivenKeyframe(plug, currentDriver=driver_plug)

    cmds.setAttr(driver_plug, pose.driver_value)
    for joint, rotations in targets:
        for axis, value in rotations.items():
            plug = "{}.{}".format(joint, axis)
            cmds.setAttr(plug, value)
            cmds.setDrivenKeyframe(plug, currentDriver=driver_plug)
    cmds.setAttr(driver_plug, 0)
    return len(targets)


def build_pose_file(json_path, side, driver_ctrl):
    """Compatibility wrapper for scripts using the original API."""
    return build_pose(load_pose(json_path), side, driver_ctrl)
