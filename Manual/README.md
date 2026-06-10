# 워드클라우드 시스템 — 내부망 오프라인 설치 메뉴얼

> 버전: 2026-06-09
> 대상: 내부망 PC (인터넷 불가, Python 미설치 가정)

---

## 0. 압축 파일 포함 내용 (별도 설치 불필요)

본 압축 파일에는 **내부망 실행에 필요한 모든 것이 포함**되어 있습니다. 별도 설치가 필요한 것은 **없습니다**.

| 포함 항목 | 설명 | 크기 |
|-----------|------|------|
| `venv\` | Python 3.10 + torch, transformers, flask 등 150+ 패키지 | 5.8GB |
| `model\` | 감정 분석(KoTE) + 반어법(Sarcasm) AI 모델 | 953MB |
| `wordcloud_project\` | 전체 소스코드, HTML 템플릿, 설정 파일 | ~100MB |
| `start.bat` | 더블클릭 실행 파일 | 1KB |

**별도 설치가 필요한 것 (2가지)**:
1. NVIDIA 그래픽 드라이버 (GPU 사용 시에만 필요)
2. JDK (Java) — `konlpy` 기능 사용 시 선택사항

> ✅ Python, pip, torch, CUDA 라이브러리 등 모두 이미 포함되어 있습니다.

---

## 1. 설치 전 확인사항

### 1.1 하드웨어 요구사항

| 항목 | 최소사양 | 권장사양 |
|------|----------|----------|
| OS | Windows 10/11 64bit | Windows 10/11 64bit |
| RAM | 8GB | 16GB 이상 |
| 디스크 | 10GB 여유 | 15GB 이상 |
| GPU | NVIDIA GTX 1060 (6GB) | NVIDIA RTX 3060 이상 |
| CUDA | 12.4 (드라이버만 설치) | 12.4 (드라이버만 설치) |

### 1.2 사전 설치 필요 항목 (반드시 먼저 설치)

| 항목 | 설치 방법 | 비고 |
|------|-----------|------|
| **NVIDIA 그래픽 드라이버** | [nvidia.com](https://www.nvidia.com/Download/index.aspx) 에서 해당 GPU 모델 선택 후 다운로드 | GPU 사용 시 필수 |
| **JDK (Java)** | `konlpy` 사용 시 필요. 없으면 `konlpy` 기능만 비활성화됨 | 선택사항 |

> 💡 **CUDA 관련**: PyTorch CUDA 라이브러리(CUDA 12.4)는 이미 `venv` 내부에 포함되어 있습니다. GPU 사용 시에는 **NVIDIA 드라이버만 별도 설치**하면 됩니다. CUDA Toolkit, cuDNN 등은 별도 설치 불필요.

> ⚠️ **Python, pip, torch 등은 이미 압축 파일에 포함되어 있으므로 별도 설치 불필요**

---

## 2. 설치 방법 (3단계)

### 단계 1: 압축 해제

**반드시 아래 경로에 압축 해제하세요.**

```
D:\dev\wordcloud\
```

> ⚠️ **중요**: `D:\dev\wordcloud\` 이외의 경로(`C:\`, `D:\work\` 등)에 압축 해제하면 실행되지 않습니다.
> venv 내부의 경로 참조가 절대경로로 되어 있어서, 다른 위치로 옮기면 깨집니다.

### 단계 2: 방법1 — 실행 (더블클릭) ← 먼저 시도

**순서: 방법1 → (안되면) 방법2**

`D:\dev\wordcloud\start.bat` 파일을 **더블클릭**합니다.

```
D:\dev\wordcloud\
├── start.bat          ← 더블클릭!
├── Manual\
│   └── README.md      ← 이 설치 메뉴얼
├── wordcloud_project\
│   └── venv\          ← Python + 모든 패키지
├── model\             ← AI 모델
└── ...
```

실행 후 자동으로:
1. Python 인터프리터 확인
2. Flask 서버 기동 (http://127.0.0.1:5001)
3. 브라우저에서 `http://127.0.0.1:5001` 접속

### 단계 3: 방법2 — 실행 (명령어) ← 방법1 실패 시

방법1이 안 될 경우에만 아래 명령어를 실행합니다.

**PowerShell:**
```powershell
cd D:\dev\wordcloud
.\wordcloud_project\venv\Scripts\python.exe -m web.app
```

**CMD:**
```batch
D:
cd D:\dev\wordcloud
wordcloud_project\venv\Scripts\python.exe -m web.app
```

> ⚠️ **반드시 방법1을 먼저 시도하세요. 방법2는 방법1이 실패할 때만 사용합니다.**

---

## 3. 접속 방법

서버 기동 후, 브라우저에서 아래 주소로 접속합니다.

```
http://127.0.0.1:5001
```

---

## 4. 문제 해결

### Q1. `D:` 드라이브가 없으면 어떻게 하나요?

USB 등으로 파일을 `D:` 드라이브에 복사하거나, `C:` 드라이브에 설치 시 경로 수정이 필요합니다.

```powershell
# PowerShell (관리자 권한)
# venv 경로를 C:\dev\wordcloud\ 로 수정
(Get-Content wordcloud_project\venv\pyvenv.cfg) -replace 'D:\\dev\\wordcloud', 'C:\\dev\\wordcloud' | Set-Content wordcloud_project\venv\pyvenv.cfg

# 또는 새로운 venv 생성
# cd C:\dev\wordcloud\wordcloud_project
# python -m venv venv
# .\venv\Scripts\pip install --no-index --find-links vendor_python_pkgs -r requirements.txt
```

### Q2. GPU가 인식되지 않나요?

```powershell
# PowerShell에서 확인
.\wordcloud_project\venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available())"
```

- `True`가 나오면 GPU 사용 중
- `False`가 나오면 CPU 모드로 실행 (속도는 느리지만 정상 작동)

### Q3. `konlpy` 오류가 나나요?

Java JDK가 설치되지 않아도 `kiwipiepy`는 정상 작동합니다.

`konlpy` 기능이 필요한 경우:
1. 내부망에 JDK 설치 (Oracle 또는 OpenJDK)
2. 환경변수 `JAVA_HOME` 설정

---

## 5. 파일 구조

```
D:\dev\wordcloud\                          ← 반드시 이 경로
├── start.bat                               ← 방법1: 더블클릭 실행
├── Manual\                                 ← 설치 메뉴얼 폴더
│   └── README.md                           ← 이 파일
├── wordcloud_project\                      ← 프로젝트 소스
│   ├── venv\                               ← Python 3.10 + 모든 패키지 (5.8GB)
│   ├── web\app.py                           ← Flask 진입점
│   ├── src\                                 ← 소스코드
│   ├── web\templates\                      ← HTML 템플릿
│   ├── configs\                            ← 설정파일
│   ├── vendor_python_pkgs\                  ← (참고용) .whl 파일들
│   └── scripts\                             ← 유틸리티 스크립트
├── model\                                   ← AI 모델
│   ├── kote_for_easygoing_people\           ← 감정 분석 모델 (KoTE)
│   └── fine_tune\fine_tuned_sarcasm_model_cuda\  ← 반어법 모델
├── outputs\                                ← 결과물 저장
├── logs\                                    ← 로그 저장
└── backup_20260609_unused\                  ← (참고) 삭제된 파일 백업
```

---

## 6. 연락처

| 항목 | 내용 |
|------|------|
| 문의 | 개발팀 |
| 버전 | 2026-06-09 |
| 최종 수정 | 2026-06-09 |

---

*본 메뉴얼은 내부망 오프라인 환경을 가정하여 작성되었습니다.*
