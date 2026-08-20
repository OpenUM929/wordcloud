"""요청·구간 소요시간 계측(20_06 / 20_09).

두 계획서 모두 "화면이 느리다"는 체감 보고만 있고 정적 코드 검토로는 후보를
더 좁힐 수 없는 상태에서 멈춰 있었다. 이 모듈은 가설(가명 역변환 대량 호출)이
맞는지 **그리고 틀렸다면 진짜 원인이 어디인지**를 같은 실행에서 동시에 드러내기
위한 계측이다.

- `install_request_timing(app)` — 모든 요청의 서버 처리시간을 1줄씩 남긴다.
  특정 라우트만 계측하면 "우리가 후보로 꼽지 않은 요청"(20_06 §2 가능성 1,
  정적 자원 포함)을 놓치므로 전역으로 건다.
- `perf_span(name)` — 한 요청 안의 구간(SQL / 가명 역변환 / 조립)을 쪼개 잰다.
  서버 총 시간이 느릴 때 그 안의 어느 구간인지 바로 나온다.

브라우저 쪽 짝은 `web/static/js/perf_probe.js`(콘솔 출력)다. 서버 로그의 ms와
브라우저 콘솔의 ms를 대조하면 지연이 서버·네트워크·렌더 중 어디인지 갈린다.

계측은 로그만 남기고 어떤 반환값·동작도 바꾸지 않는다. 계측 자체가 실패해도
요청은 정상 진행되어야 하므로 모든 경로를 예외로부터 격리한다.
"""
import time
from contextlib import contextmanager

from utils.logger import get_pipeline_logger

logger = get_pipeline_logger()

# 이 값을 넘으면 WARNING 으로 올려 로그에서 눈에 띄게 한다(콘솔 핸들러가 INFO라
# 콘솔에도 뜬다). 체감 지연의 하한을 넉넉히 잡은 값.
SLOW_MS = 300.0


def _emit(stage, message, ms):
    try:
        level = logger.warning if ms >= SLOW_MS else logger.info
        level('%s ms=%.1f', message, ms, extra={'request_id': '', 'stage': stage})
    except Exception:
        pass


@contextmanager
def perf_span(name, **fields):
    """구간 소요시간을 로그로 남긴다. 예외가 나도 소요시간은 남기고 그대로 전파."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        ms = (time.perf_counter() - t0) * 1000.0
        extra = ' '.join(f'{k}={v}' for k, v in fields.items())
        _emit('PERF', f'span={name}' + (f' {extra}' if extra else ''), ms)


def install_request_timing(app):
    """모든 HTTP 요청의 서버 처리시간을 남기는 훅을 앱에 건다.

    남기는 값: 메서드·경로·상태코드·응답크기·소요 ms. 브라우저에서 체감한
    시간이 이 값보다 훨씬 크면 원인은 서버 코드가 아니라 네트워크 구간이거나
    브라우저 렌더링이라는 뜻이므로, 그 자체가 유효한 진단 정보다.
    """
    from flask import g, request

    @app.before_request
    def _perf_request_start():
        try:
            g._perf_t0 = time.perf_counter()
        except Exception:
            pass

    @app.after_request
    def _perf_request_end(response):
        try:
            t0 = getattr(g, '_perf_t0', None)
            if t0 is not None:
                ms = (time.perf_counter() - t0) * 1000.0
                size = response.content_length
                _emit(
                    'PERF_REQ',
                    'method=%s path=%s status=%s bytes=%s' % (
                        request.method, request.path, response.status_code,
                        size if size is not None else '-'),
                    ms,
                )
        except Exception:
            pass
        return response

    return app
