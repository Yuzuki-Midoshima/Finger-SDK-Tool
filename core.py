"""Pure-Python domain logic for Finger SDK Tool."""

from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional


ROTATION_AXES = ("rotateX", "rotateY", "rotateZ")
VALID_SIDES = ("L", "R")
ATTRIBUTE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
FILE_STEM_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


class PoseValidationError(ValueError):
    """Raised when a pose template cannot be used safely."""


@dataclass(frozen=True)
class Pose:
    name: str
    driver_attr: str
    driver_value: float
    joints: Dict[str, Dict[str, float]]
    source: Path
    driver_type: str = "number"
    driver_min: float = 0.0
    driver_off_name: str = "OFF"
    driver_on_name: str = "ON"


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
    driver_type = data.get("driver_type", "number")
    driver_min = data.get("driver_min", 0)
    driver_off_name = data.get("driver_off_name", "OFF")
    driver_on_name = data.get("driver_on_name", "ON")
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
    if driver_type not in ("number", "bool", "enum"):
        raise PoseValidationError(
            "{}: driver_type must be number or enum".format(source.name)
        )
    if not isinstance(driver_min, (int, float)) or isinstance(driver_min, bool):
        raise PoseValidationError("{}: driver_min must be numeric".format(source.name))
    if driver_type == "number" and not driver_min <= 0 < driver_value:
        raise PoseValidationError(
            "{}: numeric driver range must include 0".format(source.name)
        )
    if driver_type in ("bool", "enum"):
        driver_type = "enum"
        driver_min, driver_value = 0, 1
        for label, value in (("first", driver_off_name), ("second", driver_on_name)):
            if not isinstance(value, str) or not value.strip() or ":" in value:
                raise PoseValidationError(
                    "{}: {} enum name must be text without ':'".format(source.name, label)
                )
        if driver_off_name.strip() == driver_on_name.strip():
            raise PoseValidationError("{}: enum names must be different".format(source.name))
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
        driver_type=driver_type,
        driver_min=float(driver_min),
        driver_off_name=driver_off_name.strip(),
        driver_on_name=driver_on_name.strip(),
    )


def validate_file_stem(value: str) -> str:
    """Return a safe JSON filename stem or raise a validation error."""
    stem = str(value).strip()
    if not FILE_STEM_PATTERN.match(stem):
        raise PoseValidationError(
            "file name must start with a letter or underscore and contain only "
            "letters, numbers, underscores, or hyphens"
        )
    return stem


def save_pose_data(path, data, overwrite=False) -> Pose:
    """Validate and atomically save pose data."""
    target = Path(path)
    if target.suffix.lower() != ".json":
        raise PoseValidationError("pose file must use the .json extension")
    if target.exists() and not overwrite:
        raise FileExistsError(str(target))

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".json", prefix=".pose_",
            dir=str(target.parent), delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=4)
            stream.write("\n")
        load_pose(temporary)
        temporary.replace(target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return load_pose(target)


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


def canonical_pose_joint_key(name: str, side: str) -> str:
    """Convert common rig joint naming variants to a portable pose slot key."""
    leaf = str(name).rsplit("|", 1)[-1].rsplit(":", 1)[-1]
    prefix = side + "_"
    if leaf.lower().startswith(prefix.lower()):
        leaf = leaf[len(prefix):]

    words = re.findall(r"[A-Za-z]+|\d+", leaf.lower())
    compact = "".join(words)
    finger = next(
        (value for value in ("thumb", "index", "middle", "ring", "pinky")
         if value in compact),
        None,
    )
    if not finger:
        return leaf
    if finger == "thumb" and "palm" in compact:
        return "thumb_palm_jnt"
    numbers = [int(word) for word in words if word.isdigit()]
    if numbers:
        return "{}{}_jnt".format(finger, numbers[-1])
    return leaf


def joint_name_match_score(json_key: str, scene_name: str, side: str) -> int:
    """Score a scene joint against a pose key without requiring exact naming."""
    if side not in VALID_SIDES:
        raise ValueError("side must be L or R")

    leaf = str(scene_name).rsplit("|", 1)[-1].rsplit(":", 1)[-1]
    words = re.findall(r"[A-Za-z]+|\d+", leaf.lower())
    if not words:
        return 0

    opposite = "r" if side == "L" else "l"
    side_word = side.lower()
    if opposite in words and side_word not in words:
        return 0

    ignored = {"jnt", "joint", "skn", "skin", "bind", "bn", "bone", "drv"}
    scene_words = [word for word in words if word not in ignored]
    scene_compact = "".join(
        str(int(word)) if word.isdigit() else word for word in scene_words
    )

    expected = resolve_scene_joint(json_key, side)
    if not expected:
        return 0
    expected_words = re.findall(r"[A-Za-z]+|\d+", expected.lower())
    expected_words = [word for word in expected_words if word not in ignored]
    expected_compact = "".join(
        str(int(word)) if word.isdigit() else word for word in expected_words
    )

    if scene_compact == expected_compact:
        return 100
    if expected_compact in scene_compact:
        return 80

    # Also accept rigs that spell the ordinal as 01, 02, etc. or insert
    # arbitrary separators and role words around the semantic finger slot.
    semantic = [word for word in expected_words if word not in ("l", "r")]
    semantic_text = "".join(
        str(int(word)) if word.isdigit() else word for word in semantic
    )
    if semantic_text and semantic_text in scene_compact:
        return 60 + (10 if side_word in scene_words else 0)

    slot = re.match(r"(thumb|index|middle|ring|pinky)(palm|\d+)$", semantic_text)
    if slot:
        finger, ordinal = slot.groups()
        ordinal_matches = (
            "palm" in scene_compact
            if ordinal == "palm"
            else any(word.isdigit() and int(word) == int(ordinal) for word in words)
        )
        if finger in scene_compact and ordinal_matches:
            return 50 + (10 if side_word in scene_words else 0)
    return 0
