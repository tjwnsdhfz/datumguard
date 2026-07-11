# ruff: noqa: UP020, UP031
"""Rhino 8 Python driver used only by ``rhino_step_smoke.py``.

Inputs are passed through fixed environment variables so no arbitrary command is
constructed. Rhino 8 performs code-driven file I/O in a headless document.
"""

import io
import json
import os
import traceback

import Rhino


def main():
    request_path = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__), os.pardir, "cad_smoke_outputs", "rhino-smoke-request.json"
        )
    )
    request = {}
    if os.path.isfile(request_path):
        with io.open(request_path, encoding="utf-8") as stream:
            request = json.load(stream)
    step_path = os.environ.get("DATUMGUARD_RHINO_STEP_INPUT") or request["step_path"]
    three_dm_path = os.environ.get("DATUMGUARD_RHINO_3DM_OUTPUT") or request["three_dm_path"]
    evidence_path = os.environ.get("DATUMGUARD_RHINO_EVIDENCE_OUTPUT") or request["evidence_path"]
    evidence = {
        "status": "failed",
        "step_path": step_path,
        "three_dm_path": three_dm_path,
    }
    document = None
    try:
        document = Rhino.RhinoDoc.CreateHeadless(None)
        imported = bool(document.Import(step_path))
        objects = list(document.Objects)
        if not imported or not objects:
            raise RuntimeError("Rhino headless STEP import returned no geometry")

        minimum = [float("inf"), float("inf"), float("inf")]
        maximum = [float("-inf"), float("-inf"), float("-inf")]
        object_types = {}
        for item in objects:
            geometry = item.Geometry
            box = geometry.GetBoundingBox(True)
            for index, value in enumerate((box.Min.X, box.Min.Y, box.Min.Z)):
                minimum[index] = min(minimum[index], float(value))
            for index, value in enumerate((box.Max.X, box.Max.Y, box.Max.Z)):
                maximum[index] = max(maximum[index], float(value))
            name = geometry.GetType().Name
            object_types[name] = object_types.get(name, 0) + 1

        options = Rhino.FileIO.FileWriteOptions()
        options.SuppressAllInput = True
        options.SuppressDialogBoxes = True
        options.IncludeRenderMeshes = True
        options.WriteGeometryOnly = False
        written = bool(document.Write3dmFile(three_dm_path, options))
        if not written:
            raise RuntimeError("Rhino could not write the imported geometry as 3DM")
        evidence.update(
            {
                "status": "passed",
                "rhino_version": "%s.%s"
                % (Rhino.RhinoApp.ExeVersion, Rhino.RhinoApp.ExeServiceRelease),
                "object_count": len(objects),
                "object_types": object_types,
                "model_unit_system": str(document.ModelUnitSystem),
                "bounding_box": {
                    "minimum": minimum,
                    "maximum": maximum,
                    "size": [maximum[index] - minimum[index] for index in range(3)],
                },
            }
        )
    except Exception as exc:
        evidence.update(
            {
                "exception": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
    finally:
        if document is not None:
            document.Dispose()
        with io.open(evidence_path, "w", encoding="utf-8") as stream:
            json.dump(evidence, stream, ensure_ascii=False, indent=2, sort_keys=True)
        exit_setting = os.environ.get("DATUMGUARD_RHINO_EXIT")
        if exit_setting is None:
            exit_setting = str(request.get("exit_rhino", True))
        if exit_setting.lower() == "true":
            Rhino.RhinoApp.Exit(False)


main()
