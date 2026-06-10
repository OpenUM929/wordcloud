# 내부망 오프라인 설치 가이드

> 버전: 2026-06-09
> 가정: Python 미설치, 인터넷 없음, CUDA 12.4

---

## 1. 준비물 (USB/외장하드 등으로 전달)

| 항목 | 크기 | 설명 |
|------|------|------|
| `wordcloud_internal.zip` | **~6-7GB** | 루트 폴더 전체 압축본 |

### 포함 내용
- `venv/` — Python 3.10 + torch, transformers, flask 등 150+ 패키지 (5.8GB)
- `model/` — KoTE + Sarcasm 모델 (953MB)
- `wordcloud_project/` — 소스코드 + 설정 + 템플릿
- `start.bat` — 더블클릭 실행용 Windows 배치파일

---

## 2. 설치 방법 (3단계)

### 단계 1: 동일한 경로에 압축 해제

```
D:\dev\wordcloud\
```

> ⚠️ **중요**: 반드시 `D:\dev\wordcloud\` 경로에 압축 해제하세요.
> `venv` 내부의 경로 참조가 절대경로로 되어 있어, 다른 경로에서는 실행이 안 될 수 있습니다.

### 단계 2: 실행

`D:\dev\wordcloud\start.bat` 더블클릭

또는 PowerShell/CMD:
```powershell
cd D:\dev\wordcloud
.\venv\Scripts\python.exe -m web.app
```

### 단계 3: 브라우저 접속

http://127.0.0.1:5001

---

## 3. 주의사항

| 항목 | 설명 |
|------|------|
| **경로** | `D:\dev\wordcloud\`로 압축 해제해야 함. 다른 경로로 옮기면 `venv` 깨짐 |
| **CUDA** | GPU 사용 시 내부 서버에 **CUDA 12.4** 및 NVIDIA 드라이버 설치 필요 |
| **JDK** | `konlpy` 사용 시 Java JDK 설치 필요 (없으면 `konlpy` 기능만 비활성화됨) |
| **OS** | Windows 10/11 가정 (Python 3.10 기준) |

---

## 4. 문제 해결

### 경로를 다르게 압축 해제한 경우
```powershell
# venv 경로 수정 (PowerShell 관리자 권한)
(Get-Content venv\pyvenv.cfg) -replace 'D:\\dev\\wordcloud\\wordcloud_project', 'C:\\새경로\\wordcloud_project' | Set-Content venv\pyvenv.cfg
```

### konlpy 오류 (JDK 없음)
- `kiwipiepy`만 사용하도록 설정: `configs/nlp_config.json`에서 `"use_konlpy": false`

### torch CUDA 인식 실패
- CPU 모드로 실행: `.env` 파일에 `CUDA_VISIBLE_DEVICES=-1` 추가

---

## 5. 파일 구조

```
D:\dev\wordcloud\
├── start.bat                  ← 실행 파일
├── wordcloud_project\
│   ├── venv\                  ← Python + 패키지 전체
│   ├── web\app.py              ← Flask 진입점
│   ├── src\                    ← 소스코드
│   ├── web\templates\          ← HTML 템플릿
│   ├── configs\                ← 설정파일
│   └── vendor_python_pkgs\    ← (참고용) .whl 백업
├── model\
│   ├── kote_for_easygoing_people\    ← 감정 분석 모델
│   └── fine_tune\fine_tuned_sarcasm_model_cuda\  ← 반어법 모델
├── outputs\                    ← 결과물 저장
├── logs\                      ← 로그 저장
└── backup_20260609_unused\    ← (삭제된 파일 백업)
```

---

*Prepared: 2026-06-09*
