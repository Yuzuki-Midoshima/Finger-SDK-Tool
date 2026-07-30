"""Pure-Python domain logic for Finger SDK Tool."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional


ROTATION_AXES = ("rotateX", "rotateY", "rotateZ")
VALID_SIDES = ("L", "R")
ATTRIBUTE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class PoseValidationError(ValueError):
    """Raised when a pose template cannot be used safely."""


@dataclass(frozen=True)
class Pose:
    name: str
    driver_attr: str
    driver_value: float
    joints: Dict[str, Dict[str, float]]
    source: Path


def load_pose(path) -> Pose:
    source = Path(path)
    try:
        with source.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, ValueError) as exc:
        raise PoseValidationError("{}: {}".format(source.name, exc)) from exc

    if not isinstance(data, Mapping):
        raise PoseValidationError("{}: root must be an object".format(source.name))

    name = data.get("pose_name") or source.stem
    driver_attr = data.get("driver_attr")
    driver_value = data.get("driver_value", 10)
    joints = data.get("joints")

    if not isinstance(name, str) or not name.strip():
        raise PoseValidationError("{}: pose_name must be text".format(source.name))
    if not isinstance(driver_attr, str) or not ATTRIBUTE_PATTERN.match(driver_attr):
        raise PoseValidationError(
            "{}: driver_attr must be a valid Maya attribute name".format(source.name)
        )
    if not isinstance(driver_value, (int, float)) or isinstance(driver_value, bool):
        raise PoseValidationError("{}: driver_value must be numeric".format(source.name))
    if driver_value <= 0:
        raise PoseValidationError("{}: driver_value must be greater than 0".format(source.name))
    if not isinstance(joints, Mapping) or not joints:
        raise PoseValidationError("{}: joints must be a non-empty object".format(source.name))

    clean_joints = {}
    for joint, rotations in joints.items():
        if not isinstance(joint, str) or not joint.strip():
            raise PoseValidationError("{}: invalid joint name".format(source.name))
        if not isinstance(rotations, Mapping):
            raise PoseValidationError("{}: {} must be an object".format(source.name, joint))

        unknown = set(rotations) - set(ROTATION_AXES)
        if unknown:
            raise PoseValidationError(
                "{}: {} has unsupported channels: {}".format(
                    source.name, joint, ", ".join(sorted(unknown))
                )
            )

        clean_rotations = {}
        for axis, value in rotations.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise PoseValidationError(
                    "{}: {}.{} must be numeric".format(source.name, joint, axis)
                )
            clean_rotations[axis] = float(value)
        clean_joints[joint] = clean_rotations

    return Pose(
        name=name.strip(),
        driver_attr=driver_attr,
        driver_value=float(driver_value),
        joints=clean_joints,
        source=source,
    )


def resolve_scene_joint(json_key: str, side: str) -> Optional[str]:
    if side not in VALID_SIDES:
        raise ValueError("side must be L or R")

    key = str(json_key).strip()
    if key.startswith(VALID_SIDES):
        return key if key.startswith(side + "_") else None

    aliases = {
        "index1": "index1_jnt",
        "index2": "index2_jnt",
        "index3": "index3_jnt",
        "middle1": "middle1_jnt",
        "middle2": "middle2_jnt",
        "middle3": "middle3_jnt",
        "ring1": "ring1_jnt",
        "ring2": "ring2_jnt",
        "ring3": "ring3_jnt",
        "pinky1": "pinky1_jnt",
        "pinky2": "pinky2_jnt",
        "pinky3": "pinky3_jnt",
        "pinky4": "pinky4_jnt",
        "thumb_palm": "thumb_palm_jnt",
        "thumb1": "thumb1_jnt",
        "thumb2": "thumb2_jnt",
        "thumb3": "thumb3_jnt",
    }
    suffix = key if key.endswith("_jnt") else aliases.get(key.lower(), key)
    return "{}_{}".format(side, suffix)

