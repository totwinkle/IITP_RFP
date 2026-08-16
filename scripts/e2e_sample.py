#!/usr/bin/env python3
"""Run the real staged API flow against an HWPX fixture."""

import argparse
import base64
import io
import json
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from iitp_app.kordoc import COMPATIBILITY_ENTRIES, KordocCLI
from iitp_app.server import create_app


def request(app, method: str, path: str, payload=None):
    body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    environ = {
        "REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": "",
        "CONTENT_LENGTH": str(len(body)), "CONTENT_TYPE": "application/json",
        "wsgi.input": io.BytesIO(body), "wsgi.url_scheme": "http",
        "SERVER_NAME": "e2e", "SERVER_PORT": "80",
    }
    result = {}
    def start_response(status, headers):
        result["status"] = int(status.split()[0])
    raw = b"".join(app(environ, start_response))
    data = json.loads(raw.decode("utf-8"))
    if result["status"] >= 400:
        raise RuntimeError(f"{result['status']} {path}: {data}")
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--data-dir", type=Path, default=Path("./e2e-data"))
    parser.add_argument(
        "--compatibility-source",
        type=Path,
        help="Known-good HWPX containing all three Hancom compatibility entries",
    )
    parser.add_argument("--clean", action="store_true", help="Remove the target data directory before running")
    args = parser.parse_args()
    if args.clean and args.data_dir.exists():
        shutil.rmtree(args.data_dir)
    app = create_app(args.data_dir, kordoc=KordocCLI(compatibility_source=args.compatibility_source))
    content = base64.b64encode(args.fixture.read_bytes()).decode("ascii")
    project = request(app, "POST", "/api/projects", {"filename": args.fixture.name, "content_base64": content})
    project_id = project["id"]
    project = request(app, "POST", f"/api/projects/{project_id}/planning")
    project = request(app, "POST", f"/api/projects/{project_id}/planning/confirm")
    project = request(app, "POST", f"/api/projects/{project_id}/rfp")
    project = request(app, "POST", f"/api/projects/{project_id}/rfp/confirm")
    for kind in ("planning", "rfp"):
        validation = project[f"{kind}_validation"]
        if not validation.get("completed") or validation.get("zip", {}).get("missing_compatibility"):
            raise RuntimeError(f"{kind} did not pass the compatibility gate: {validation}")
        artifact = app.store.artifact_path(project_id, f"{kind}.hwpx")
        with zipfile.ZipFile(artifact) as archive:
            missing = [name for name in COMPATIBILITY_ENTRIES if name not in archive.namelist()]
        if missing:
            raise RuntimeError(f"{kind} artifact lacks compatibility entries: {missing}")
    print(json.dumps({
        "project_id": project_id,
        "stage": project["stage"],
        "project_dir": str(app.store.directory(project_id).resolve()),
        "outputs": project["manifest"]["outputs"],
        "planning_validation": project["planning_validation"],
        "rfp_validation": project["rfp_validation"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
