# -*- coding: utf-8 -*-
"""13_03 Track2 단위테스트 — apply_model_label_override (프로덕션 함수 직접 검증).

실행: cd wordcloud_project && python plans/2026/07/13_03_rule-alignment/test/test_override_guard.py
(pytest 불요 — assert 기반 자기완결. 통과 시 'ALL PASS' 출력, 실패 시 AssertionError.)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WP = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..', '..'))
sys.path.insert(0, WP)

from src.services.perspective_service import apply_model_label_override as ov

# (model_label, sentence, field) -> expected
CASES = [
    # ── R1 발동: 요청표지 화행에서 모델이 거짓 긍정 → 중립화(긍↔부 불생성) ──
    ('positive', '적극적으로 의견을 수렴해 주세요', '단점', 'neutral', 'R1: ~해주세요'),
    ('positive', '더 소통하려는 노력을 바랍니다', '단점', 'neutral', 'R1: 바랍니다'),
    ('positive', '개선되었으면 좋겠습니다', '단점', 'neutral', 'R1: 희망형'),

    # ── R1 미발동(트랩 보호): 긍정어가 요청표지로 오인되면 안 됨 ──
    ('positive', '하고자 하는 일에 대하여 집요함', '장점', 'positive', 'trap: 집요함≠요함'),
    ('positive', '매우 중요함', '장점', 'positive', 'trap: 중요함≠요함'),
    ('positive', '직원들과 의사소통이 원활합니다', '장점', 'positive', '평범한 긍정 보존'),

    # ── R1 미발동(명시 강긍정 보호): 요청표지가 있어도 강한 칭찬이면 긍정 유지 ──
    ('positive', '업무가 매우 뛰어나니 지금처럼 해주세요', '장점', 'positive', '강긍정 보호'),

    # ── 모델 부정/중립은 절대 안 건드림(부→긍/중→부 override 없음 = 긍↔부 안전) ──
    ('negative', '의견을 수렴해 주세요', '단점', 'negative', '모델 부정 보존'),
    ('neutral', '관리 감독 없이 업무 수행', '장점', 'neutral', '모델 중립 보존(R2 폐기)'),
    ('negative', '직원들과 의사소통이 원활합니다', '장점', 'negative', '모델 부정 절대보존(부→긍 없음)'),

    # ── 빈 입력 방어 ──
    ('positive', '', '장점', 'positive', '빈 문장'),
    ('positive', None, '단점', 'positive', 'None 문장'),
]


def main():
    fails = []
    for ml, sent, field, exp, desc in CASES:
        got = ov(ml, sent, field)
        ok = (got == exp)
        print(f'  [{"OK " if ok else "FAIL"}] {ml:8s} -> {got:8s} (exp {exp:8s}) | {desc}')
        if not ok:
            fails.append((desc, ml, sent, exp, got))
    # 불변식: R1은 절대 'negative'를 반환하지 않는다(긍→부 금지 = 긍↔부 불생성)
    for ml, sent, field, exp, desc in CASES:
        got = ov(ml, sent, field)
        assert not (ml == 'positive' and got == 'negative'), f'긍→부 위반! {desc}'
        assert not (ml in ('negative', 'neutral') and got != ml), f'모델 부정/중립 변경! {desc}'
    print('── 불변식: 긍→부 0 · 모델 부정/중립 불변 확인 ──')
    if fails:
        raise AssertionError(f'{len(fails)}건 실패: {[f[0] for f in fails]}')
    print(f'ALL PASS ({len(CASES)} cases)')


if __name__ == '__main__':
    main()
