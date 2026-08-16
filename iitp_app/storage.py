from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_filename(name: str) -> str:
    base = Path(name).name
    safe = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", base).strip("._")
    return safe or "input.hwpx"


class ProjectStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, filename: str, content: bytes) -> tuple[dict, Path]:
        project_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(4)
        project_dir = self.root / project_id
        (project_dir / "source").mkdir(parents=True)
        (project_dir / "artifacts").mkdir()
        source = project_dir / "source" / safe_filename(filename)
        source.write_bytes(content)
        project = {
            "id": project_id,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "stage": "upload",
            "decisions": {},
            "evidence": [],
            "analysis": None,
            "planning_markdown": None,
            "rfp_markdown": None,
            "planning_validation": None,
            "rfp_validation": None,
            "manifest": {
                "schema_version": 1,
                "project_id": project_id,
                "inputs": [{
                    "role": "source_demand_hwpx",
                    "original_filename": filename,
                    "stored_path": str(source.resolve()),
                    "size": source.stat().st_size,
                    "sha256": sha256(source),
                    "received_at": utc_now(),
                    "authoritative": True,
                }],
                "sources": [],
                "decisions": [],
                "outputs": [],
                "commands": [],
                "warnings": [],
            },
        }
        self.save(project)
        return project, source

    def directory(self, project_id: str) -> Path:
        if not re.fullmatch(r"[0-9]{14}-[0-9a-f]{8}", project_id):
            raise KeyError(project_id)
        path = self.root / project_id
        if not path.is_dir():
            raise KeyError(project_id)
        return path

    def load(self, project_id: str) -> dict:
        path = self.directory(project_id) / "project.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, project: dict) -> None:
        project["updated_at"] = utc_now()
        path = self.root / project["id"] / "project.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def source_path(self, project: dict) -> Path:
        return Path(project["manifest"]["inputs"][0]["stored_path"])

    def artifact_path(self, project_id: str, name: str) -> Path:
        return self.directory(project_id) / "artifacts" / safe_filename(name)

    def list_projects(self) -> list[dict]:
        results = []
        for path in sorted(self.root.glob("*/project.json"), reverse=True):
            try:
                project = json.loads(path.read_text(encoding="utf-8"))
                results.append({key: project.get(key) for key in ("id", "created_at", "updated_at", "stage")})
                results[-1]["title"] = (project.get("analysis") or {}).get("fields", {}).get("title", {}).get("value")
            except (OSError, json.JSONDecodeError):
                continue
        return results

