"""Maya shelf entry point for Finger SDK Tool."""

from pathlib import Path
import importlib.util
import sys

import maya.cmds as cmds


tool_root = Path(cmds.internalVar(userAppDir=True)) / "scripts" / "Finger-SDK-Tool"
main_file = tool_root / "main.py"

if not main_file.is_file():
    cmds.error(
        "Finger SDK Tool was not found:\n{}\n\n"
        "Install the Finger-SDK-Tool folder directly under:\n{}".format(
            main_file, tool_root.parent
        )
    )

module_name = "_finger_sdk_tool_main"
sys.modules.pop(module_name, None)
spec = importlib.util.spec_from_file_location(module_name, str(main_file))
if spec is None or spec.loader is None:
    cmds.error("Could not load: {}".format(main_file))

module = importlib.util.module_from_spec(spec)
sys.modules[module_name] = module
spec.loader.exec_module(module)
module.show()
