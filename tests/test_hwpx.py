import tempfile
import unittest
import zipfile
from pathlib import Path

from iitp_app.kordoc import COMPATIBILITY_ENTRIES, KordocCLI, inspect_hwpx_zip, repair_compatibility_entries
from tests.helpers import make_hwpx


class HwpxZipTests(unittest.TestCase):
    def test_valid_hwpx_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "valid.hwpx"
            make_hwpx(path)
            result = inspect_hwpx_zip(path)
            self.assertTrue(result["ok"])
            self.assertEqual(result["mimetype"], "application/hwp+zip")

    def test_missing_required_entry_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.hwpx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("mimetype", "application/hwp+zip")
            result = inspect_hwpx_zip(path)
            self.assertFalse(result["ok"])
            self.assertIn("Contents/section0.xml", result["missing"])

    def test_repair_copies_only_compatibility_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "generated.hwpx"
            source = Path(tmp) / "known-good.hwpx"
            make_hwpx(target, text="generated-content", compatibility=False)
            make_hwpx(source, text="donor-content", compatibility=True)
            with zipfile.ZipFile(target) as archive:
                generated_content = archive.read("Contents/section0.xml")

            repair = repair_compatibility_entries(target, source)
            result = inspect_hwpx_zip(target)

            self.assertTrue(repair["applied"])
            self.assertCountEqual(repair["copied_entries"], COMPATIBILITY_ENTRIES)
            self.assertTrue(result["compatibility_ok"])
            with zipfile.ZipFile(target) as archive:
                self.assertEqual(archive.read("Contents/section0.xml"), generated_content)
                self.assertNotIn(b"donor-content", archive.read("Contents/section0.xml"))

    def test_generate_is_incomplete_without_compatibility_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            markdown = root / "input.md"
            output = root / "output.hwpx"
            roundtrip = root / "roundtrip.md"
            render = root / "render.svg"
            markdown.write_text("# 문서\n\n본문", encoding="utf-8")

            class StubKordoc(KordocCLI):
                def __init__(self):
                    super().__init__(command=["stub"])
                    self.calls = []

                def _run(self, args):
                    self.calls.append(args)
                    if args[0] == "generate":
                        make_hwpx(output, compatibility=False)
                    elif args[0] == "render":
                        render.write_text("<svg/>", encoding="utf-8")
                    elif args[0] != "validate":
                        roundtrip.write_text(markdown.read_text(encoding="utf-8"), encoding="utf-8")
                    return {"command": ["stub", *args], "ok": True, "exit_code": 0, "stdout": "", "stderr": ""}

            adapter = StubKordoc()
            result = adapter.generate_and_verify(markdown, output, roundtrip, render, "report")

            self.assertFalse(result["completed"])
            self.assertEqual(result["compatibility"]["status"], "source_unavailable")
            self.assertFalse(result["zip"]["compatibility_ok"])
            self.assertEqual([call[0] for call in adapter.calls], ["generate", "validate", str(output), "render"])


    def test_default_command_prefers_bundled_runtime(self):
        root = Path(__file__).resolve().parents[1]
        bundled_archive = root / "api" / "kordoc-runtime.tar.xz"
        if bundled_archive.is_file():
            adapter = KordocCLI()
            self.assertEqual(Path(adapter.command[0]).name, "node")
            self.assertTrue(Path(adapter.command[0]).is_file())
            self.assertTrue(Path(adapter.command[1]).is_file())


if __name__ == "__main__":
    unittest.main()
