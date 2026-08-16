import base64
import tempfile
import unittest
from pathlib import Path

from iitp_app.server import create_app
from tests.helpers import FakeKordoc, IncompleteFakeKordoc, make_hwpx, wsgi_json


class ApiFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(Path(self.tmp.name), kordoc=FakeKordoc())
        source = Path(self.tmp.name) / "fixture.hwpx"
        make_hwpx(source)
        self.upload = {
            "filename": "arbitrary-demand.hwpx",
            "content_base64": base64.b64encode(source.read_bytes()).decode("ascii"),
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_complete_staged_endpoint_flow(self):
        status, project = wsgi_json(self.app, "POST", "/api/projects", self.upload)
        self.assertEqual(status, 201)
        project_id = project["id"]
        self.assertEqual(project["stage"], "analysis")

        status, planning = wsgi_json(self.app, "POST", f"/api/projects/{project_id}/planning", {})
        self.assertEqual(status, 200)
        self.assertIn("Ⅰ. 개요", planning["planning_markdown"])

        status, blocked = wsgi_json(self.app, "POST", f"/api/projects/{project_id}/rfp", {})
        self.assertEqual(status, 409)
        self.assertIn("confirm", blocked["error"])

        status, confirmed = wsgi_json(self.app, "POST", f"/api/projects/{project_id}/planning/confirm", {})
        self.assertEqual(status, 200)
        self.assertTrue(confirmed["validation"]["completed"])

        status, rfp = wsgi_json(self.app, "POST", f"/api/projects/{project_id}/rfp", {})
        self.assertEqual(status, 200)
        self.assertIn("As-is", rfp["rfp_markdown"])

        status, final = wsgi_json(self.app, "POST", f"/api/projects/{project_id}/rfp/confirm", {})
        self.assertEqual(status, 200)
        self.assertEqual(final["stage"], "complete")
        self.assertEqual(len(final["manifest"]["outputs"]), 2)

    def test_confirmation_stays_incomplete_without_compatibility(self):
        app = create_app(Path(self.tmp.name) / "incomplete", kordoc=IncompleteFakeKordoc())
        status, project = wsgi_json(app, "POST", "/api/projects", self.upload)
        self.assertEqual(status, 201)
        project_id = project["id"]
        status, _ = wsgi_json(app, "POST", f"/api/projects/{project_id}/planning", {})
        self.assertEqual(status, 200)

        status, failed = wsgi_json(app, "POST", f"/api/projects/{project_id}/planning/confirm", {})

        self.assertEqual(status, 422)
        self.assertFalse(failed["validation"]["completed"])
        self.assertEqual(failed["project"]["stage"], "planning_review")
        self.assertFalse(failed["project"]["planning_validation"]["zip"]["compatibility_ok"])
        self.assertEqual(failed["project"]["manifest"]["outputs"], [])


if __name__ == "__main__":
    unittest.main()
