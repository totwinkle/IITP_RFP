# IITP Document Studio

기술수요조사서 HWPX를 직접 파싱하여 기술기획보고서와 RFP를 순차적으로 작성·검토·확정하고, 각 결과를 native HWPX로 내려받는 local-first MVP입니다. 특정 기술 샘플의 내용이나 수치를 내장하지 않습니다. 입력에서 확인되지 않은 TRL, 실증대상, KPI, 예산 배분 등은 `[추가 결정 필요]`로 남깁니다.

## 핵심 흐름

1. **수요 업로드** — HWPX ZIP을 검사하고 Kordoc으로 Markdown/JSON을 추출합니다.
2. **분석·결정** — 원문 필드, 항목별 `직접 근거 / 추가 조사 / 담당자 판단` 매핑, 결정 질문, 외부 근거를 검토합니다.
3. **기술기획보고서** — IITP Ⅰ~Ⅴ장 구조로 초안을 만들고 사용자가 Markdown을 수정합니다. 확정 시에만 Kordoc 생성·검증을 수행합니다.
4. **RFP** — 확정된 기획보고서를 문제·As-is/To-be·필수 요구·검증증적 중심 RFP로 변환합니다. 별도 사용자 확정 후 HWPX를 만듭니다.
5. **다운로드와 감사** — HWPX, 왕복 Markdown, SVG 렌더, provenance manifest를 프로젝트 폴더에 보존합니다.

기획보고서가 확정되기 전에는 RFP API가 `409 Conflict`를 반환합니다. Kordoc validate, HWPX→Markdown 왕복, SVG 렌더, ZIP 필수 구성요소 또는 한컴 호환성 메타데이터 중 하나라도 실패하면 문서는 확정되지 않습니다.

## 아키텍처

```text
Browser (vanilla HTML/CSS/JS)
        │ JSON + base64 HWPX
        ▼
Python standard-library WSGI API
        ├─ ProjectStore       프로젝트별 JSON/파일 원자적 저장
        ├─ Analysis pipeline  필드 추출, ①/②/③ 갭 매핑
        ├─ Composers          일반 기술기획보고서 / RFP Markdown
        └─ KordocCLI          parse → generate → validate → roundtrip → render
                 │
                 ▼
          native HWPX + SVG + audit artifacts
```

- `iitp_app/server.py`: WSGI 서버, 단계 전이, API, 다운로드
- `iitp_app/pipeline.py`: 입력 분석과 template-independent 문서 구성
- `iitp_app/kordoc.py`: Kordoc subprocess 어댑터와 HWPX ZIP 검증
- `iitp_app/storage.py`: manifest, 해시, 프로젝트 저장
- `iitp_app/static/`: 단계형 브라우저 UI
- `tests/`: 파싱, placeholder 안전, 주제 비누출, API 흐름, ZIP 검증
- `scripts/e2e_sample.py`: 실제 Kordoc을 사용하는 endpoint 수준 E2E 실행기

데이터는 기본적으로 `./data/<project-id>/`에만 저장됩니다. 외부 근거는 사용자가 URL과 검증 상태를 등록하며, 앱은 네트워크 조사나 출처 사실 확인을 자동으로 하지 않습니다.

## 요구사항

- Python 3.11 이상(런타임 의존성 없음)
- Node.js 18 이상 및 npm/npx
- Kordoc 실행 시 npm 패키지 다운로드가 필요할 수 있는 네트워크 또는 사전 캐시

Kordoc 명령은 기본적으로 다음 형태로 실행됩니다.

```sh
npx --yes --package kordoc --package pdfjs-dist kordoc
```

폐쇄망이나 로컬 설치를 쓰려면 `KORDOC_COMMAND`를 지정할 수 있습니다.

```sh
export KORDOC_COMMAND="./node_modules/.bin/kordoc"
```

Kordoc 생성본에 호환성 메타데이터가 빠지는 환경에서는 세 항목을 모두 가진 known-good HWPX를 지정합니다. 앱은 이 파일에서 `settings.xml`, `version.xml`, `META-INF/manifest.xml`만 복사하며 본문·스타일 XML은 복사하지 않습니다. 업로드 원본이 세 항목을 모두 가진 경우에는 그 원본을 사용할 수 있고, 그렇지 않으면 환경 설정을 사용합니다.

```sh
export IITP_HWPX_COMPATIBILITY_SOURCE="/absolute/path/to/known-good.hwpx"
```

## 실행

저장소 루트에서:

```sh
python3 -m iitp_app.server
```

브라우저에서 <http://127.0.0.1:8080>을 엽니다. 경로와 포트는 환경변수로 바꿀 수 있습니다.

```sh
IITP_DATA_DIR=/absolute/path/to/projects IITP_HOST=127.0.0.1 IITP_PORT=8090 python3 -m iitp_app.server
```

## 테스트

빠른 전체 테스트는 실제 Kordoc 호출을 fake adapter로 격리하므로 오프라인에서도 실행됩니다.

```sh
python3 -m unittest discover -v
```

제공 fixture를 이용한 실제 Kordoc end-to-end 흐름:

```sh
python3 scripts/e2e_sample.py \
  /opt/data/IITP_work/output/01_기술기획보고서_초안.hwpx \
  --compatibility-source /absolute/path/to/known-good.hwpx \
  --data-dir ./e2e-data --clean
```

E2E는 업로드·파싱 → 기획 초안 → 기획 확정/HWPX 검증 → RFP 초안 → RFP 확정/HWPX 검증을 실제 API 라우팅과 Kordoc CLI로 실행합니다. fixture는 테스트 입력일 뿐 애플리케이션 코드나 문서 템플릿에 포함되지 않습니다.

## API 요약

| Method | Endpoint | 역할 |
| --- | --- | --- |
| `POST` | `/api/projects` | `{filename, content_base64}` HWPX 업로드·분석 |
| `GET` | `/api/projects` | 로컬 프로젝트 목록 |
| `GET` | `/api/projects/{id}` | 프로젝트 상태 조회 |
| `PATCH` | `/api/projects/{id}/review` | 담당자 결정·근거 레지스트리 저장 |
| `POST/PUT` | `/api/projects/{id}/planning` | 기획 초안 생성/수정 |
| `POST` | `/api/projects/{id}/planning/confirm` | 기획 HWPX 생성·검증·확정 |
| `POST/PUT` | `/api/projects/{id}/rfp` | RFP 초안 생성/수정 |
| `POST` | `/api/projects/{id}/rfp/confirm` | RFP HWPX 생성·검증·확정 |
| `GET` | `/api/projects/{id}/download/{planning\|rfp}` | 검증된 HWPX 다운로드 |
| `GET` | `/api/projects/{id}/render/{planning\|rfp}` | SVG 렌더 확인 |
| `GET` | `/api/projects/{id}/roundtrip/{planning\|rfp}` | 왕복 Markdown 확인 |
| `GET` | `/api/projects/{id}/manifest/provenance` | provenance manifest |

## 안전성과 provenance

- 업로드 파일명은 정규화하며 프로젝트 ID 밖의 경로를 사용할 수 없습니다.
- 입력 HWPX의 절대 저장경로, 크기, SHA-256, ZIP 검사, Kordoc 파싱 명령을 manifest에 기록합니다.
- 외부 근거는 `source_evidence`, 담당자 답변은 `owner_decision`, 업로드는 `source_demand_hwpx`로 역할을 분리합니다.
- 입력에서 찾은 값과 미결정값은 각각 `source_input`, `unresolved` provenance로 구분됩니다.
- 수치와 외부 사실을 생성 모델로 추정하지 않습니다. 사용자가 명시한 결정 또는 검증된 URL 근거만 확정값으로 취급합니다.
- 생성본을 입력 원본이나 템플릿으로 승격하지 않습니다.

## 알려진 한계

- 현재 분석은 로컬 결정론적 휴리스틱입니다. 다양한 표 라벨·병합셀은 Kordoc Markdown 결과에 따라 일부 필드가 미확정으로 남을 수 있습니다. 이는 잘못 채우는 것보다 의도적으로 보수적인 동작입니다.
- 외부 정책·시장 조사를 자동 수행하지 않습니다. 검증된 출처는 사용자가 등록해야 합니다.
- RFP는 사용자 제공 전용 RFP 양식이 없어도 동작하는 일반 표 중심 구조입니다. 특정 기관 양식의 픽셀 단위 복제가 아닙니다.
- Kordoc 프리셋 재생성은 구조·스타일 근사입니다. `template_fidelity=generic_structure_only`로 명시하며 HWPX가 검증되었다고 해서 한컴의 모든 버전에서 동일하게 보인다는 뜻은 아닙니다.
- 브라우저 UI는 Markdown 텍스트 편집기입니다. 표 단위 WYSIWYG 편집과 다중 사용자 협업은 MVP 범위 밖입니다.
- Kordoc 생성본에 `settings.xml`, `version.xml`, `META-INF/manifest.xml`이 없고 known-good 원본도 없으면 API는 `422`와 `completed=false`를 반환합니다. 호환성 보강 후 ZIP·validate·왕복·render 전체 게이트를 다시 통과해야 확정됩니다.

## Vercel 배포 런타임

Vercel Python Function에는 `npx`가 제공되지 않으므로 Kordoc CLI를 실행할 Node.js 런타임과 Kordoc npm 의존성을 `api/runtime/`에 번들합니다. `iitp_app.kordoc.KordocCLI`는 `api/runtime/node`와 `api/runtime/node_modules/kordoc/dist/cli.js`가 있으면 이를 우선 사용하고, 로컬 개발 환경에서는 `KORDOC_COMMAND` 또는 `npx` fallback을 사용할 수 있습니다. PDF/OCR용 선택적 의존성은 Vercel 함수 크기를 줄이기 위해 제외되어 HWPX 파싱·생성·검증·왕복·렌더링 경로를 대상으로 합니다.

## 적용한 프로젝트 규칙

구현은 저장소 외부의 지정 자료를 읽고 다음 원칙을 반영했습니다: 원문 우선, 양식/내용 분리, ①·②·③ 정보 매핑, 담당자 결정 우선, 미결정 수치 placeholder, 기획→RFP 의미 변환, native Kordoc 생성, ZIP·validate·왕복·render 완료 게이트. 샘플 고유 기술·정책·수치·기관은 재사용하지 않습니다.
