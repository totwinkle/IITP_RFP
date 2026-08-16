import io
import json
import zipfile
from pathlib import Path


def make_hwpx(path: Path, text: str = "fixture", compatibility: bool = True) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("Contents/content.hpf", "<package />")
        archive.writestr("Contents/header.xml", "<header />")
        archive.writestr("Contents/section0.xml", f"<section><text>{text}</text></section>")
        if compatibility:
            archive.writestr("META-INF/manifest.xml", "<manifest />")
            archive.writestr("settings.xml", "<settings />")
            archive.writestr("version.xml", "<version />")


class FakeKordoc:
    def __init__(self, markdown=None):
        self.markdown = markdown or (
            "# 해양 미세플라스틱 회수 기술 수요조사서\n\n"
            "| 항목 | 내용 |\n| --- | --- |\n"
            "| 수요명 | 해양 미세플라스틱 회수 플랫폼 |\n"
            "| 기술분야 | 환경·해양 |\n"
            "| 개발목표 | 연안의 미세플라스틱을 탐지하고 회수하는 기술 개발 |\n"
            "| 개발내용 | 센서 융합 탐지 기술 개발<br>자율 회수 모듈 개발 |\n"
            "| 지원 필요성/기대효과 | 해양 오염 저감 기반 확보 |\n"
        )

    def parse(self, source, markdown_output, json_output=None):
        markdown_output.write_text(self.markdown, encoding="utf-8")
        if json_output:
            json_output.write_text(json.dumps({"success": True, "markdown": self.markdown}), encoding="utf-8")
        return {"command": ["fake", "parse"], "ok": True, "stdout": ""}

    def generate_and_verify(self, markdown_path, hwpx_path, roundtrip_path, render_path, preset, compatibility_source=None):
        make_hwpx(hwpx_path, markdown_path.read_text(encoding="utf-8"))
        roundtrip_path.write_text(markdown_path.read_text(encoding="utf-8"), encoding="utf-8")
        render_path.write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>", encoding="utf-8")
        return {
            "completed": True,
            "preset": preset,
            "kordoc_validate": {"ok": True},
            "roundtrip": {"ok": True},
            "render": {"ok": True},
            "zip": {"ok": True, "missing": [], "bad_entry": None},
            "compatibility": {"applied": False, "status": "already_present", "copied_entries": []},
            "roundtrip_required_sections": {"ok": True, "missing": []},
            "warnings": [],
        }


class IncompleteFakeKordoc(FakeKordoc):
    def generate_and_verify(self, markdown_path, hwpx_path, roundtrip_path, render_path, preset, compatibility_source=None):
        make_hwpx(hwpx_path, markdown_path.read_text(encoding="utf-8"), compatibility=False)
        roundtrip_path.write_text(markdown_path.read_text(encoding="utf-8"), encoding="utf-8")
        render_path.write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>", encoding="utf-8")
        return {
            "completed": False,
            "preset": preset,
            "kordoc_validate": {"ok": True},
            "roundtrip": {"ok": True},
            "render": {"ok": True},
            "zip": {
                "ok": True,
                "compatibility_ok": False,
                "missing": [],
                "missing_compatibility": ["settings.xml", "version.xml", "META-INF/manifest.xml"],
                "bad_entry": None,
            },
            "compatibility": {"applied": False, "status": "source_unavailable", "copied_entries": []},
            "roundtrip_required_sections": {"ok": True, "missing": []},
            "warnings": ["known-good HWPX unavailable"],
        }


def wsgi_json(app, method, path, payload=None):
    body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": "application/json",
        "wsgi.input": io.BytesIO(body),
        "wsgi.url_scheme": "http",
        "SERVER_NAME": "test",
        "SERVER_PORT": "80",
    }
    captured = {}

    def start_response(status, headers):
        captured["status"] = int(status.split()[0])
        captured["headers"] = dict(headers)

    response_body = b"".join(app(environ, start_response))
    return captured["status"], json.loads(response_body.decode("utf-8"))
