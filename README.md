# Finger SDK Tool

A production-minded Autodesk Maya tool that builds reusable finger
set-driven-key networks from human-readable JSON pose templates.

Mayaリグに左右のフィンガーコントローラーを配置し、選択したポーズだけを
JSONからSDK（Set Driven Key）として構築するツールです。

## Highlights

- Non-destructive Maya workflow with one-step undo and automatic rollback
- Multi-select pose library with validation before scene edits
- Data-driven JSON poses: add or tune poses without changing Python code
- Idempotent rebuild: tool-managed SDK curves are replaced instead of stacked
- Maya 2022–2026 compatible PySide2/PySide6 UI
- Pure-Python domain layer with automated tests

## Requirements

- Autodesk Maya 2022 or newer
- A rig using `L_` / `R_` joint prefixes
- Wrist joints named `L_wrist_skn_jnt` and `R_wrist_skn_jnt`
- Finger joints matching the names in `templates/*.json`

The supplied templates target the Diana rig naming convention, for example
`L_index1_jnt`, `R_pinky3_jnt`, and `L_thumb_palm_jnt`.

## Installation

Copy this repository as:

```text
Documents/
└─ maya/
   └─ scripts/
      └─ Finger-SDK-Tool/
         ├─ main.py
         ├─ builder.py
         ├─ core.py
         ├─ resources/
         └─ templates/
```

Do not place it under a version- or locale-specific folder such as
`maya/2026/ja_JP/scripts`.

Create a **Python** shelf button and paste the contents of `launch.py`.

## Usage

1. Open a compatible character rig in Maya.
2. Launch the tool from the shelf.
3. Select one or more poses with Ctrl/Shift.
4. Review the attribute, driver value, and joint count.
5. Click **BUILD SDK** and confirm.

The tool creates `L_fingers_anim` and `R_fingers_anim` when needed. Rebuilding
replaces SDK networks owned by the selected attributes. User-defined attributes
on these generated controllers that are not represented by the current
selection are removed.

## Pose schema

```json
{
  "pose_name": "fist",
  "driver_attr": "fist",
  "driver_value": 10,
  "joints": {
    "index1_jnt": {
      "rotateX": 0,
      "rotateY": 0,
      "rotateZ": -75
    }
  }
}
```

Only `rotateX`, `rotateY`, and `rotateZ` are accepted. Joint keys may omit the
side prefix; the tool resolves them independently for `L` and `R`.

## Development

The core tests run without Maya:

```powershell
python -m unittest discover -s tests -v
```

For Maya integration testing, use a disposable copy of the target rig and
verify controller placement, both sides, a repeated build, and a single Undo.

## Architecture

```text
main.py          Qt UI, user confirmation, progress, rollback
builder.py       Maya scene operations and SDK construction
core.py          JSON validation and joint-name resolution
templates/       Versionable pose data
resources/       Maya controller asset
tests/           Maya-independent regression tests
```

## License

[MIT](LICENSE)
