from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import os
import traceback
from pathlib import Path
from urllib.parse import unquote
from wsgiref.simple_server import make_server

from .kordoc import KordocCLI, KordocError, inspect_hwpx_zip
from .pipeline import analyze_markdown, compose_planning, compose_rfp
from .storage import ProjectStore, sha256, utc_now


MAX_UPLOAD_BYTES = 50 * 1024 * 1024
STATIC_DIR = Path(__file__).parent / "static"


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


class IITPApplication:
    def __init__(self, data_root: Path, kordoc=None):
        self.store = ProjectStore(data_root)
        self.kordoc = kordoc or KordocCLI()

    def __call__(self, environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = unquote(environ.get("PATH_INFO", "/"))
        try:
            if path.startswith("/api/"):
                return self._api(environ, start_response, method, path)
            return self._static(start_response, path)
        except ApiError as exc:
            return json_response(start_response, exc.status, {"error": exc.message})
        except KordocError as exc:
            return json_response(start_response, 502, {"error": str(exc), "kind": "kordoc_error"})
        except Exception as exc:
            if os.environ.get("IITP_DEBUG") == "1":
                traceback.print_exc()
            return json_response(start_response, 500, {"error": str(exc), "kind": "internal_error"})

    def _api(self, environ, start_response, method: str, path: str):
        parts = [part for part in path.split("/") if part]
        if parts == ["api", "health"] and method == "GET":
            return json_response(start_response, 200, {"ok": True, "service": "iitp-document-generator"})
        if parts == ["api", "projects"]:
            if method == "GET":
                return json_response(start_response, 200, {"projects": self.store.list_projects()})
            if method == "POST":
                return self._create_project(start_response, read_json(environ))
        if len(parts) < 3 or parts[:2] != ["api", "projects"]:
            raise ApiError(404, "API endpoint not found")
        project_id = parts[2]
        try:
            project = self.store.load(project_id)
        except KeyError:
            raise ApiError(404, "Project not found")
        suffix = parts[3:]
        if not suffix and method == "GET":
            return json_response(start_response, 200, public_project(project))
        if suffix == ["review"] and method == "PATCH":
            return self._update_review(start_response, project, read_json(environ))
        if suffix == ["planning"]:
            if method == "POST":
                project["planning_markdown"] = compose_planning(project["analysis"], project["decisions"], project["evidence"])
                project["stage"] = "planning_review"
                self._write_markdown(project, "planning")
                self.store.save(project)
                return json_response(start_response, 200, public_project(project))
            if method == "PUT":
                project["planning_markdown"] = require_markdown(read_json(environ))
                project["stage"] = "planning_review"
                self._write_markdown(project, "planning")
                self.store.save(project)
                return json_response(start_response, 200, public_project(project))
        if suffix == ["planning", "confirm"] and method == "POST":
            return self._confirm(start_response, project, "planning", "report")
        if suffix == ["rfp"]:
            if method == "POST":
                if project["stage"] not in {"planning_confirmed", "rfp_review", "complete"}:
                    raise ApiError(409, "Planning report must be confirmed before RFP generation")
                project["rfp_markdown"] = compose_rfp(project["planning_markdown"], project["analysis"], project["decisions"])
                project["stage"] = "rfp_review"
                self._write_markdown(project, "rfp")
                self.store.save(project)
                return json_response(start_response, 200, public_project(project))
            if method == "PUT":
                project["rfp_markdown"] = require_markdown(read_json(environ))
                project["stage"] = "rfp_review"
                self._write_markdown(project, "rfp")
                self.store.save(project)
                return json_response(start_response, 200, public_project(project))
        if suffix == ["rfp", "confirm"] and method == "POST":
            if project["stage"] not in {"rfp_review", "complete"}:
                raise ApiError(409, "RFP draft must be generated before confirmation")
            return self._confirm(start_response, project, "rfp", "gaejosik")
        if len(suffix) == 2 and suffix[0] in {"download", "render", "roundtrip", "manifest"} and method == "GET":
            return self._artifact(start_response, project, suffix)
        raise ApiError(404, "API endpoint not found")

    def _create_project(self, start_response, payload: dict):
        filename = str(payload.get("filename", ""))
        encoded = payload.get("content_base64")
        if not filename.lower().endswith(".hwpx"):
            raise ApiError(400, "Only .hwpx files are accepted")
        if not encoded:
            raise ApiError(400, "content_base64 is required")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            raise ApiError(400, "Invalid base64 upload")
        if not content or len(content) > MAX_UPLOAD_BYTES:
            raise ApiError(413, "Upload must be between 1 byte and 50 MiB")
        project, source = self.store.create(filename, content)
        zip_check = inspect_hwpx_zip(source)
        if not zip_check["ok"]:
            raise ApiError(400, "Invalid HWPX ZIP: " + ", ".join(zip_check.get("missing", [])))
        project_dir = self.store.directory(project["id"])
        source_md = project_dir / "source" / "source.md"
        source_json = project_dir / "source" / "source.json"
        parse_result = self.kordoc.parse(source, source_md, source_json)
        markdown = source_md.read_text(encoding="utf-8")
        project["analysis"] = analyze_markdown(markdown)
        project["stage"] = "analysis"
        project["manifest"]["inputs"][0]["zip_validation"] = zip_check
        project["manifest"]["inputs"][0]["parsed_markdown"] = str(source_md.resolve())
        project["manifest"]["commands"].append(safe_command_record("parse", parse_result))
        project["manifest"]["warnings"].extend(project["analysis"]["warnings"])
        self.store.save(project)
        return json_response(start_response, 201, public_project(project))

    def _update_review(self, start_response, project: dict, payload: dict):
        decisions = payload.get("decisions", {})
        evidence = payload.get("evidence", [])
        if not isinstance(decisions, dict) or not isinstance(evidence, list):
            raise ApiError(400, "decisions must be an object and evidence must be a list")
        project["decisions"] = {str(key): str(value).strip() for key, value in decisions.items() if str(value).strip()}
        project["evidence"] = [normalize_evidence(item) for item in evidence if isinstance(item, dict)]
        project["manifest"]["decisions"] = [
            {"key": key, "value": value, "source": "owner_decision", "recorded_at": utc_now()}
            for key, value in project["decisions"].items()
        ]
        project["manifest"]["sources"] = project["evidence"]
        self.store.save(project)
        return json_response(start_response, 200, public_project(project))

    def _write_markdown(self, project: dict, kind: str) -> Path:
        path = self.store.artifact_path(project["id"], f"{kind}.md")
        path.write_text(project[f"{kind}_markdown"], encoding="utf-8")
        return path

    def _confirm(self, start_response, project: dict, kind: str, preset: str):
        markdown = project.get(f"{kind}_markdown")
        if not markdown:
            raise ApiError(409, f"{kind} draft has not been generated")
        md_path = self._write_markdown(project, kind)
        hwpx_path = self.store.artifact_path(project["id"], f"{kind}.hwpx")
        roundtrip_path = self.store.artifact_path(project["id"], f"{kind}.roundtrip.md")
        render_path = self.store.artifact_path(project["id"], f"{kind}.svg")
        validation = self.kordoc.generate_and_verify(
            md_path,
            hwpx_path,
            roundtrip_path,
            render_path,
            preset,
            compatibility_source=self.store.source_path(project),
        )
        project[f"{kind}_validation"] = validation
        if not validation.get("completed"):
            project["stage"] = "planning_review" if kind == "planning" else "rfp_review"
            role = "technical_planning_report" if kind == "planning" else "rfp"
            project["manifest"]["outputs"] = [
                item for item in project["manifest"]["outputs"] if item["role"] != role
            ]
            self.store.save(project)
            return json_response(start_response, 422, {
                "error": f"{kind} validation gate failed",
                "validation": validation,
                "project": public_project(project),
            })
        project["stage"] = "planning_confirmed" if kind == "planning" else "complete"
        output = {
            "role": "technical_planning_report" if kind == "planning" else "rfp",
            "markdown_path": str(md_path.resolve()),
            "hwpx_path": str(hwpx_path.resolve()),
            "roundtrip_path": str(roundtrip_path.resolve()),
            "render_path": str(render_path.resolve()),
            "sha256": sha256(hwpx_path),
            "size": hwpx_path.stat().st_size,
            "confirmed_at": utc_now(),
            "validation_completed": True,
        }
        project["manifest"]["outputs"] = [item for item in project["manifest"]["outputs"] if item["role"] != output["role"]]
        project["manifest"]["outputs"].append(output)
        project["manifest"]["commands"].append({"operation": f"generate_verify_{kind}", "preset": preset, "recorded_at": utc_now()})
        self.store.save(project)
        response = public_project(project).copy()
        response["validation"] = validation
        return json_response(start_response, 200, response)

    def _artifact(self, start_response, project: dict, suffix: list[str]):
        category, kind = suffix
        if category == "manifest":
            if kind != "provenance":
                raise ApiError(404, "Manifest not found")
            return json_response(start_response, 200, project["manifest"])
        if kind not in {"planning", "rfp"}:
            raise ApiError(404, "Artifact not found")
        validation = project.get(f"{kind}_validation") or {}
        if not validation.get("completed"):
            raise ApiError(409, "Artifact is not confirmed and validated")
        extension = {"download": "hwpx", "render": "svg", "roundtrip": "roundtrip.md"}[category]
        path = self.store.artifact_path(project["id"], f"{kind}.{extension}")
        if not path.exists():
            raise ApiError(404, "Artifact not found")
        content_type = {
            "hwpx": "application/hwp+zip",
            "svg": "image/svg+xml; charset=utf-8",
            "roundtrip.md": "text/markdown; charset=utf-8",
        }[extension]
        headers = [("Content-Type", content_type), ("Content-Length", str(path.stat().st_size))]
        if category == "download":
            headers.append(("Content-Disposition", f'attachment; filename="{kind}.hwpx"'))
        start_response("200 OK", headers)
        return [path.read_bytes()]

    def _static(self, start_response, path: str):
        name = "index.html" if path in {"", "/"} else path.lstrip("/")
        requested = (STATIC_DIR / name).resolve()
        if STATIC_DIR.resolve() not in requested.parents and requested != STATIC_DIR.resolve():
            raise ApiError(404, "Not found")
        if not requested.is_file():
            requested = STATIC_DIR / "index.html"
        data = requested.read_bytes()
        content_type = mimetypes.guess_type(requested.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        start_response("200 OK", [("Content-Type", content_type), ("Content-Length", str(len(data)))])
        return [data]


def normalize_evidence(item: dict) -> dict:
    status = "verified" if item.get("status") == "verified" and item.get("url") else "unverified"
    return {
        "source_id": str(item.get("source_id") or f"SRC-{abs(hash(str(item))) % 10000:04d}"),
        "organization": str(item.get("organization", "")).strip(),
        "title": str(item.get("title", "")).strip(),
        "date": str(item.get("date", "")).strip(),
        "url": str(item.get("url", "")).strip(),
        "claim": str(item.get("claim", "")).strip(),
        "status": status,
        "role": "source_evidence",
    }


def safe_command_record(operation: str, result: dict) -> dict:
    return {
        "operation": operation,
        "ok": bool(result.get("ok")),
        "command": [str(item) for item in result.get("command", [])],
        "recorded_at": utc_now(),
    }


def require_markdown(payload: dict) -> str:
    markdown = payload.get("markdown")
    if not isinstance(markdown, str) or len(markdown.strip()) < 20:
        raise ApiError(400, "markdown must be a non-empty string")
    return markdown


def read_json(environ) -> dict:
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        raise ApiError(400, "Invalid Content-Length")
    if length > MAX_UPLOAD_BYTES * 2:
        raise ApiError(413, "Request too large")
    raw = environ["wsgi.input"].read(length) if length else b"{}"
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ApiError(400, "Invalid JSON body")
    if not isinstance(payload, dict):
        raise ApiError(400, "JSON body must be an object")
    return payload


def public_project(project: dict) -> dict:
    return project


def json_response(start_response, status: int, payload: dict):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    phrase = {200: "OK", 201: "Created", 400: "Bad Request", 404: "Not Found", 409: "Conflict", 413: "Payload Too Large", 422: "Unprocessable Entity", 500: "Internal Server Error", 502: "Bad Gateway"}.get(status, "OK")
    start_response(f"{status} {phrase}", [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(data)))])
    return [data]


def create_app(data_root: Path | None = None, kordoc=None):
    root = data_root or Path(os.environ.get("IITP_DATA_DIR", "./data"))
    return IITPApplication(root, kordoc=kordoc)


def main():
    host = os.environ.get("IITP_HOST", "127.0.0.1")
    port = int(os.environ.get("IITP_PORT", "8080"))
    app = create_app()
    print(f"IITP Document Studio: http://{host}:{port}")
    print(f"Local data: {app.store.root}")
    with make_server(host, port, app) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
