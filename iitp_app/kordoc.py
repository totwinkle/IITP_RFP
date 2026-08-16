from __future__ import annotations

import json
import os
import subprocess
import tarfile
import tempfile
import zipfile
from copy import copy
from pathlib import Path
from typing import Iterable


MIMETYPE = "application/hwp+zip"
REQUIRED_ENTRIES = (
    "mimetype",
    "Contents/content.hpf",
    "Contents/header.xml",
    "Contents/section0.xml",
)
COMPATIBILITY_ENTRIES = ("settings.xml", "version.xml", "META-INF/manifest.xml")


def inspect_hwpx_zip(path: Path) -> dict:
    result = {
        "ok": False,
        "path": str(path.resolve()),
        "mimetype": None,
        "entries": 0,
        "missing": [],
        "missing_compatibility": [],
        "bad_entry": None,
    }
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            result["entries"] = len(names)
            result["bad_entry"] = archive.testzip()
            result["missing"] = [item for item in REQUIRED_ENTRIES if item not in names]
            result["missing_compatibility"] = [item for item in COMPATIBILITY_ENTRIES if item not in names]
            if "mimetype" in names:
                result["mimetype"] = archive.read("mimetype").decode("ascii", errors="replace").strip()
            first_entry_ok = bool(names) and names[0] == "mimetype"
            mimetype_stored = (
                "mimetype" in names and archive.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
            )
            result["mimetype_first_and_stored"] = first_entry_ok and mimetype_stored
            result["ok"] = not result["missing"] and result["bad_entry"] is None and result["mimetype"] == MIMETYPE
            result["compatibility_ok"] = not result["missing_compatibility"]
    except (OSError, zipfile.BadZipFile) as exc:
        result["error"] = str(exc)
    return result


class KordocError(RuntimeError):
    pass


class KordocCLI:
    def __init__(
        self,
        command: Iterable[str] | None = None,
        timeout: int = 180,
        compatibility_source: Path | str | None = None,
    ):
        env_command = os.environ.get("KORDOC_COMMAND")
        runtime_dir = Path(__file__).resolve().parents[1] / "api"
        bundled_archive = runtime_dir / "kordoc-runtime.tar.xz"
        cache_dir = Path(tempfile.gettempdir()) / "iitp-kordoc-runtime"
        bundled_node = cache_dir / "node"
        bundled_cli = cache_dir / "node_modules" / "kordoc" / "dist" / "cli.js"
        if bundled_archive.is_file() and not (bundled_node.is_file() and bundled_cli.is_file()):
            temporary_dir = cache_dir.with_name(cache_dir.name + ".tmp")
            if temporary_dir.exists():
                import shutil
                shutil.rmtree(temporary_dir)
            temporary_dir.mkdir(parents=True)
            with tarfile.open(bundled_archive, mode="r:xz") as archive:
                archive.extractall(temporary_dir, filter="data")
            (temporary_dir / "node").chmod(0o755)
            if cache_dir.exists():
                import shutil
                shutil.rmtree(cache_dir)
            temporary_dir.replace(cache_dir)
        if command:
            default_command = list(command)
        elif env_command:
            default_command = env_command.split()
        elif bundled_node.is_file() and bundled_cli.is_file():
            default_command = [str(bundled_node), str(bundled_cli)]
        else:
            default_command = [
                "npx", "--yes", "--package", "kordoc", "--package", "pdfjs-dist", "kordoc"
            ]
        self.command = default_command
        self.timeout = timeout
        configured_source = compatibility_source or os.environ.get("IITP_HWPX_COMPATIBILITY_SOURCE")
        self.compatibility_source = Path(configured_source).expanduser() if configured_source else None

    def _run(self, args: list[str]) -> dict:
        command = self.command + args
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise KordocError(f"Kordoc 실행 실패: {exc}") from exc
        result = {
            "command": command,
            "ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-8000:],
            "stderr": completed.stderr[-8000:],
        }
        if not result["ok"]:
            raise KordocError(result["stderr"] or result["stdout"] or "Kordoc 명령 실패")
        return result

    def parse(self, source: Path, markdown_output: Path, json_output: Path | None = None) -> dict:
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        md_result = self._run([str(source), "-o", str(markdown_output), "--silent"])
        if json_output:
            json_result = self._run([str(source), "--format", "json", "--silent"])
            raw = json_result["stdout"].strip()
            try:
                parsed = json.loads(raw)
                json_output.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
            except json.JSONDecodeError:
                json_output.write_text(json.dumps({"success": False, "raw": raw}, ensure_ascii=False, indent=2), encoding="utf-8")
            md_result["json_command"] = json_result["command"]
        return md_result

    def generate_and_verify(
        self,
        markdown_path: Path,
        hwpx_path: Path,
        roundtrip_path: Path,
        render_path: Path,
        preset: str,
        compatibility_source: Path | str | None = None,
    ) -> dict:
        hwpx_path.parent.mkdir(parents=True, exist_ok=True)
        generate_args = [
            "generate", str(markdown_path), "-o", str(hwpx_path), "--preset", preset,
            "--font", "myeongjo", "--pt", "11", "--line-spacing", "160", "--bullet2", "ㅇ", "--silent",
        ]
        if preset == "gaejosik":
            generate_args += ["--no-toc", "--no-cover", "--no-page-numbers", "--h2-marker", "number"]
        generate = self._run(generate_args)
        generated_zip = inspect_hwpx_zip(hwpx_path)
        source = self._select_compatibility_source(compatibility_source)
        compatibility = repair_compatibility_entries(hwpx_path, source)
        zip_result = inspect_hwpx_zip(hwpx_path)
        validate = self._run(["validate", str(hwpx_path)])
        roundtrip = self._run([str(hwpx_path), "-o", str(roundtrip_path), "--silent"])
        render = self._run(["render", str(hwpx_path), "-o", str(render_path), "--silent"])
        expected = _required_sections(markdown_path.read_text(encoding="utf-8"), preset)
        roundtrip_text = roundtrip_path.read_text(encoding="utf-8") if roundtrip_path.exists() else ""
        roundtrip_headings = {
            _heading_semantic(line.lstrip("# "))
            for line in roundtrip_text.splitlines()
            if line.startswith("#")
        }
        missing_sections = [heading for heading in expected if _heading_semantic(heading) not in roundtrip_headings]
        warnings = []
        if zip_result["missing_compatibility"]:
            warnings.append("한컴 호환성 메타데이터를 보강할 known-good HWPX가 없습니다: " + ", ".join(zip_result["missing_compatibility"]))
        if not zip_result.get("mimetype_first_and_stored"):
            warnings.append("mimetype 엔트리가 ZIP 첫 항목/비압축 조건을 충족하지 않습니다.")
        if missing_sections:
            warnings.append("왕복 변환에서 필수 제목이 누락되었습니다: " + ", ".join(missing_sections))
        completed = bool(
            zip_result["ok"]
            and zip_result["compatibility_ok"]
            and validate["ok"]
            and roundtrip["ok"]
            and render["ok"]
            and not missing_sections
        )
        return {
            "completed": completed,
            "preset": preset,
            "generate": generate,
            "generated_zip": generated_zip,
            "compatibility": compatibility,
            "kordoc_validate": validate,
            "roundtrip": roundtrip,
            "render": render,
            "zip": zip_result,
            "roundtrip_required_sections": {"ok": not missing_sections, "missing": missing_sections},
            "template_fidelity": "generic_structure_only",
            "warnings": warnings,
        }

    def _select_compatibility_source(self, compatibility_source: Path | str | None) -> Path | None:
        candidates = []
        if compatibility_source:
            candidates.append(Path(compatibility_source).expanduser())
        if self.compatibility_source and self.compatibility_source not in candidates:
            candidates.append(self.compatibility_source)
        for candidate in candidates:
            inspection = inspect_hwpx_zip(candidate)
            if inspection.get("ok") and inspection.get("compatibility_ok"):
                return candidate
        return None


def repair_compatibility_entries(target: Path, source: Path | None) -> dict:
    """Append only Hancom package metadata from a validated known-good HWPX."""
    before = inspect_hwpx_zip(target)
    missing = list(before.get("missing_compatibility", COMPATIBILITY_ENTRIES))
    result = {
        "required_entries": list(COMPATIBILITY_ENTRIES),
        "missing_before": missing,
        "copied_entries": [],
        "source_path": str(source.resolve()) if source else None,
        "applied": False,
    }
    if not missing:
        result["status"] = "already_present"
        return result
    if source is None:
        result["status"] = "source_unavailable"
        return result

    source_check = inspect_hwpx_zip(source)
    if not source_check.get("ok") or not source_check.get("compatibility_ok"):
        result["status"] = "source_invalid"
        return result

    with zipfile.ZipFile(source) as donor, zipfile.ZipFile(target, "a") as output:
        for name in missing:
            donor_info = donor.getinfo(name)
            metadata = copy(donor_info)
            metadata.filename = name
            output.writestr(metadata, donor.read(name))
            result["copied_entries"].append(name)
    result["applied"] = bool(result["copied_entries"])
    result["status"] = "repaired"
    return result


def _required_sections(markdown: str, preset: str) -> list[str]:
    headings = []
    for line in markdown.splitlines():
        if line.startswith("## "):
            headings.append(line[3:].strip())
    return headings[:5] if preset == "gaejosik" else headings[:8]


def _heading_semantic(heading: str) -> str:
    """Compare semantic headings after Kordoc's preset-specific marker rewrite."""
    import re
    value = heading.strip()
    value = re.sub(r"^[□◈ㅇ○\s]+", "", value)
    value = re.sub(r"^(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|\d+)[.．]\s*", "", value)
    return re.sub(r"\s+", " ", value).strip()
