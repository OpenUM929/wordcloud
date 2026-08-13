# 운영자 메뉴얼 작성 지침 보완 (A4·탭·탐색·통합)

> 상태: Done | 완료일: 2026-07-15
> 작성일: 2026-07-15
> 작업 유형: docs (문서/지침 작성)
> 참조 지침: `.clinerules/core/00-core.md`(시작 3단계), `.clinerules/docs/msys/operator-manual/DEVELOPMENT.md`, `.clinerules/core/08-guideline-modification`(02·04·05 절차)

---

## 1. 배경 및 요구

사용자는 운영 매뉴얼을 다음 조건으로 작성하기를 원함:
- R1: md 작성 시 A4 용지에 맞춰 줄바꿈·폭이 들어가도록 (인쇄 최적화)
- R2: 제목+서론+목록(1파일) + 메뉴별 1파일 구성
- R3: 탭 보유 메뉴는 구성+탭설명(1) + 탭별(1) 하위파일 분할
- R4: 메뉴 간 클릭 탐색(이전/다음/목록)
- R5: 통합 메뉴얼 존재 (일일이 인쇄 방지)

### 기존 지침 갭 분석
기존 `.clinerules/docs/msys/operator-manual/DEVELOPMENT.md`는 R1·R3·R4·R5 **미포함**, R2는 README 정적 나열뿐. → **신규 섹션으로 보완**.

## 2. 산출물 (완료)

| 파일 | 내용 |
|------|------|
| `DEVELOPMENT.md` | §6 A4 인쇄 규칙, §7 파일 구성(제목/서론/목록+메뉴별+탭 하위파일), §8 탐색 규칙, §9 통합 생성 규칙, **§10 수정이력·테스트결과** 추가 (§1.1 명명 예외, §5 체크리스트 보강) |
| `build/print.css` | `@page A4`(margin 18/16mm), `.container{max-width:170mm}`, `.pagebreak{break-before:page}`, `img{max-width:640px}`, `table{max-width:640px}` |
| `build/MANIFEST.txt` | 통합 순서(34개 파일 목록: 기존 24 + 탭 10) |
| `build/build_integrated.py` | 순수 표준 라이브러리 md→HTML 변환 + 통합 md/html 생성 (외부 의존성 없음). `BASE`=운영자 메뉴얼 루트 기준 |
| `00-index.md` | 신규 진입점: 제목+서론+목록(TOC), 각 메뉴 상대경로 링크. **명칭 `00-index.md` 유지 확정**(기존 `NN-영문.md` 패턴과 일치, §1.1 예외 명시) |
| `integrated-manual.md` | 빌드 결과(단일 md) |
| `integrated-manual.html` | 빌드 결과(A4 print.css 임베드, 브라우저→인쇄→PDF) |
| `README.md` | 구조 트리 갱신(`00-index.md` 진입점, `build/` 폴더, `integrated-manual.*` 반영), 버전 1.1 행 추가 |

## 2.1 지침 위반 인정 및 2차 정정 (08 절차 준수)

1차 작업 후 사용자 지적에 따라 다음 위반을 인정하고 조치함:

| 위반 | 근거 지침 | 조치 |
|------|-----------|------|
| 시작 전 의무 3단계 미준수 | `CLAUDE.md` 최우선 / `00-core.md` 3~5행 | `00-core.md` 분류표 확인 → (운영자 메뉴얼→DEVELOPMENT.md) + (지침 수정→`08-guideline-modification`) 조사 후 작업 |
| 지침 수정 전 Before/After 미제시 | `08/02.modification-procedure.md` §규칙 수정 시 | DEVELOPMENT.md §6~§9 변경분을 Before(없음)/After(추가)로 요약 제시·승인 |
| 수정 후 테스트 결과 미기록 | `08/05.post-modification.md` | DEVELOPMENT.md 하단에 `## 10. 수정 이력 및 테스트 결과` 추가 |
| 신규 파일 README 구조 미갱신 | `08/02` 참조 일관성 | `README.md` 구조 트리·버전 1.1 갱신 |
| NN 명명 규칙 미조사 | `DEVELOPMENT.md` §1.1 `NN-영문-메뉴-명.md` | §1.1에 `00-index.md`(진입점)·`build/` 툴링 예외 명시. **`00-index.md` 명칭은 기존 `NN-영문.md` 패턴(00-getting-started 등)과 일치하므로 유지 확정** |
| 툴링 파일 평탄 배치 | `08/04.folder-naming.md` 정돈 원칙 | `print.css`/`MANIFEST.txt`/`build_integrated.py`를 `build/` 하위로 이동, 스크립트 `BASE` 경로 보정 |

## 2.2 탭 파일 명명(`NN-menu.tabN.md`) 실제 적용 (R3·§7.3)

지적 후 `00-index.md` 유지 확정 속에서도, **탭 보유 메뉴의 `NN-menu.tabN.md` 하위파일 방식이 실제 파일에 한 번도 적용되지 않았던 것**을 인정하고 적용:

- `05-mngr-sett.md`: 기존 인라인 탭 기술 → **구성+탭설명 파일** + `05-mngr-sett.tab1~6.md`(설정/사용자/데이터권한/상태코드/아이콘/API관리) 6개 탭 파일로 분리
- `04-common-menus/08-api-key-mngr.md`: → 구성 파일 + `08-api-key-mngr.tab1~4.md`(API키관리/기간차트/위험군/설정) 4개 탭 파일로 분리
- 각 탭 파일에 §8 규칙(↑메뉴/이전/다음 탭 링크) 적용, `width="800"`→`600` A4 규칙 적용
- `MANIFEST.txt`(탭 파일 순서 추가), `README.md`(구조 트리 탭 파일 반영), `DEVELOPMENT.md §7.3`(실제 파일명 예시 `tab-api`→`tab1`로 정정) 갱신
- `build/build_integrated.py` 재실행 → 34개 파일 통합 성공(기존 24 + 탭 10), 오류 없음

## 3. A4 수치 기준

- A4 가용 가로 ≈ 170mm (≒ 640px @96dpi). 이미지 `width` 기본 600 / 상한 640.
- 페이지 나누기: `<!-- pagebreak -->` → CSS `break-before:page`.
- 표 컬럼 합 ≤ 640px.

## 4. 검증 결과

- `python build/build_integrated.py` 정상 종료, 출력은 운영자 메뉴얼 루트(`integrated-manual.md`/`.html`)에 생성. 1차 빌드 24개 파일 → §2.2 탭 분리(05-mngr-sett 6탭·08-api-key-mngr 4탭 = 탭 10개) 후 **재빌드 34개 파일 모두 `[ok]`**(현재 `build/MANIFEST.txt` 등재 기준).
- `integrated-manual.html`(약 167KB · 171,429 bytes, width→600 재빌드 후 실측): `@page` 포함, `class="pagebreak"` 34개, `<img>` 20개(전부 `width="600"`), 이미지 경로 `04-common-menus/images/...`로 재작성 확인.
- 버그 수정: `**`로 시작하는 문단 줄이 리스트 마커로 오인되어 무한루프 되던 것 → 문단 분기를 `else` 폴백 + 정규식 경계 검사로 해결.
- `00-core.md` line 39가 이미 `operator-manual/DEVELOPMENT.md`를 가리킴 → 분류표 추가 갱신 불필요 확인.

## 5. 잔여/후속 (별도 작업)

- `05-mngr-sett.md`(탭 인라인)는 레거시 → 신규 탭 메뉴만 §7.3 하위파일 방식 적용. 필요 시 마이그레이션.
- weasyprint 설치 시 `build_integrated.py`에 PDF 직접 출력 분기 추가(선택).

## 5.1 `width="800"` → `width="600"` 정비 수행 (2026-07-15)

§5 잔여 항목 중 이미지 폭 초과 정비를 수행함 (A4 규칙 §6.1: 기본 600 / 상한 640).

**대상·처리 건수 (치환 전 → 후)**
| 파일 | `width="800"` → `width="600"` |
|------|------|
| `DEVELOPMENT.md` | 예시 `<img>` 1건 600 치환 (기존 2건 중 1건은 §6.1 규칙 예시 문구 `width="800"` 지양 안내로 의도 보존) |
| `04-common-menus/01-dashboard.md` | 6 → 0 |
| `04-common-menus/02-collection-schedule.md` | 5 → 0 |
| `04-common-menus/03-chart-analysis.md` | 2 → 0 |
| `04-common-menus/04-data-analysis.md` | 1 → 0 |
| `04-common-menus/05-data-spec.md` | 1 → 0 |
| `04-common-menus/06-card-summary.md` | 1 → 0 |
| `04-common-menus/09-jandi.md` | 1 → 0 |

**검증**
- `python build/build_integrated.py` 재실행 → 34개 파일 모두 `[ok]`, 통합본 재생성.
- 전체 `.md`(재귀) `width="800"` 잔여 = **1건** (`DEVELOPMENT.md` §6.1 규칙 예시 문구, 의도된 보존). 실제 이미지 속성 잔여 0.
- `integrated-manual.md` 이미지 `width="600"` 20건 / `width="800"` 0건 확인.
- `DEVELOPMENT.md` §6.1 규칙 문구("기존 `width="800"` 등 상한 초과값 금지") 의미 일관성 확인.

## 5.2 이미지+설명·운영 시나리오 강화 (2026-07-15, 사용자 요청)

`DEVELOPMENT.md`에 지침 추가(08 절차 준수, Before/After 제시·수행). 서브모듈 `.clinerules` 작업트리 반영, 커밋 대기.

- **이미지+설명 의무 강화**: §2.1을 "설명 대상=이미지 1장(요소 단위 필수)"으로 개정, **§2.4 Playwright 요소 캡처 절차** 신설(셀렉터 지정→요소만 스크린샷→`images/`, A4 width 600). §1.2 화면구성 표에 "이미지(요소 캡처)" 열 추가.
- **운영 시나리오 필수화**: §1.2 템플릿에 `## 4. 운영 시나리오`(모니터링/문제 §5/§6 재번호), **§1.3 시나리오 규칙**(메뉴당 최소 1개), **§7.5 종단(E2E) 시나리오** 규칙 신설. §5 체크리스트 2항 추가.
- **참조 매뉴얼 정렬**(사용자 제안 `D:\dev\msys\ref clinerules\...\operator-manual`): 참조본의 이미지/DEVELOPMENT 규칙은 15_04 이전 구버전이라 이미지 규칙엔 신규성 없음. 단 **운영 문서 세트**(`06-daily-operations`·`07-troubleshooting`·`08-backup-recovery`)는 유용한 선례 → §7.5를 신규 파일 창설이 아니라 **기존 06~08 보강**으로 정렬(본 매뉴얼에도 동일 파일 존재).
- **후속 콘텐츠 작업(별도)**: 기존 메뉴 문서(01~08 등)는 신규 규칙상 **시나리오·요소 이미지 미보유 = 미완성** → 각 메뉴에 `## 4. 운영 시나리오` + 요소 캡처 이미지, `06~08`에 Task 기반 E2E 시나리오 백필 필요. (지침은 완료, 실제 캡처/집필은 별도 작업)

## 6. 사용법

```powershell
cd .clinerules/docs/msys/operator-manual
python build/build_integrated.py
# integrated-manual.html → 브라우저 열기 → 인쇄 → PDF 저장 (용지 A4)
```
