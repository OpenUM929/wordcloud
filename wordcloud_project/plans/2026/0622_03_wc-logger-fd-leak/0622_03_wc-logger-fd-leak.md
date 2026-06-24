# 계획서 — 워드클라우드 로거 파일 디스크립터 누수 수정

> 상태: Todo | 작성일: 2026-06-22
> 작업 유형: A (버그 수정/핫픽스)
> 선행: [0618_03_deploy-wc-parallel](../0618_03_deploy-wc-parallel/0618_03_deploy-wc-parallel.md) — 제출용 저장 워드클라우드 병렬화(ThreadPool)

---

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-22 | 전체 | 최초 작성 (그룹분석 테스트 중 발견된 FD 누수) |

---

## 1. 배경 및 목적

그룹분석(매트릭스) 제출용 저장(`/api/perspective/matrix/save-deploy`) 테스트 중 다수 요청이
`500` 으로 실패. 다량의 워드클라우드를 연속 생성할 때 운영체제 파일 핸들이 고갈되어
서비스가 멈춘다. 원인을 제거하여 대량 그룹/배치 저장에서도 FD 누수가 없도록 한다.

## 2. 문제 정의

- **증상**: `save-deploy` 다건 처리 중 `OSError: [Errno 24] Too many open files`로 500 발생.
  실패 지점은 `wordcloud_config.json` open(`wordcloud_generator.py:37`)으로 보이나, 이는
  FD 고갈 후 **가장 먼저 실패한 open**일 뿐 진짜 누수원이 아니다.
- **재현 조건**: 행 수가 많은 매트릭스 또는 대량 그룹을 제출용 저장. 통합/긍정/부정 3장 ×
  행 수만큼 워드클라우드를 생성하면서 열린 파일이 누적된다.

## 3. 원인 분석

- **근거 (로그)**: `260617.txt`
  ```
  perspective_service.py:2049 _generate_wc_for_items
  perspective_service.py:2030 _save_wc
  perspective_service.py:1221 _save_wordcloud_to_path
  wordcloud_generator.py:127 __init__  (WordCloudGenerator)
  wordcloud_generator.py:32  __init__  (WordCloudConfig)
  wordcloud_generator.py:37  _load_config → OSError [Errno 24]
  ```
- **근거 (코드)**:
  - `src/services/perspective_service.py:1221` `_save_wordcloud_to_path` 는 호출마다
    `WordCloudGenerator(config_path=...)` 를 **새로 생성**한다.
  - `src/services/perspective_service.py:2143` `_save_wc` 는 통합/긍정/부정 3회 호출되고,
    `_generate_wc_for_items` 가 행마다 반복된다 → 생성 인스턴스가 행×3 으로 증식.
  - `src/modules/wordcloud_generator.py:120` `WordCloudGenerator.__init__` 가 매번
    `setup_logger(self.config["module_name"], ...)` 호출. `module_name == "wordcloud_generator"`.
  - `utils/logger.py:20` `logging.getLogger(name)` 은 **이름이 같으면 동일 싱글톤**을 반환하는데,
    `:33`/`:45` 에서 매 호출마다 `StreamHandler` + `FileHandler` 를 **중복 add** 한다.
    `FileHandler` 는 즉시 로그 파일을 열며, 제거·close 되지 않는다.
- **분석**: 같은 이름의 로거 1개에 핸들러(=열린 파일)가 무한정 누적된다. 인스턴스가 GC 되어도
  전역 로거 레지스트리(`logging.Logger.manager.loggerDict`)가 로거를 강참조하므로 핸들러와
  열린 파일이 해제되지 않는다. 호출이 수백~수천 회면 열린 파일 수가 OS 한계를 넘어
  이후 모든 `open()`(여기서는 config 로드)이 `Errno 24` 로 실패한다.
- **회귀 도입 지점**: `setup_logger` 의 중복 핸들러 추가는 초기 구현부터 존재한 잠재 결함.
  선행 `0618_03_deploy-wc-parallel` 의 ThreadPool 병렬화로 동시에 다수 인스턴스가 생성되며
  누적 속도가 빨라져 대량 그룹/배치 저장에서 임계점에 먼저 도달, 표면화되었다.

## 4. 수정 방안

- **핵심 변경**: `setup_logger` 가 이미 핸들러가 붙은 로거를 받으면 **재사용하고 조기 반환**한다.
  (프로세스당 1회만 설정 → 핸들러·열린 파일을 콘솔1·파일1 로 고정)
- **세부 수정**:
  - `utils/logger.py` `setup_logger()`: `logger.setLevel(level)` 직후
    `if logger.handlers: return logger` 가드 추가. 핸들러 중복 add 차단.

```python
logger = logging.getLogger(name)
logger.setLevel(level)

# getLogger(name)은 이름이 같으면 동일 싱글톤을 반환한다.
# 핸들러가 이미 붙어 있으면 재사용한다 — 매 호출마다 FileHandler를 중복
# 추가하면 열린 로그 파일이 누적되어 'Too many open files'(Errno 24)가
# 발생한다(그룹/매트릭스 저장처럼 WordCloudGenerator를 루프로 생성할 때).
if logger.handlers:
    return logger
```

## 5. 영향도 분석

- **변경 파일**: `wordcloud_project/utils/logger.py` (1개, 가드 1줄 추가).
- **영향 범위**: `setup_logger` 를 쓰는 **모든 모듈 로거**. 동작 변화는 "같은 이름 로거에
  두 번째 호출부터 핸들러를 안 붙인다" 뿐 — 로깅 출력은 동일(첫 설정 유지), 부작용 없음.
- **부수 효과(의도)**: WordCloudGenerator 인스턴스마다 만들던 타임스탬프 로그 파일 난립이 사라진다.
- **배포본 반영**: 본 수정은 소스(`wordcloud_project`)에만 적용됨. 에러 로그 경로
  `wordcloud-internal\...` 는 빌드 산출물이므로 `build_deploy.ps1` 재빌드 + 서버 재시작 필요.

## 6. 테스트/검증 계획

- [x] 단위: `setup_logger("wordcloud_generator", 임시경로)` 50회 호출 후 핸들러 수 확인
      → 핸들러 2개(콘솔1/파일1) 고정, FileHandler 1개. (수정 전이라면 100개로 누적)
- [ ] 실동작: 재빌드·재시작 후 행 수 많은 매트릭스/대량 그룹을 제출용 저장하여
      `Errno 24` 미발생 + 모든 셀 정상 저장 확인.
- [ ] FD 추세: 다건 저장 중 프로세스 열린 핸들 수가 평탄(누적 증가 없음) 확인.

## 7. 리스크 및 제약

- **동시성 미세 경합**: 병렬 스레드가 최초 1회 동시에 진입하면 가드 통과 전 핸들러가
  소수(스레드 수 이하) 중복될 수 있으나 **유한·소량**으로 누수 아님. 필요 시 후속으로
  모듈 로드시 1회 설정 방식으로 강화 가능(현 수정으로 누수는 해소).
- **제약**: 첫 호출의 log_file 경로가 해당 로거의 파일로 고정된다(이후 타임스탬프 파일 미생성).
  WordCloudGenerator 로깅은 진단용이라 무해.

## 8. 롤백 계획

- `utils/logger.py` 의 `if logger.handlers: return logger` 가드 3줄(주석 포함) 제거하면 원복.

## 9. 결과 (구현 완료 후 기재)

- **적용된 변경**: `utils/logger.py` 가드 추가 완료.
- **검증 결과**: 단위 검증 통과(50회 호출 후 핸들러 2개 고정). **실동작(배포본) 검증 전 → 상태 PND 유지.**
