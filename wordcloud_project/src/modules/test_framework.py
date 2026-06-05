from dataclasses import dataclass, field
from typing import Callable, Dict, Any, List
import time

@dataclass
class TestCase:
    id: str
    input: str
    expected: Any
    category: str
    description: str = ""

@dataclass
class TestResult:
    case_id: str
    input: str
    expected: Any
    actual: Any
    match: bool
    processing_time_ms: int
    details: Dict[str, Any] = field(default_factory=dict)

class TestRunner:
    """공통 테스트 실행기. executor에 실제 분석 함수를 주입받아 동작."""
    
    def __init__(self, test_type: str, executor: Callable[[str, Dict], Dict]):
        self.test_type = test_type
        self.executor = executor
    
    def run_single(self, text: str, **params) -> Dict[str, Any]:
        """단일 실행"""
        start = time.time()
        actual = self.executor(text, params)
        elapsed = int((time.time() - start) * 1000)
        return {
            "test_type": self.test_type,
            "mode": "single",
            "input": text,
            "actual": actual,
            "processing_time_ms": elapsed,
        }
    
    def run_batch(self, cases: List[TestCase], **params) -> Dict[str, Any]:
        """배치 실행 → 통계 자동 계산"""
        results: List[TestResult] = []
        passed = 0
        total_time = 0
        
        for case in cases:
            start = time.time()
            actual = self.executor(case.input, params)
            elapsed = int((time.time() - start) * 1000)
            total_time += elapsed
            
            match = self._compare(actual, case.expected)
            if match:
                passed += 1
            
            results.append(TestResult(
                case_id=case.id,
                input=case.input,
                expected=case.expected,
                actual=actual,
                match=match,
                processing_time_ms=elapsed,
                details=actual
            ))
        
        total = len(cases)
        return {
            "success": True,
            "test_type": self.test_type,
            "mode": "batch",
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "accuracy": round(passed / total * 100, 2) if total > 0 else 0,
            "total_time_ms": total_time,
            "avg_time_ms": round(total_time / total, 1) if total > 0 else 0,
            "results": [vars(r) for r in results],
        }
    
    def _compare(self, actual: Dict, expected: Any) -> bool:
        """실제 결과와 기대값 비교. 테스트 유형별 오버라이드 가능."""
        if isinstance(expected, dict):
            for key, val in expected.items():
                if actual.get(key) != val:
                    return False
            return True
        return actual == expected
