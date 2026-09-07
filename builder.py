"""Maya operations for building finger set-driven-key networks."""

from __future__ import annotations

import re
from pathlib import Path

import maya.cmds as cmds

from core import ROTATION_AXES, joint_name_match_score, load_pose, resolve_scene_joint


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
CONTROLLER_Y_ADDITION = 10.0
FINGER_SLOT_PATTERN = re.compile(
    r"^(thumb|index|middle|ring|pinky)_?(palm|\d+)(?:_jnt)?$", re.IGNORECASE
)


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


def ensure_driver_attr(
    controller, attr_name, maximum, minimum=0.0, driver_type="number",
    off_name="OFF", on_name="ON",
):
    if not cmds.objExists(controller):
        raise RuntimeError("Missing controller: {}".format(controller))
    if not cmds.attributeQuery(attr_name, node=controller, exists=True):
        options = {
            "longName": attr_name,
            "attributeType": "enum" if driver_type == "enum" else "double",
            "defaultValue": 0,
            "keyable": True,
        }
        if driver_type == "enum":
            options["enumName"] = "{}:{}".format(off_name, on_name)
        else:
            options.update(minValue=minimum, maxValue=maximum)
        cmds.addAttr(controller, **options)


def validate_controller_target(side, controller_name=None, wrist=None):
    """Validate one controller target before scene changes begin."""
    target_name = (
        "{}_fingers_anim".format(side)
        if controller_name is None
        else controller_name.strip()
    )
    if not target_name:
        raise ValueError("Controller name cannot be empty")
    # An existing controller can be rebuilt without locating its original wrist.
    # The wrist is only required when a new controller must be placed and parented.
    if cmds.objExists(target_name):
        return target_name

    file_path = RESOURCE_DIR / "fingers_anim.ma"
    wrist = wrist or "{}_wrist_skn_jnt".format(side)
    if not file_path.is_file():
        raise RuntimeError("Missing controller asset: {}".format(file_path))
    if not cmds.objExists(wrist):
        raise RuntimeError("Missing wrist joint: {}".format(wrist))
    return target_name


def import_finger_controller(
    side, controller_name=None, wrist=None, rotation_offset=None
):
    """Return an existing controller or import and place a new one."""
    target_name = validate_controller_target(side, controller_name, wrist)
    if cmds.objExists(target_name):
        return target_name

    file_path = RESOURCE_DIR / "fingers_anim.ma"
    wrist = wrist or "{}_wrist_skn_jnt".format(side)

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

    base_rotation = [0.0, 0.0, 0.0]
    if side == "L":
        base_rotation[1] = -90.0
        base_y = 3.0
    else:
        base_rotation[0] = 180.0
        base_rotation[1] = 90.0
        base_y = -4.0
    rotation_offset = rotation_offset or (0.0, 0.0, 0.0)
    cmds.setAttr(
        controller + ".rotate",
        *(base + offset for base, offset in zip(base_rotation, rotation_offset)),
        type="double3"
    )
    signed_addition = CONTROLLER_Y_ADDITION if side == "L" else -CONTROLLER_Y_ADDITION
    cmds.setAttr(controller + ".translateY", base_y + signed_addition)

    cmds.makeIdentity(controller, apply=True, translate=True, rotate=True, scale=True)
    return controller


def _find_scene_joint(key, side, scene_joints=None):
    """Resolve an exact joint first, then a unique best flexible-name match."""
    exact = resolve_scene_joint(key, side)
    if exact and cmds.objExists(exact):
        return exact

    if scene_joints is None:
        list_joints = getattr(cmds, "ls", None)
        scene_joints = list_joints(type="joint", long=True) or [] if list_joints else []
    scored = [
        (joint_name_match_score(key, joint, side), joint)
        for joint in scene_joints
    ]
    scored = [(score, joint) for score, joint in scored if score]
    if not scored:
        return None
    best_score = max(score for score, _joint in scored)
    best = [joint for score, joint in scored if score == best_score]
    return best[0] if len(best) == 1 else None


def _joint_chain(root):
    """Return a single joint chain beginning at root, stopping at a branch."""
    chain = [root]
    current = root
    while True:
        children = cmds.listRelatives(
            current, children=True, type="joint", fullPath=True
        ) or []
        if len(children) != 1:
            break
        current = children[0]
        chain.append(current)
    return chain


def find_matching_finger_root(source_root, target_side):
    """Find the same-named root below the opposite side's DAG hierarchy."""
    if target_side not in ("L", "R"):
        raise ValueError("target_side must be L or R")
    leaf = str(source_root).rsplit("|", 1)[-1].rsplit(":", 1)[-1].lower()
    source_words = re.findall(r"[A-Za-z]+|\d+", leaf)
    source_signature = tuple(word for word in source_words if word not in ("l", "r"))
    candidates = []
    for joint in cmds.ls(type="joint", long=True) or []:
        if joint == source_root:
            continue
        candidate_leaf = joint.rsplit("|", 1)[-1].rsplit(":", 1)[-1].lower()
        candidate_words = re.findall(r"[A-Za-z]+|\d+", candidate_leaf)
        candidate_signature = tuple(
            word for word in candidate_words if word not in ("l", "r")
        )
        if candidate_leaf == leaf or candidate_signature == source_signature:
            candidates.append(joint)
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        return None

    side_word = target_side.lower()
    opposite = "r" if target_side == "L" else "l"
    scored = []
    for joint in candidates:
        words = re.findall(r"[A-Za-z]+|\d+", joint.lower())
        score = (2 if side_word in words else 0) - (2 if opposite in words else 0)
        scored.append((score, joint))
    best_score = max(score for score, _joint in scored)
    best = [joint for score, joint in scored if score == best_score]
    return best[0] if best_score > 0 and len(best) == 1 else None


def _structural_joint(key, finger_roots, chain_cache, thumb_mode="auto"):
    match = FINGER_SLOT_PATTERN.match(str(key).strip())
    if not match:
        return None
    finger, position = match.groups()
    root = (finger_roots or {}).get(finger.lower())
    if not root or not cmds.objExists(root):
        return None
    if root not in chain_cache:
        chain_cache[root] = _joint_chain(root)
    chain = chain_cache[root]
    if finger.lower() == "thumb":
        root_leaf = root.rsplit("|", 1)[-1].rsplit(":", 1)[-1].lower()
        root_words = re.findall(r"[A-Za-z]+|\d+", root_leaf)
        explicitly_palm = any(
            word in ("palm", "meta", "metacarpal") for word in root_words
        )
        explicitly_first = any(
            word.isdigit() and int(word) == 1 for word in root_words
        )
        last_leaf = chain[-1].rsplit("|", 1)[-1].rsplit(":", 1)[-1].lower()
        last_words = re.findall(r"[A-Za-z]+|\d+", last_leaf)
        functional_count = len(chain) - (
            1 if any(word in ("end", "tip") for word in last_words) else 0
        )
        if thumb_mode == "palm":
            has_palm_joint = True
        elif thumb_mode == "first":
            has_palm_joint = False
        elif explicitly_palm:
            has_palm_joint = True
        elif explicitly_first:
            has_palm_joint = False
        else:
            has_palm_joint = functional_count >= 4
        if position.lower() == "palm":
            return chain[0]
        # A three-joint thumb has no separate palm joint. Combine the template's
        # palm and thumb1 rotations on its first joint instead of shifting the
        # remaining joints by one slot.
        index = int(position) if has_palm_joint else max(int(position) - 1, 0)
    else:
        index = int(position) - 1
    return chain[index] if 0 <= index < len(chain) else None


def _delete_driver_curves(driver_plug):
    """Delete one driver's curves and remove stale blendWeighted input values."""
    curves = cmds.listConnections(
        driver_plug, source=False, destination=True, type="animCurve"
    ) or []
    if not curves:
        return

    orphan_candidates = []
    for curve in set(curves):
        orphan_candidates.extend(
            cmds.listConnections(
                curve + ".output",
                source=False,
                destination=True,
                plugs=True,
            ) or []
        )
    cmds.delete(list(set(curves)))

    node_type = getattr(cmds, "nodeType", None)
    remove_multi = getattr(cmds, "removeMultiInstance", None)
    if not node_type or not remove_multi:
        return
    for plug in set(orphan_candidates):
        node = plug.split(".", 1)[0]
        if node_type(node) != "blendWeighted" or ".input[" not in plug:
            continue
        incoming = cmds.listConnections(plug, source=True, destination=False) or []
        if not incoming and cmds.objExists(plug):
            remove_multi(plug, b=True)


def prepare_pose_rebuild(
    poses, side, driver_ctrl, finger_roots=None, thumb_mode="auto"
):
    """Clean selected managed SDKs and detach residual target rotate inputs.

    Only joints resolved from the selected poses are inspected. Downstream nodes
    that are not managed anim curves are preserved; only their direct connection
    to a target rotate channel is detached.
    """
    target_joints = set()
    for pose in poses:
        entries, _missing = _resolve_pose_target_entries(
            pose, side, finger_roots, thumb_mode
        )
        target_joints.update(joint for _key, joint, _values in entries)

        driver_plug = "{}.{}".format(driver_ctrl, pose.driver_attr)
        if cmds.objExists(driver_plug):
            _delete_driver_curves(driver_plug)

    disconnected = []
    for joint in sorted(target_joints):
        for axis in ROTATION_AXES:
            driven_plug = "{}.{}".format(joint, axis)
            sources = cmds.listConnections(
                driven_plug, source=True, destination=False, plugs=True
            ) or []
            for source_plug in list(dict.fromkeys(sources)):
                cmds.disconnectAttr(source_plug, driven_plug)
                disconnected.append((source_plug, driven_plug))

            remaining = cmds.listConnections(
                driven_plug, source=True, destination=False, plugs=True
            ) or []
            if remaining:
                raise RuntimeError(
                    "Could not clear input connection on {}: {}".format(
                        driven_plug, ", ".join(remaining)
                    )
                )
    return disconnected


def _resolve_pose_target_entries(
    pose, side, finger_roots=None, thumb_mode="auto"
):
    """Return semantic keys with resolved targets and unresolved slots."""
    entries = []
    missing = []
    list_joints = getattr(cmds, "ls", None)
    scene_joints = list_joints(type="joint", long=True) or [] if list_joints else []
    chain_cache = {}
    for key, values in pose.joints.items():
        joint = _structural_joint(key, finger_roots, chain_cache, thumb_mode)
        if not joint:
            joint = _find_scene_joint(key, side, scene_joints)
        if joint:
            entries.append((key, joint, values))
        else:
            expected = resolve_scene_joint(key, side)
            if expected:
                missing.append(expected)
    return entries, missing


def resolve_pose_targets(pose, side, finger_roots=None, thumb_mode="auto"):
    """Return resolved targets and unresolved expected slots for one pose/side."""
    entries, missing = _resolve_pose_target_entries(
        pose, side, finger_roots, thumb_mode
    )
    return [(joint, values) for _key, joint, values in entries], missing


def build_pose(
    pose, side, driver_ctrl, finger_roots=None, inverted_axes=None,
    thumb_mode="auto", cleanup_existing=True,
):
    entries, _missing = _resolve_pose_target_entries(
        pose, side, finger_roots, thumb_mode
    )
    if not entries:
        raise RuntimeError("No matching {} finger joints found".format(side))
    merged = {}
    for key, joint, rotations in entries:
        item = merged.setdefault(
            joint, {"rotations": {}, "is_thumb": str(key).lower().startswith("thumb")}
        )
        for axis, value in rotations.items():
            item["rotations"][axis] = item["rotations"].get(axis, 0.0) + value
    ensure_driver_attr(
        driver_ctrl, pose.driver_attr, pose.driver_value,
        pose.driver_min, pose.driver_type,
        pose.driver_off_name, pose.driver_on_name,
    )
    driver_plug = "{}.{}".format(driver_ctrl, pose.driver_attr)

    # Rebuilding must replace, not stack, the existing network.
    if cleanup_existing:
        _delete_driver_curves(driver_plug)

    for joint in merged:
        for axis in ROTATION_AXES:
            plug = "{}.{}".format(joint, axis)
            cmds.setDrivenKeyframe(
                plug, currentDriver=driver_plug, driverValue=0, value=0
            )

    inverted_axes = set(inverted_axes or ())
    for joint, item in merged.items():
        rotations = item["rotations"]
        is_thumb = item["is_thumb"]
        for axis, value in rotations.items():
            plug = "{}.{}".format(joint, axis)
            if axis in inverted_axes and not is_thumb:
                value = -value
            cmds.setDrivenKeyframe(
                plug,
                currentDriver=driver_plug,
                driverValue=pose.driver_value,
                value=value,
            )
    cmds.setAttr(driver_plug, 0)
    return len(merged)


def build_pose_file(json_path, side, driver_ctrl):
    """Compatibility wrapper for scripts using the original API."""
    return build_pose(load_pose(json_path), side, driver_ctrl)
