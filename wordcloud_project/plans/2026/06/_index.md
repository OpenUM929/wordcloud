# 2026-06 계획서 인덱스

| 계획서 | 작업 요약 | 상태 | 작성일 | 관련 CR | 선행 | 에픽 |
|--------|-----------|------|--------|---------|------|------|
| 02_01_profanity-eng-fix | 불용어 영문 처리 개선 | Done | 2026-06-02 |  |  |  |
| 04_01_deploy-gallery-v2 | 갤러리 v2 배포 | Done | 2026-06-04 |  |  |  |
| 04_01_deploy-image-gallery | 이미지 갤러리 배포 | Done | 2026-06-04 |  |  |  |
| 04_01_deploy-resume | 세션 저장 및 재개 | Done | 2026-06-04 |  |  |  |
| 04_01_profanity-display-fix | 불용어 표시 오류 수정 | Done | 2026-06-04 |  |  |  |
| 05_01_global-auth-real | 전역 인증 체계 도입 | Done | 2026-06-05 |  |  |  |
| 05_01_restore-deploy-preview | 배포 결과 미리보기 복원 | Done | 2026-06-05 |  |  |  |
| 05_02_deploy-ux-enhance | 저장 완료 후 UX 개선 | Done | 2026-06-05 |  |  |  |
| 05_03_deploy-retry-cascade | 실패 태스크 재시도 | Done | 2026-06-05 |  |  |  |
| 08_01_gallery-search-delete | 갤러리 검색 및 삭제 기능 | Done | 2026-06-08 |  |  |  |
| 08_01_matrix-generate-improve | 매트릭스 생성 개선 | Done | 2026-06-08 |  |  |  |
| 08_02_batch-title-input | 배치 명칭 입력 및 중복 확인 | Done | 2026-06-08 |  |  |  |
| 09_01_deploy-retry-dup-fix | 재시도 failData 중복 누적 수정 | Done | 2026-06-09 |  |  |  |
| 09_01_gallery-db-migration | deploy_manifest.json → SQLite 전환 | Done | 2026-06-09 |  |  |  |
| 09_02_evaluation-db-migration | users/*.json → SQLite 정규화 | Done | 2026-06-09 |  |  |  |
| 09_03_internal-localization | 웹시스템 내부망 로컬화 | Done | 2026-06-09 |  |  |  |
| 10_01_gallery-download | 저장 갤러리 이미지 다운로드 | Done | 2026-06-10 | REQ-2606-003 |  |  |
| 10_02_deploy-mode-color-preset | 배포 모드 통합 추가 + 색상 선택 | Done | 2026-06-10 |  |  |  |
| 10_03_sentiment-correction | 문장별 감정 수정 및 워드클라우드 재생성 | Done | 2026-06-10 |  |  |  |
| 10_04_perspective-test-corpus | perspective_test 📋 복사 + 습득한 데이터 게시판 | Done | 2026-06-10 |  |  |  |
| 10_05_neutral-sentence-display | 배포 카드 중립 문장 탭 추가 | Done | 2026-06-10 |  |  |  |
| 11_01_batch-db-unification | 배치 처리 DB 일원화 완성 | Done | 2026-06-11 | REQ-2606-002 | 15_01 |  |
| 11_02_profanity-list-admin | 전사 욕설 리스트 (Admin) | Done | 2026-06-11 |  |  |  |
| 12_01_batch-work-order | 배치 작업서 기반 Resume 시스템 | Done | 2026-06-12 | REQ-2606-004 |  |  |
| 12_02_deploy-preview-pagination | 제출용 저장 결과 화면 페이징 + 아코디언 + 옵션 최적화 | Done | 2026-06-12 |  |  |  |
| 15_01_batch-csv-stream | 배치 CSV 스트리밍 + Staging DB + 2단계 진행 표시 | Done | 2026-06-15 | REQ-2606-031 |  |  |
| 15_02_batch-display-name | 배치 명칭 지정 및 수정 | Done | 2026-06-15 | REQ-2606-031 | 15_01 |  |
| 15_03_profanity-pseudonym | 비속어 기능 가명 복원 누락 수정 | Done | 2026-06-15 | REQ-2606-030 |  |  |
| 15_04_perspective-title-recall | 그룹 분석 테스트 배치 명칭 기반 재호출 | Done | 2026-06-15 |  |  |  |
| 15_05_group-save-option | 그룹 분석 페이지 설정 저장, 전체직원 기본 체크, x축 통합출력 기본 | Done | 2026-06-15 |  |  |  |
| 15_06_emp-id-match-fix | 그룹분석·제출용저장 회귀 수정 (target_employee_id 매칭 키 복원) | Done | 2026-06-15 | REQ-2606-030, REQ-2606-032 |  |  |
| 15_07_sentiment-save-fix | 워드클라우드 감정 분리 모드 저장 누락 수정 | Done | 2026-06-15 |  |  |  |
| 15_08_sentence-kote-cache | 배치 시 문장 단위 KoTE 캐시 저장 + 그룹 분석 재사용 | Done | 2026-06-15 | REQ-2606-033 |  |  |
| 15_09_metadata-group-fix | 통합데이터 생성·그룹 분석 결함 수정 (D·A 해결 / B·C·E 무해·보류→0618_01) | Done | 2026-06-15 |  |  |  |
| 15_10_corpus-refine-csv | 취득 코퍼스 정제 후 CSV 내보내기 (규칙 마이닝용 데이터셋) | Done | 2026-06-15 |  |  |  |
| 17_01_emotion-rule-mining | 코퍼스 기반 감정 규칙 마이닝 + KoTE 분류 정당성 검증 + 긍정어 강화 (코드완료, 잔여 deferred) | Done | 2026-06-17 |  |  |  |
| 17_02_group-bulk-move | 집단 분석 결과 → 습득 데이터 일괄 이동(감정 버킷·욕설·KoTE 값 동반) | Done | 2026-06-17 |  |  |  |
| 17_03_batch-pseudo-flush | 배치 데이터 수집 멈춤 해소 — 가명화 매핑 일괄 저장(O(n²)→O(n)) | Done | 2026-06-17 |  |  |  |
| 17_04_acquired-board-cols | 습득데이터 게시판 감정분석/욕설/비꼼 칸 '-' 표시 수정 | Done | 2026-06-17 |  |  |  |
| 17_05_kote-finetune-data | KoTE 파인튜닝용 데이터셋 설계(설계완료, P1+ 구현 결정 6건 대기 로드맵) | Hold | 2026-06-17 |  |  |  |
| 17_06_word-noise-filter | 단어 추출 노이즈 필터링(반복 도배 collapse 구현 / gibberish는 데이터 근거로 미구현) | Done | 2026-06-17 |  |  |  |
| 17_07_hardware-adaptive-worker-plan | 하드웨어(CPU/RAM/VRAM) 실측 기반 배치 워커 수 동적 선정 + GPU 오프로딩 | Done | 2026-06-17 |  |  |  |
| 18_01_pending-wrapup | 미완료 기능 통합 마무리 (A 정합성 적용완료 / B·C·E 무해·미적용 보류) | Hold | 2026-06-18 |  |  |  |
| 18_02_wordcloud-opt-feasibility | 0617_07 기법의 워드클라우드 적용 가능성 분석(타 AI) — GPU 무관·PIL 렌더링이 병목 | Drop | 2026-06-18 |  |  |  |
| 18_03_deploy-wc-parallel | 제출용 저장 워드클라우드 생성 병렬화(직렬 스트림 → ThreadPool) + getextrema/지역RNG + 결과 캐싱 | Done | 2026-06-18 |  |  |  |
| 18_04_batch-resume-progress | 배치 이어서 처리 진행 현황 + 배치 명칭 출력 오류 수정 | Done | 2026-06-18 |  |  |  |
| 18_05_plans-kanban-board | Plans Kanban Board + 폴더 선택형 프레임워크 | Done | 2026-06-18 |  |  |  |
| 18_06_batch-skip-modal | 배치 시 중복(미저장) 평가 목록 + 증거값 안내 모달 | Done | 2026-06-18 |  |  |  |
| 19_02_deploy-mem-stream | 제출용 저장 메모리 폭증(17k명 29~30GB 정지) 해소 — 직원 단위 로딩(load_employee_batch)으로 전환 | Pre-Done | 2026-06-19 | REQ-2606-032 |  |  |
| 19_03_busy-lock-progress | 배치 이력 + X축(시간/회차) 메타 조회 속도 개선(load_all_batches 제거) + 장시간 작업 전면 차단 오버레이 | Pre-Done | 2026-06-19 |  |  |  |
| 19_04_leadership-judge-ai | 리더십 판단 AI 설계(외부 OpenUM929 골격 + 우리 코퍼스 gold, 문장→micro 추출기·전용분류기, LP0~LP5) | Todo | 2026-06-19 |  |  |  |
| 22_01_metadata-acq-extract | 통합데이터 시점 문장+KoTE 인라인 추출(그룹분석 불요) → 압축 JSONL 핸드오프 코퍼스(LLM 분석용) 전량 적립 | Pre-Done | 2026-06-22 |  |  |  |
| 22_02_kanban-predone | Kanban 보드 Pre-Done(PDN) 상태 추가 | Pre-Done | 2026-06-22 |  |  |  |
| 22_03_wc-logger-fd-leak | 워드클라우드 로거 핸들러 누수로 인한 FD 고갈(Too many open files) 수정 — 그룹/대량 저장 500 | Todo | 2026-06-22 |  |  |  |
| 23_01_judgment-extract-ui | 판정 패킷 추출 배치 체크박스 연동(핸드오프 동형, 둘 다 기본 체크) + eval/judgment 저장 | Pre-Done | 2026-06-23 |  |  |  |
| 23_02_sentiment-rule3-rescue | rule3_last_low 긍→부 보강(장점). 장점 0.6→94.5%·긍↔부0이나 **단점 적대검증서 부→긍 187 회귀** → 결핍·희망·과잉·역접 가드 선결(보류) | Pre-Done | 2026-06-23 |  |  |  |
| 23_03_sentiment-cons-guard | 단점 맥락 부→긍 가드(has_improvement_request) — 0623_02 장점수정의 단점 적대검증 회귀 차단. 단점 부→긍 11,039→8,802, 양방향 긍↔부 0(장점94.5%·하드84.9%) | Pre-Done | 2026-06-24 |  |  |  |
| 24_01_metadata-generation-ui | 통합데이터 생성 UI 버그(로딩 미표시, 폴더선택 공백) + 배치명칭 자동입력 | Done | 2026-06-24 | REQ-2606-035 |  |  |
| 24_02_css-standardization | CSS 표준안 위반 수정 + 최대 너비 1600px 확장 | Done | 2026-06-24 |  |  |  |
| 24_03_judgment-apply-ui | 판정 결과 반영 UI(주기능) — 판정 완료 패킷 업로드→/judgment/apply→요약·검토큐. 추출↔반영 end-to-end 연결 | Pre-Done | 2026-06-24 |  |  |  |
| 24_04_emotion-clustering | KoTE 파인튜닝용 신규 HR 감정그룹 군집 발굴(감정 스트림) — 미피복 484K(56%) 멀티뷰 군집 24개→3대 화행(G1약점부재·G2개선요청·G3역량서술). D1·D3·D4·D5 완료(176K weak 전파·gold 1,318·baseline 1,500). 군집≠gold·필드 1급·긍↔부0 | Doing | 2026-06-24 |  |  |  |
| 24_05_group-review-ui | 신규 그룹 gold 검토 웹 UI(재사용 라벨링) — eval/*.jsonl 호출→긍/부/중/그룹아님 빠른 선택(키보드)·ai_reference 힌트·결정 저장. 데이터 추가 시 재사용. 경로 traversal 가드·admin·plans 배포제외 | Pre-Done | 2026-06-24 |  |  |  |
| 25_01_eval-pseudonym-double-mapping-fix | (오진 학습기록·보존) 가명화가 원인이라 단정했으나 실제 원인은 evaluation_date int → 행 필터 전건탈락. 본문=당시 오진, 최하단 "반전"=실제 원인/해결(date_normalize). 작성법 교훈 6가지 | Done | 2026-06-25 |  |  |  |
| 30_01_nav-restructure | (0701_01 리베이스) 잔여 범위=batch-monitor/judgment-extract 신규 페이지 + 파이프라인 순번화. 허브·접기·배지는 0701_01서 완료 | Todo | 2026-06-30 | REQ-2605-007 |  |  |
| 30_02_unhealthy-substr-fp | 비건전 단어 substring 오탐 수정 (회사정책→"사정" 욕설 오인) — 형태소/단어경계 매칭으로 교체 | Pre-Done | 2026-06-30 |  |  |  |
| 30_03_deficiency-framing-neutral | 결핍·개선요청("보완 필요")이 rule4_default로 부→긍 누수되던 13만 구멍 중립화 — 전수 24,384 수정·긍↔부 0 | Pre-Done | 2026-06-30 |  |  |  |
| 30_04_deficiency-noun-neg | 결핍명사(부족·미흡·결여·부재) substring 부정화 시도 — 전수 재생서 긍→부 263(장점 138) 잔존(술어결정 토픽명사), 코드 원복·극성표/파인튜닝 트랙 이관 | Drop | 2026-06-30 |  |  |  |
| 30_05_perspective-sort-feature | perspective_test 워드클라우드/매트릭스 정렬 기능(오름/내림/긍/부/중/욕설) | Todo | 2026-06-30 |  |  |  |
| 22_04_gallery-collapsible-groups | 갤러리 접을 수 있는 그룹 | Todo | 2026-06-22 |  |  |  |
| 24_03_plan-folder-sequence-rule | (빈 폴더/미작성) | Drop | 2026-06-24 |  |  |  |
