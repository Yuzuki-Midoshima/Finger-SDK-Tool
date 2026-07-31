"""Maya operations for building finger set-driven-key networks."""

from __future__ import annotations

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


def import_finger_controller(side):
    """Return an existing controller or import and place a new one."""
    target_name = "{}_fingers_anim".format(side)
    if cmds.objExists(target_name):
        return target_name

    file_path = RESOURCE_DIR / "fingers_anim.ma"
    wrist = "{}_wrist_skn_jnt".format(side)
    if not file_path.is_file():
        raise RuntimeError("Missing controller asset: {}".format(file_path))
    if not cmds.objExists(wrist):
        raise RuntimeError("Missing wrist joint: {}".format(wrist))

    before = set(cmds.ls(assemblies=True) or [])
    cmds.file(
        str(file_path),
        i=True,
        ignoreVersion=True,
        mergeNamespacesOnClash=False,
        namespace=":",
        returnNewNodes=True,
    )
    new_roots = set(cmds.ls(assemblies=True) or []) - before
    candidates = [
        node
        for node in new_roots
        if cmds.listRelatives(node, shapes=True, type="nurbsCurve")
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            "Expected one imported controller, found {}".format(len(candidates))
        )

    controller = candidates[0]
    cmds.delete(cmds.parentConstraint(wrist, controller, maintainOffset=False))
    controller = cmds.rename(controller, target_name)
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


def remove_driver_sdk(controller, attr_name):
    if not cmds.objExists(controller):
        return
    if not cmds.attributeQuery(attr_name, node=controller, exists=True):
        return

    plug = "{}.{}".format(controller, attr_name)
    curves = cmds.listConnections(
        plug, source=False, destination=True, type="animCurve"
    ) or []
    if curves:
        cmds.delete(list(set(curves)))
    try:
        cmds.deleteAttr(plug)
    except RuntimeError as exc:
        raise RuntimeError("Could not remove {}: {}".format(plug, exc)) from exc


def cleanup_unselected_template_attrs(controller, poses):
    selected = {pose.driver_attr for pose in poses}
    for attr in cmds.listAttr(controller, userDefined=True) or []:
        if attr not in selected:
            remove_driver_sdk(controller, attr)
    return selected


def build_pose(pose, side, driver_ctrl):
    ensure_driver_attr(driver_ctrl, pose.driver_attr, pose.driver_value)
    driver_plug = "{}.{}".format(driver_ctrl, pose.driver_attr)
    targets = []
    for key, values in pose.joints.items():
        joint = resolve_scene_joint(key, side)
        if joint and cmds.objExists(joint):
            targets.append((joint, values))
    if not targets:
        raise RuntimeError("No matching {} finger joints found".format(side))

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
