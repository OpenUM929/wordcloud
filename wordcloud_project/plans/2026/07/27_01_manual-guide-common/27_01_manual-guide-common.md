# 운영자 메뉴얼 작성 지침 공용화 — `.clinerules/docs/common/operator-manual/` 신설

> 상태: Done | 작성일: 2026-07-27 | 완료일: 2026-07-27
> 작업 유형: D (리팩토링 — 문서 구조 재편, 코드 변경 없음)
> 선행: 23_01 (`wordcloud_project/plans/2026/07/23_01_clinerules-msys-decontaminate/23_01_clinerules-msys-decontaminate.md`)
> 관련 CR: -
> 참조 지침: `D:\dev\wordcloud\.clinerules\core\00-core\03.plan-mode.md`(계획서 작성 규칙), `D:\dev\wordcloud\.clinerules\core\00-core.md`(작업 유형 분류표)

> **본 문서는 사후 기록(post-hoc) 계획서다.** 아래 작업은 2026-07-27 세션에서 이미 전부 실행 완료되었다(코드/문서 변경 종결). 이 문서는 그 실행 내역을 계획서 관례에 맞춰 기록하는 것이며, plan-mode.md #14의 "재확인"(사용자 사전 확인) 절차는 생략하고 바로 "작업 후 답"까지 채운 완결 표로 작성했다. 계획서 저장만 수행했으며, 추가 코드/문서 변경은 사용자가 별도로 "수행"을 명시할 때까지 하지 않는다.

---

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-07-27 | 전체 | 사후 기록 초안 작성(Done) |

---

## 요구사항 원자화

원자 질문·기대값은 상위 지시(작업 지시문)에서 그대로 채택했고, 아래 "작업 후 답"은 2026-07-27 본 세션에서 Read/Grep/Bash로 직접 재검증한 결과다.

| # | 원자 질문 | 기대 | 작업 후 답 (근거) |
|---|-----------|------|------------------|
| 1.1 | `D:\dev\wordcloud\.clinerules\docs\common\operator-manual\DEVELOPMENT\00-a4-authoring-guide.md`가 실제로 존재하는가? | Y | Y — `ls` 확인, 파일 존재 |
| 1.2 | `D:\dev\wordcloud\.clinerules\docs\msys\operator-manual\DEVELOPMENT\00-a4-authoring-guide.md`(구 위치)가 삭제되어 없는가? | Y | Y — `ls` 시도 시 "No such file or directory" |
| 1.3 | `D:\dev\wordcloud\.clinerules\docs\project_wordcloud\operator-manual\DEVELOPMENT\00-a4-authoring-guide.md`(구 수작업 사본)가 삭제되어 없는가? | Y | Y — `ls` 시도 시 "No such file or directory" |
| 1.4 | `core/00-core.md` 42행이 이제 `docs/common/operator-manual/`를 가리키는가? | Y | Y — `core/00-core.md:42`, 실제 행: `` `[.clinerules/docs/project_wordcloud/operator-manual/DEVELOPMENT.md]` (프로젝트 나침반) → **공용 작성 규칙 정본은 [docs/common/operator-manual/DEVELOPMENT.md]** ``, `git diff core/00-core.md`로 변경 전(`docs/msys/operator-manual/...`) 대비 확인 |
| 1.5 | `build_integrated.py`의 HTML 타이틀이 "MSYS"를 포함하지 않는가? | Y | Y — `grep -n "MSYS" docs/common/operator-manual/build/build_integrated.py` 결과 0건. 재빌드한 두 `integrated-manual.html` 모두 `<title>운영자 메뉴얼 (통합)</title>` (MSYS 문자열 없음) |
| 1.6 | `docs/project_wordcloud/operator-manual/developer-manual/01-architecture.md`의 첫 H1이 손번호 없이 `# 아키텍처 개요`인가? | Y | Y — 파일 5번째 줄이 `# 아키텍처 개요` (프론트매터 `reportTheme: technical` 다음) |
| 1.7 | 재빌드한 두 `integrated-manual.html`에 "목록으로"/"이전:"/"다음:" 문자열이 0건인가? | Y | Y — 두 파일 모두 재빌드 후 `grep -c "목록으로\|이전:\|다음:"` = 0 |

---

## 1. 배경 및 문제

`.clinerules`는 msys·project_wordcloud 등 여러 프로젝트가 공유하는 서브모듈이다(`D:\dev\wordcloud\.clinerules`). 운영자 메뉴얼 작성 지침 원자 문서 9개(`DEVELOPMENT/00-a4-authoring-guide.md` ~ `08-change-log.md`)가 문서 자체 안에서 "모든 프로젝트 공용"이라고 선언만 해두고, 실제로는 `docs/msys/operator-manual/DEVELOPMENT/` 폴더 안에만 물리적으로 존재했다.

`docs/project_wordcloud/operator-manual/`에는 이 중 `00-a4-authoring-guide.md` 하나만 msys 사본과 byte-identical하게 수작업 복붙 동기화되고 있었고(변경 전 `git diff core/00-core.md`에서 확인되는 구 참조 경로가 이를 뒷받침), 01~08 나머지 문서는 project_wordcloud에 전혀 존재하지 않았다. 사용자가 이 상태를 지적("공통으로 구성 안되어 있어?")했고, "각각의 프로젝트 메뉴얼 지침에서 공통 부분으로 사용할 수 있는 모든 부분을 공통지침으로 옮겨줘"라고 명시적으로 요청했다.

---

## 2. 실행 내역 (전부 완료 — 2026-07-27 세션)

### 2.1 공용 위치 신설

`D:\dev\wordcloud\.clinerules\docs\common\operator-manual\` 신설(기존 선례 `docs/ui/common/design-system/`와 동일 패턴). 나침반 `D:\dev\wordcloud\.clinerules\docs\common\operator-manual\DEVELOPMENT.md` 신규 작성 — §0에 최우선 정본(`00-a4-authoring-guide.md`)을 걸고, "문서 지도" 표(00~08)와 "한눈 요약(원칙)"으로 구성(실제 파일 Read로 확인, 총 52행).

### 2.2 완전 공용 문서 이동 (git mv, 내용 변경 없이 위치만 이동)

`git status --short` 확인 결과, 아래 5개 파일이 `docs/msys/operator-manual/DEVELOPMENT/` → `docs/common/operator-manual/DEVELOPMENT/`로 rename(`R`) 처리됨:

- `DEVELOPMENT/00-a4-authoring-guide.md`
- `DEVELOPMENT/01-structure.md`
- `DEVELOPMENT/04-a4-print.md`
- `DEVELOPMENT/05-composition-nav.md`
- `DEVELOPMENT/07-checklist.md`

### 2.3 부분 공용 분리 (내용 분할 후 재작성 — `RM`/`AM`으로 git status에 표기)

- **`02-image-capture.md`**: 공용본(`docs/common/operator-manual/DEVELOPMENT/02-image-capture.md`) Read로 확인한 결과 §1(캡처 원칙)·이하 삽입/절차만 포함, msys 전용 "§4 캡처 영역 예시" 표(대시보드/수집스케줄/API키관리 등 메뉴명)는 제외되어 `docs/msys/operator-manual/DEVELOPMENT/msys-specifics.md` §1로 이관됨(해당 파일 Read로 확인, 대시보드·수집 스케줄·API 키 관리·사용자 관리·관리자 설정 5행 표 존재).
- **`03-content-rules.md`**: 공용본 Read로 확인한 결과 제목이 "공통 작성 규칙 · 용어 사전 원칙"으로 변경되었고, §1(한글/테이블/경고 등 공통규칙)만 포함. msys 전용 "mngr_sett 작성 특이사항" 섹션 전체와 CD901~904류 예시 표는 공용본에 없고(`grep -c "mngr_sett\|CD90" docs/common/operator-manual/DEVELOPMENT/03-content-rules.md` = 1건, 단 이 1건은 msys 전용 섹션이 아니라 "메뉴ID는 영문 그대로: `mngr_sett`, `api_key_mngr`"라는 네이밍 표기 예시일 뿐), msys 전용 실제 특이사항은 `msys-specifics.md`에 존치(`grep -c "mngr_sett\|CD90" docs/msys/operator-manual/DEVELOPMENT/msys-specifics.md` = 5건).
- **`06-integrated-build.md`**: 공용본에 `cd .clinerules/docs/<프로젝트키>/operator-manual`(프로젝트 중립 플레이스홀더)가 실제로 존재함(`grep -n "cd \.clinerules/docs" docs/common/operator-manual/DEVELOPMENT/06-integrated-build.md` 28행에서 확인).
- **`08-change-log.md`**: 공용 이동 + 2026-07-27 항목 실제 존재 확인(`grep -n "2026-07-27" docs/common/operator-manual/DEVELOPMENT/08-change-log.md` 21행, 본 재구조화 작업 자체를 상세 서술).

### 2.4 msys 전용 잔여 파일 신설

`docs/msys/operator-manual/DEVELOPMENT/msys-specifics.md` 신규 생성(`git status`에 `A` — msys-specifics.md 추가로 표기) — 위에서 제외한 캡처 영역 예시 표·mngr_sett 특이사항·CD901~904 예시를 모아 존치. 파일 Read로 §1(캡처 영역 예시 표) 존재 확인.

### 2.5 양쪽 프로젝트 `DEVELOPMENT.md` 재작성

- `docs/msys/operator-manual/DEVELOPMENT.md`, `docs/project_wordcloud/operator-manual/DEVELOPMENT.md` 모두 `git status`에 수정(`M`)/신규(`??`)로 표기.
- `docs/project_wordcloud/operator-manual/DEVELOPMENT.md`를 Read로 전문 확인(29행) — 1~4행에서 공용 나침반(`../../common/operator-manual/DEVELOPMENT.md`)을 정본으로 걸고, "wordcloud 프로젝트 전용 작성 규칙" 섹션은 "현재 전용 규칙 없음, 공용 규칙만으로 충분"이라고 명시. §빌드 섹션에 공용 스크립트 상대경로 호출 명령이 실제로 기재됨.
- project_wordcloud 구 `00-a4-authoring-guide.md` 사본은 삭제됨(§1.3 원자질문 확인).

### 2.6 빌드 스크립트 이관 + 버그 수정

`docs/msys/operator-manual/build/build_integrated.py`·`print.css` → `docs/common/operator-manual/build/`로 `git mv`(git status `RM` 표기).

- **`BASE` 기본값 변경**: `docs/common/operator-manual/build/build_integrated.py` 32행 실측 — `BASE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()`. 스크립트가 공용 폴더로 이동한 이상 구 방식(`Path(__file__).resolve().parent.parent`, 스크립트 자기 위치 기준)은 무의미해져 현재 작업 디렉터리(`Path.cwd()`) 기준으로 변경된 상태가 실제 코드로 확인됨.
- **CSS 탐색 3단 확장**: 같은 파일 34~38행 실측 —
  ```python
  CSS = BASE / "build" / "print.css"
  if not CSS.exists():                # 그 프로젝트의 상위(operator-manual)가 갖는 공용 print.css
      CSS = BASE.parent / "build" / "print.css"
  if not CSS.exists():                # 모든 프로젝트 공용 정본(이 스크립트와 같은 폴더)
      CSS = Path(__file__).resolve().parent / "print.css"
  ```
  기존 2단(대상 폴더 자신 → `BASE.parent`)에 마지막 3번째 단계(스크립트와 같은 공용 폴더의 `print.css`)가 추가되어 있음 — project_wordcloud처럼 로컬 `print.css` 사본이 전혀 없는 프로젝트도 공용 정본을 자동으로 찾도록 함(실제로 project_wordcloud 재빌드 시 이 3번째 단계로 도달, §3 검증 참조).
  - **참고**: 문서 주석(11~22행)은 탐색 순서를 "① 그 프로젝트의 `operator-manual/build/print.css` → ② 공용 정본" 2단으로 서술하나, 코드는 대상 폴더 자신 → 상위(`.parent`) → 공용 정본의 3단이다. 실제 우선순위는 코드(34~38행) 기준이며 주석 표현이 다소 축약되어 있음 — 동작에는 영향 없음.
- **버그 발견 및 수정**: HTML 출력 타이틀이 `<title>MSYS 운영자 메뉴얼 (통합)</title>`로 하드코딩되어 있어, 다른 프로젝트(wordcloud) 문서를 빌드해도 "MSYS"가 찍히던 버그였음. 현재 스크립트에 `MSYS` 문자열이 0건(§요구사항 원자화 1.5)이며, 재빌드한 두 HTML 모두 `<title>운영자 메뉴얼 (통합)</title>`로 프로젝트 중립화된 것을 확인.
- **`strip_nav_links()` 신규 함수**(사용자 요청, 대화 중 추가 지시): 같은 파일 185~200행 실측 — 개별 문서 열람용 탐색 링크(`↑`로 시작하는 줄: `↑ [목록으로](...)`, `↑ [← 이전: ...] [다음: ... →]` 등)를 통합 빌드 시점에 걸러낸다. 코드펜스 내부(`FENCE_RE` 매칭 시 `in_fence` 토글)는 건드리지 않는다고 docstring(186~191행)에 명시. 원본 개별 파일은 그대로 두어 낱개 열람 시 탐색은 유지.
- 각 프로젝트의 `operator-manual/build/`(및 `developer-manual/build/`)에는 `MANIFEST.txt`만 남고, `print.css`·`build_integrated.py`는 공용 위치 단일 사본만 존재 — `docs/project_wordcloud/operator-manual/developer-manual/MANIFEST.txt`(잘못된 위치의 중복 미사용 파일, `build/MANIFEST.txt`와 중복이고 빌드 스크립트가 읽지 않는 죽은 파일)는 삭제되어 현재 `ls` 시도 시 "No such file or directory".

### 2.7 참조 갱신 (Grep 전수 확인 후 수정)

- `core/00-core.md` 42행 — `git diff core/00-core.md` 실측: "운영자 메뉴얼 작성/수정" 라우팅 항목이 변경 전 `docs/msys/operator-manual/DEVELOPMENT.md`(나침반) + `docs/msys/operator-manual/DEVELOPMENT/00-a4-authoring-guide.md`(정본)를 가리키던 것에서, 변경 후 `docs/project_wordcloud/operator-manual/DEVELOPMENT.md`(프로젝트 나침반) → `docs/common/operator-manual/DEVELOPMENT.md`(공용 작성 규칙 정본), `docs/common/operator-manual/DEVELOPMENT/00-a4-authoring-guide.md`(양식·페이지·마크업 최우선 정본, "2026-07-27 공용 이관" 명시)로 갱신됨.
- `docs/msys/operator-manual/README.md` — `git diff` 실측: 구조 트리에서 `build/print.css`·`build_integrated.py` 두 항목이 제거되고 `build/MANIFEST.txt`만 남음. `> print.css·build_integrated.py는 모든 프로젝트 공용 단일 사본으로 docs/common/operator-manual/build/에 있다(2026-07-27 이관...)` 안내 문구 추가. 재생성 커맨드가 `python build/build_integrated.py`에서 `cd .clinerules/docs/msys/operator-manual && python ../../common/operator-manual/build/build_integrated.py .`로 갱신.
- `docs/msys/operator-manual/07-troubleshooting.md` — `git diff` 실측: `DEVELOPMENT/05-composition-nav.md §1.5` 인용 경로가 `../common/operator-manual/DEVELOPMENT/05-composition-nav.md §1.5`로 갱신.
- `docs/msys/operator-manual/08-backup-recovery.md` — `git diff` 실측: 동일 패턴으로 `../common/operator-manual/DEVELOPMENT/05-composition-nav.md §1.5`로 갱신.
- `docs/msys/operator-manual/04-common-menus/02-collection-schedule.md` — `git diff` 실측: `DEVELOPMENT/02-image-capture.md` 인용이 `../../common/operator-manual/DEVELOPMENT/02-image-capture.md`(하위 폴더이므로 `../../`)로 갱신.
- `docs/project_wordcloud/operator-manual/developer-manual/build/MANIFEST.txt` — 2행 실측: `# 빌드: cd .clinerules/docs/project_wordcloud/operator-manual && python ../../common/operator-manual/build/build_integrated.py developer-manual`. (수정 전 msys 경로가 잘못 하드코딩되어 있었던 것 — wordcloud 빌드인데 msys에서 실행하라는 주석이었음 — 을 올바른 경로로 교정)
- `docs/project_wordcloud/operator-manual/developer-manual/MANIFEST.txt`(잘못된 위치의 중복 미사용 파일, `build/MANIFEST.txt`와 중복이고 빌드 스크립트가 읽지 않는 죽은 파일) 삭제 — `ls` 시도 시 파일 없음 확인.

### 2.8 wordcloud 개발 메뉴얼 이중번호 수정 (후속 사용자 요청)

`docs/project_wordcloud/operator-manual/developer-manual/01-architecture.md` ~ `09-extension-points.md` 9개 파일에서, 자동채번 시스템(`build_integrated.py`의 `Numberer`가 `1`/`1.1`/`1.1.1` 계층 번호를 빌드 시점에 자동 주입 — `docs/common/operator-manual/DEVELOPMENT.md` 51행 "헤딩 번호: md 원문에는 손으로 번호를 적지 않는다"와 일치)와 충돌하는 손으로 박아둔 번호를 제거:

- **H1**: `grep -h "^# " docs/project_wordcloud/operator-manual/developer-manual/0*.md` 실측 결과, 9개 파일의 H1이 모두 `# 아키텍처 개요`, `# 모듈 지도`, `# 감정분석 엔진`, `# 데이터 계층`, `# 빌드·배포`, `# 배치 처리`, `# 파인튜닝 데이터 파이프라인`, `# 개발 환경·테스트·트러블슈팅`, `# 확장 포인트 / 주의`로, 손번호 접두(`01. ` 등) 없음을 확인.
- **H2**: `grep -c "^## " <파일>` 각각 실측 — 01:5, 02:4, 03:4, 04:5, 05:4, 06:5, 07:4, 08:4, 09:5 (합계 40, 산식: 각 파일 카운트의 단순 합). `grep -rn "^## [0-9]\+\. "`(숫자 접두 패턴)로 9개 파일 전체를 재검색한 결과 0건 — 손번호 H2가 완전히 제거되었음을 확인.
- **코드펜스 내부 예외**: `docs/project_wordcloud/operator-manual/developer-manual/08-dev-setup-troubleshooting.md` 32~38행 실측 — `# (1) 가상환경·의존성`, `# (2) 실행 (기본 127.0.0.1:5001)`는 ` ``` ` 코드펜스(34행 시작) 안의 셸 주석이며, 실제 H1/H2 헤딩이 아니므로 정비 대상에서 제외된 것이 맞음(빌드 스크립트가 헤딩으로 오인하지 않음 — `strip_nav_links()`와 동일하게 `FENCE_RE`로 코드펜스 내부를 건드리지 않는 구조).

---

## 3. 검증 (실제 재빌드 실행 결과)

2026-07-27 본 세션에서 아래 두 명령을 직접 실행:

```bash
cd /d/dev/wordcloud/.clinerules/docs/msys/operator-manual
python ../../common/operator-manual/build/build_integrated.py .

cd /d/dev/wordcloud/.clinerules/docs/project_wordcloud/operator-manual
python ../../common/operator-manual/build/build_integrated.py developer-manual
```

- 둘 다 정상 종료(각 파일 `[ok]` 라인 출력, 마지막에 "통합 완료" + 산출 경로 2개 출력). 산출물: `docs/msys/operator-manual/integrated-manual.md`/`.html`, `docs/project_wordcloud/operator-manual/developer-manual/integrated-manual.md`/`.html` 재생성됨.
- `grep -o "<title>[^<]*</title>"` — 두 HTML 모두 `<title>운영자 메뉴얼 (통합)</title>` (MSYS 하드코딩 없음).
- `grep -c "h1 { font-size: 18pt" <html>` — 두 HTML 모두 1건. wordcloud 쪽은 로컬 `print.css`가 없으므로 §2.6의 3단 CSS fallback 마지막 단계(공용 폴더 사본)로 정상 도달해 임베드된 것으로 확인.
- `grep -c "목록으로\|이전:\|다음:" <html>` — 두 HTML 모두 0건 (탐색 링크가 통합본에서 정상 제거됨, `strip_nav_links()` 동작 확인).
- wordcloud 쪽 `grep -o "<h1>[^<]*</h1>"` — `<h1>1 아키텍처 개요</h1>` ~ `<h1>9 확장 포인트 / 주의</h1>`로 `Numberer` 자동채번과 원문 무번호 헤딩이 정상 결합됨(이중번호 — 예: 수정 전이라면 `<h1>1 01. 아키텍처 개요</h1>` — 이 사라짐).

---

## 4. 변경 대상 파일 목록

전체 경로는 `D:\dev\wordcloud\.clinerules\` 기준. 계층 구분: 이 서브모듈은 코드가 아닌 지침/문서 저장소이므로 "docs"(운영자 메뉴얼 콘텐츠)와 "core"(공통 라우팅 규칙)로만 구분한다.

| 파일 | 유형 | 계층 |
|------|------|------|
| `docs/common/operator-manual/DEVELOPMENT.md` | 신규 | docs (공용 나침반) |
| `docs/common/operator-manual/DEVELOPMENT/00-a4-authoring-guide.md` | 이동(rename, 내용 무변경) | docs (공용) |
| `docs/common/operator-manual/DEVELOPMENT/01-structure.md` | 이동(rename, 내용 무변경) | docs (공용) |
| `docs/common/operator-manual/DEVELOPMENT/02-image-capture.md` | 이동+분할 재작성 | docs (공용) |
| `docs/common/operator-manual/DEVELOPMENT/03-content-rules.md` | 이동+분할 재작성 | docs (공용) |
| `docs/common/operator-manual/DEVELOPMENT/04-a4-print.md` | 이동(rename, 내용 무변경) | docs (공용) |
| `docs/common/operator-manual/DEVELOPMENT/05-composition-nav.md` | 이동(rename, 내용 무변경) | docs (공용) |
| `docs/common/operator-manual/DEVELOPMENT/06-integrated-build.md` | 이동+명령 중립화 재작성 | docs (공용) |
| `docs/common/operator-manual/DEVELOPMENT/07-checklist.md` | 이동(rename, 내용 무변경) | docs (공용) |
| `docs/common/operator-manual/DEVELOPMENT/08-change-log.md` | 이동+2026-07-27 항목 추가 | docs (공용) |
| `docs/common/operator-manual/build/build_integrated.py` | 이동(rename)+`BASE`/CSS fallback/타이틀/`strip_nav_links` 수정 | docs (공용 빌드 툴링) |
| `docs/common/operator-manual/build/print.css` | 이동(rename, 내용 무변경) | docs (공용 빌드 툴링) |
| `docs/msys/operator-manual/DEVELOPMENT/msys-specifics.md` | 신규 | docs (msys 전용) |
| `docs/msys/operator-manual/DEVELOPMENT.md` | 수정(공용 나침반 참조로 축소) | docs (msys 나침반) |
| `docs/msys/operator-manual/README.md` | 수정(구조 트리·재생성 커맨드 갱신) | docs |
| `docs/msys/operator-manual/07-troubleshooting.md` | 수정(참조 경로 1곳) | docs |
| `docs/msys/operator-manual/08-backup-recovery.md` | 수정(참조 경로 1곳) | docs |
| `docs/msys/operator-manual/04-common-menus/02-collection-schedule.md` | 수정(참조 경로 1곳) | docs |
| `docs/msys/operator-manual/build/print.css`, `build_integrated.py` | 삭제(공용 위치로 이동됨) | docs |
| `docs/project_wordcloud/operator-manual/DEVELOPMENT.md` | 신규(공용 나침반 참조 얇은 나침반) | docs (project_wordcloud 나침반) |
| `docs/project_wordcloud/operator-manual/DEVELOPMENT/00-a4-authoring-guide.md`(구 수작업 사본) | 삭제 | docs |
| `docs/project_wordcloud/operator-manual/developer-manual/01-architecture.md` ~ `09-extension-points.md` | 수정(H1 9건·H2 40건 손번호 제거) | docs |
| `docs/project_wordcloud/operator-manual/developer-manual/build/MANIFEST.txt` | 수정(빌드 커맨드 주석 경로 교정) | docs |
| `docs/project_wordcloud/operator-manual/developer-manual/MANIFEST.txt`(중복 죽은 파일) | 삭제 | docs |
| `core/00-core.md` | 수정(42행 라우팅 경로 갱신) | core (공통 라우팅 규칙) |

---

## 5. 영향도 / 리스크

### 5.1 공용 문서(`docs/common/operator-manual/`) — 🟡 향후 수정 시 승인 필요 항목

`docs/common/operator-manual/`은 msys·project_wordcloud 등 여러 프로젝트가 함께 참조하는 공용 정본이다(static/js/modules/common/*.js와 동급의 "공통 모듈" 성격). 2026-07-27 본 작업으로 이 폴더를 신설·채운 것 자체는 이번 계획서의 완료 범위이지만, **향후 이 폴더 내용을 추가로 수정할 때는 msys 쪽 문서에도 영향이 전파되므로 사전 고지/승인이 필요**하다. 아래는 `grep -rl "common/operator-manual" --include="*.md" .`(저장소 루트: `D:\dev\wordcloud\.clinerules`) 전수 확인 결과 — 공용 경로를 참조하는 12개 파일:

| 참조 파일 | 참조 성격 |
|-----------|-----------|
| `core/00-core.md` | 공통 라우팅 규칙(전 프로젝트 진입점) |
| `docs/common/operator-manual/DEVELOPMENT.md` | 자기 자신(공용 나침반, self) |
| `docs/common/operator-manual/DEVELOPMENT/06-integrated-build.md` | 자기 자신(공용 원자 문서, self) |
| `docs/common/operator-manual/DEVELOPMENT/08-change-log.md` | 자기 자신(공용 원자 문서, self) |
| `docs/msys/operator-manual/04-common-menus/02-collection-schedule.md` | msys 콘텐츠 문서 — 공용 캡처 규칙 인용 |
| `docs/msys/operator-manual/07-troubleshooting.md` | msys 콘텐츠 문서 — 공용 시나리오 규칙 인용 |
| `docs/msys/operator-manual/08-backup-recovery.md` | msys 콘텐츠 문서 — 공용 시나리오 규칙 인용 |
| `docs/msys/operator-manual/DEVELOPMENT.md` | msys 나침반 — 공용 나침반 참조 |
| `docs/msys/operator-manual/DEVELOPMENT/msys-specifics.md` | msys 전용 잔여 — 공용 원자 문서 역참조 |
| `docs/msys/operator-manual/README.md` | msys 구조 안내 — 공용 이관 안내 |
| `docs/msys/operator-manual/integrated-manual.md` | msys 빌드 산출물(재생성 시 자동 갱신, 수동 편집 대상 아님) |
| `docs/project_wordcloud/operator-manual/DEVELOPMENT.md` | project_wordcloud 나침반 — 공용 나침반 참조 |

이 중 msys 쪽 6개(콘텐츠 3 + 나침반/README/잔여 3, 빌드 산출물 제외)는 본 작업으로 **함께 수정되었으며 본 계획서 범위 내**이므로 추가 승인 불필요. 다만 **향후** `docs/common/operator-manual/DEVELOPMENT/*.md` 원자 문서나 `build/build_integrated.py`를 다시 수정하는 작업은, 위 12개 참조처(특히 msys 6개) 전체에 영향이 미치므로 별도 계획서에서 호출처 재확인 후 진행할 것을 권고한다.

### 5.2 리스크

| 리스크 | 대응 |
|--------|------|
| `docs/common/operator-manual/DEVELOPMENT/06-integrated-build.md` 주석(2단 표현)과 `build_integrated.py` 실제 코드(3단 fallback)의 서술 불일치 | 동작에는 영향 없음(코드가 실제 정본). 문서 표현 정밀화는 별도 소규모 후속 작업으로 남김(본 계획서 범위 아님) |
| `.sessions`(git 협업 보존 규칙, plan-mode.md "Git 커밋/푸시 시 지침 파일 취급 규칙") 미준수 시 원격 병합 충돌 | 본 작업은 아직 커밋 전(작업 트리 변경, `git status`로 확인) — 커밋 시 `git diff HEAD~1 -- .clinerules/`로 원격 대비 확인 후 append 방식으로 커밋할 것 |
| project_wordcloud/developer-manual 9개 파일의 H1/H2 손번호 제거가 다른 프로젝트(msys)의 콘텐츠 문서에는 적용되지 않음(범위 밖) | msys 쪽 헤딩 번호 실태는 본 작업에서 조사하지 않았음 — 별도 확인 필요 시 후속 계획서로 분리 |

---

## 6. 롤백 방법

본 작업은 파일 이동(rename)·분할·삭제·경로 문자열 치환으로 구성되어 코드 로직 변경은 `build_integrated.py`(BASE 기본값·CSS fallback·타이틀·`strip_nav_links`)에 한정된다. 롤백이 필요할 경우:

1. **커밋 전(현재 상태)**: `.clinerules` 서브모듈에서 `git checkout -- .` 또는 `git restore .`로 작업 트리 전체를 직전 커밋(`6abcce2`, 2026-07-22) 상태로 되돌린다. 단, 이 커밋 시점 이후 23_01 등 다른 미커밋 변경도 함께 소실되므로 필요한 파일만 개별 `git restore <path>`로 선별 롤백 권장.
2. **커밋 후**: 본 작업을 별도 커밋으로 분리해 두었다면 `git revert <해당 커밋>`으로 되돌린다.
3. **부분 롤백(빌드 스크립트만)**: `docs/common/operator-manual/build/build_integrated.py`의 개별 수정(BASE 기본값 32행, CSS fallback 34~38행, 타이틀 문자열, `strip_nav_links` 185~200행)만 되돌리려면 해당 줄만 직전 버전(`docs/msys/operator-manual/build/build_integrated.py`, 커밋 `6abcce2` 시점)과 대조해 수동 복원한다.

---

## 실행 로그(수행일·작업자)

- **수행일**: 2026-07-27
- **작업자**: Claude Code(AI)

### 수행 명령어(재빌드 검증, 본 세션에서 실행)

```bash
cd /d/dev/wordcloud/.clinerules/docs/msys/operator-manual
python ../../common/operator-manual/build/build_integrated.py .

cd /d/dev/wordcloud/.clinerules/docs/project_wordcloud/operator-manual
python ../../common/operator-manual/build/build_integrated.py developer-manual
```

### 입력 파일(전체 경로)

- `D:\dev\wordcloud\.clinerules\docs\msys\operator-manual\build\MANIFEST.txt`
- `D:\dev\wordcloud\.clinerules\docs\project_wordcloud\operator-manual\developer-manual\build\MANIFEST.txt`
- `D:\dev\wordcloud\.clinerules\docs\common\operator-manual\build\build_integrated.py`
- `D:\dev\wordcloud\.clinerules\docs\common\operator-manual\build\print.css`

### 산출물(전체 경로)

- `D:\dev\wordcloud\.clinerules\docs\msys\operator-manual\integrated-manual.md`
- `D:\dev\wordcloud\.clinerules\docs\msys\operator-manual\integrated-manual.html`
- `D:\dev\wordcloud\.clinerules\docs\project_wordcloud\operator-manual\developer-manual\integrated-manual.md`
- `D:\dev\wordcloud\.clinerules\docs\project_wordcloud\operator-manual\developer-manual\integrated-manual.html`

### 핵심 수치 (집계 명령 병기)

| 수치 | 값 | 집계 명령 |
|------|-----|-----------|
| 두 HTML의 `<title>`에 "MSYS" 잔존 | 0건(둘 다 `운영자 메뉴얼 (통합)`) | `grep -o "<title>[^<]*</title>" <html>` |
| 두 HTML의 print.css 임베드 확인 | 각 1건 | `grep -c "h1 { font-size: 18pt" <html>` |
| 두 HTML의 탐색 링크 잔존 | 0건 | `grep -c "목록으로\|이전:\|다음:" <html>` |
| `build_integrated.py`의 "MSYS" 문자열 잔존 | 0건 | `grep -n "MSYS" docs/common/operator-manual/build/build_integrated.py` |
| developer-manual 9개 파일 H1 손번호(`# NN. `) 잔존 | 0건 | `grep -rn "^# [0-9][0-9]\. " docs/project_wordcloud/operator-manual/developer-manual/0*.md` |
| developer-manual 9개 파일 H2 손번호(`## N. `) 잔존 | 0건 | `grep -rn "^## [0-9]\+\. " docs/project_wordcloud/operator-manual/developer-manual/0*.md \| wc -l` |
| developer-manual 9개 파일 현재 H2 총계 | 40건(01:5, 02:4, 03:4, 04:5, 05:4, 06:5, 07:4, 08:4, 09:5의 합) | 파일별 `grep -c "^## " <파일>` 후 합산 |
| `docs/common/operator-manual/DEVELOPMENT/03-content-rules.md`의 msys 키워드(mngr_sett/CD90) 잔존 | 1건(네이밍 예시 문구, msys 전용 섹션 아님) | `grep -c "mngr_sett\|CD90" docs/common/operator-manual/DEVELOPMENT/03-content-rules.md` |
| `docs/msys/operator-manual/DEVELOPMENT/msys-specifics.md`의 msys 키워드(mngr_sett/CD90) 존재 | 5건 | `grep -c "mngr_sett\|CD90" docs/msys/operator-manual/DEVELOPMENT/msys-specifics.md` |
| 공용 경로(`common/operator-manual`) 참조 파일 수 | 12개(자기 자신 3 + msys 6 + project_wordcloud 1 + core 1 + 빌드산출물 1) | `grep -rl "common/operator-manual" --include="*.md" .`(저장소 루트 `.clinerules`) |

### 편차/불확실

- `docs/common/operator-manual/DEVELOPMENT/06-integrated-build.md` 문서 주석(11~22행)이 CSS 탐색을 2단으로 서술하나 실제 `build_integrated.py` 코드(34~38행)는 3단 fallback이다 — 동작에는 영향 없으나 문서-코드 서술 정밀도 편차로 §5.2에 기록. 정정 여부는 상위 판단 필요.
- 본 세션 종료 시점 기준 `.clinerules` 서브모듈은 **커밋 전 작업 트리 변경 상태**(`git status`로 다수 미커밋 항목 확인, 본 작업 외에도 23_01 등 이전 세션의 미커밋 변경이 함께 존재). 커밋·푸시는 본 계획서 범위에 포함하지 않았다 — 필요 시 plan-mode.md "Git 커밋/푸시 시 `.clinerules` 지침 파일 취급 규칙"(교체 금지·append 방식) 준수하여 별도로 수행할 것.
