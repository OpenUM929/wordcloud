# WordCloud Project

한국어 인사평가 문서 감정 분석 및 워드클라우드 생성 시스템

## 설치

### 개발 모드 (editable)

```bash
cd wordcloud_project
pip install -e .
```

### 일반 설치

```bash
cd wordcloud_project
pip install .
```

### 개발 도구 포함

```bash
pip install -e ".[dev]"
```

## 실행

### 개발 서버

```bash
# 방법 1 — entry point
wordcloud-server

# 방법 2 — Flask CLI
flask --app web.app run --port 5001 --host 127.0.0.1

# 방법 3 — 직접 실행
python -m web.app
```

### 프로덕션 (gunicorn)

```bash
pip install -e ".[prod]"
gunicorn -w 1 -b 127.0.0.1:5001 "web.app:create_app()"
```

## 환경 변수

`.env` 파일 또는 환경 변수로 설정:

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `FLASK_DEBUG` | `false` | 디버그 모드 |
| `FLASK_PORT` | `5001` | 포트 번호 |
| `FLASK_HOST` | `127.0.0.1` | 호스트 주소 |
| `SECRET_KEY` | `your_secret_key_here` | Flask 시크릿 키 |
| `ADMIN_PASSWORD` | `admin1234` | 관리자 비밀번호 |
| `MODEL_DIR` | `model` | 모델 디렉토리 |
| `OUTPUTS_DIR` | `outputs` | 출력 디렉토리 |

## 패키지 빌드

```bash
# 소스 배포판
python -m build --sdist

# 휠 배포판
python -m build --wheel

# 설치 테스트
pip install dist/wordcloud_project-*.whl
```
