"""KoTE 배치 추론 vs 개별 추론 성능 벤치마크 (독립 실행 스크립트)

목적:
    0617_07_hardware-adaptive-worker-plan 작업5(GPU 배치 추론)를 실제로 구현할
    가치가 있는지 판단하기 위한 순수 모델 forward-pass 시간 비교.
    실제 직원 데이터는 쓰지 않음(합성 한국어 문장만 사용) — dev/내부망 어디서나 실행 가능.

실행:
    python scripts/bench_kote_batch_inference.py            (wordcloud_project/ 루트에서)
    python scripts/bench_kote_batch_inference.py --n 500 --batch-sizes 1,4,8,16,32

출력 해석:
    - "문장 단위" 결과: sentence_emotion.py의 compute_sentence_raw_scores()가
      문서 내 문장마다 analyze_emotion()을 개별 호출하는 패턴을 흉내냄 (현재 호출량이 가장 많은 경로).
    - "평가문서 단위" 결과: metadata_manager.create_employee_metadata()가
      직원당 evaluations 리스트를 순회하며 analyze_emotion()을 호출하는 패턴(작업5가 원래 겨냥한 범위).
    - 배치 크기 1 대비 speedup이 거의 1.0x면 배치화 이득이 없다는 뜻 (CPU-bound 구간이거나
      모델이 너무 작아 커널 launch 오버헤드가 무시할 수준).
"""
import argparse
import os
import sys
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import torch  # noqa: E402

from src.modules.kote_shared import KoTEModel  # noqa: E402


SAMPLE_SENTENCES = [
    "업무 처리 속도가 빠르고 정확합니다.",
    "팀원들과의 협업 태도가 매우 우수합니다.",
    "가끔 의사소통에서 오해가 생기는 편입니다.",
    "맡은 일은 책임감 있게 끝까지 완수합니다.",
    "새로운 아이디어를 적극적으로 제안합니다.",
    "마감 기한을 자주 넘기는 경향이 있습니다.",
    "후배 직원을 잘 챙기고 멘토링에 적극적입니다.",
    "전반적으로 만족스러운 성과를 보여주었습니다.",
    "개선이 필요한 부분이 몇 가지 있습니다.",
    "고객 응대 시 침착하고 신뢰감을 줍니다.",
]


def make_sentences(n: int):
    return [SAMPLE_SENTENCES[i % len(SAMPLE_SENTENCES)] for i in range(n)]


def make_documents(n: int, sentences_per_doc: int = 8):
    docs = []
    for i in range(n):
        start = (i * sentences_per_doc) % len(SAMPLE_SENTENCES)
        chunk = [SAMPLE_SENTENCES[(start + j) % len(SAMPLE_SENTENCES)] for j in range(sentences_per_doc)]
        docs.append(" ".join(chunk))
    return docs


def run_sequential(model, tokenizer, texts):
    device = model.device
    if device.type == 'cuda':
        torch.cuda.synchronize()
    start = time.perf_counter()
    for text in texts:
        inputs = tokenizer(text, return_tensors="pt", truncation=True, padding=True, max_length=512)
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            model(**inputs)
    if device.type == 'cuda':
        torch.cuda.synchronize()
    return time.perf_counter() - start


def run_batched(model, tokenizer, texts, batch_size):
    device = model.device
    if device.type == 'cuda':
        torch.cuda.synchronize()
    start = time.perf_counter()
    for i in range(0, len(texts), batch_size):
        chunk = texts[i:i + batch_size]
        inputs = tokenizer(chunk, return_tensors="pt", truncation=True, padding=True, max_length=512)
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            model(**inputs)
    if device.type == 'cuda':
        torch.cuda.synchronize()
    return time.perf_counter() - start


def warmup(model, tokenizer, device):
    inputs = tokenizer(["워밍업 문장입니다."] * 4, return_tensors="pt", truncation=True, padding=True, max_length=512)
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        model(**inputs)
    if device.type == 'cuda':
        torch.cuda.synchronize()


def print_section(title, texts, model, tokenizer, batch_sizes):
    print(f"\n=== {title} (항목 수: {len(texts)}) ===")
    seq_time = run_sequential(model, tokenizer, texts)
    print(f"개별 호출(batch=1 동일):  총 {seq_time:.3f}s | 항목당 {seq_time / len(texts) * 1000:.2f}ms")

    for bs in batch_sizes:
        if bs <= 1 or bs > len(texts):
            continue
        batched_time = run_batched(model, tokenizer, texts, bs)
        speedup = seq_time / batched_time if batched_time > 0 else float('inf')
        print(f"배치 크기 {bs:>3}:          총 {batched_time:.3f}s | 항목당 {batched_time / len(texts) * 1000:.2f}ms | speedup {speedup:.2f}x")


def main():
    parser = argparse.ArgumentParser(description="KoTE 배치 추론 성능 벤치마크")
    parser.add_argument("--n", type=int, default=200, help="문장/문서 샘플 개수 (기본 200)")
    parser.add_argument("--sentences-per-doc", type=int, default=8, help="평가문서당 평균 문장 수 (기본 8)")
    parser.add_argument("--batch-sizes", type=str, default="1,4,8,16,32", help="비교할 배치 크기 목록 (쉼표 구분)")
    args = parser.parse_args()

    batch_sizes = [int(x) for x in args.batch_sizes.split(",")]

    print("KoTE 모델 로드 중...")
    shared = KoTEModel()
    model, tokenizer, device = shared.model, shared.tokenizer, shared.device
    print(f"device = {device}")
    if device.type == 'cuda':
        print(f"GPU: {torch.cuda.get_device_name(0)}, 총 VRAM: {torch.cuda.get_device_properties(0).total_memory / (1024**2):.0f}MB")
    else:
        print("⚠ CUDA 미사용 — CPU 결과는 GPU 배치 효과 판단 근거로 부적합")

    warmup(model, tokenizer, device)

    sentences = make_sentences(args.n)
    print_section("문장 단위 (sentence_emotion.py 패턴)", sentences, model, tokenizer, batch_sizes)

    documents = make_documents(max(args.n // 4, 10), args.sentences_per_doc)
    print_section("평가문서 단위 (작업5 원안 패턴)", documents, model, tokenizer, batch_sizes)

    print("\n해석 기준:")
    print("- 문장 단위 speedup이 평가문서 단위보다 훨씬 크면 → 작업5를 문서 단위로만 구현하는 것은 효과가 제한적,")
    print("  sentence_emotion.py의 문장 루프를 배치화해야 실제 이득이 큼.")
    print("- 모든 배치 크기에서 speedup이 1.0x 근처면 → 이 하드웨어/모델 크기에서는 배치화 이득이 미미함.")


if __name__ == "__main__":
    main()
