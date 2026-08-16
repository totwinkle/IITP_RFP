import tempfile
import unittest
from pathlib import Path

from iitp_app.pipeline import PLACEHOLDER, analyze_markdown, compose_planning, compose_rfp


class PipelineTests(unittest.TestCase):
    def test_parses_demand_fields_and_builds_mapping(self):
        markdown = (
            "# 스마트 농업 수요조사서\n\n"
            "| 항목 | 내용 |\n|---|---|\n"
            "| 수요명 | 저전력 작물 생육 진단 |\n"
            "| 개발목표 | 현장 진단 장치 개발 |\n"
            "| 개발내용 | 센서 개발<br>진단 모델 개발 |\n"
        )
        analysis = analyze_markdown(markdown)
        self.assertEqual(analysis["fields"]["title"]["value"], "저전력 작물 생육 진단")
        self.assertEqual(analysis["fields"]["objective"]["provenance"], "source_input")
        self.assertGreaterEqual(len(analysis["mapping"]), 12)

    def test_unresolved_quantitative_values_are_explicit(self):
        analysis = analyze_markdown("# 산림 재난 대응 기술\n\n## 개발목표\n조기 감지 기술 개발")
        planning = compose_planning(analysis, decisions={}, evidence=[])
        self.assertIn(PLACEHOLDER, planning)
        self.assertIn("정량 KPI", planning)
        self.assertNotIn("TRL 7", planning)

    def test_arbitrary_topic_does_not_leak_sample_content(self):
        analysis = analyze_markdown(
            "# 폐배터리 재활용 기술\n\n## 개발목표\n희소금속 회수 공정 개발\n\n"
            "## 개발내용\nㅇ 저온 분리 공정\nㅇ 회수율 검증"
        )
        planning = compose_planning(analysis, {}, [])
        rfp = compose_rfp(planning, analysis, {})
        forbidden = ["양자내성암호", "PQC", "클라우드 암호", "NIST"]
        for term in forbidden:
            self.assertNotIn(term, planning + rfp)


if __name__ == "__main__":
    unittest.main()

