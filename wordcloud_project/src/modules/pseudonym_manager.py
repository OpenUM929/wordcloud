import os
import json
import uuid
import base64
import hashlib
import threading
from contextlib import contextmanager
from datetime import datetime
from utils.logger import get_pipeline_logger, _mask_real_id

logger = get_pipeline_logger()

PSEUDONYM_PREFIX = "평가자_"

def _derive_key(master_password):
    return base64.urlsafe_b64encode(
        hashlib.pbkdf2_hmac('sha256', master_password.encode('utf-8'), b'pseudonym_salt', 100000, dklen=32)
    )


class PseudonymManager:
    def __init__(self, mappings_path, master_password):
        self.mappings_path = mappings_path
        self._key = _derive_key(master_password)
        self._fernet = None
        self._mapping_cache = None
        self._lock = threading.RLock()
        # 일괄 저장 모드 상태: bulk_mode() 블록 동안 per-ID 저장을 보류
        self._defer_save = False
        self._dirty = False

    @property
    def _cipher(self):
        if self._fernet is None:
            from cryptography.fernet import Fernet
            self._fernet = Fernet(self._key)
        return self._fernet

    def _load_mappings(self):
        with self._lock:
            if self._mapping_cache is not None:
                logger.debug("cache_hit=True", extra={'request_id': '', 'stage': 'PSEUDO_LOAD'})
                return self._mapping_cache
            if not os.path.exists(self.mappings_path):
                logger.warning("file_not_found creating_empty", extra={'request_id': '', 'stage': 'PSEUDO_LOAD'})
                self._mapping_cache = {"real_to_pseudo": {}, "pseudo_to_real": {}}
                return self._mapping_cache
            logger.info("path=%s", self.mappings_path, extra={'request_id': '', 'stage': 'PSEUDO_LOAD'})
            try:
                with open(self.mappings_path, 'rb') as f:
                    encrypted = f.read()
                decrypted = self._cipher.decrypt(encrypted)
                data = json.loads(decrypted.decode('utf-8'))
                self._mapping_cache = data
                return data
            except Exception as e:
                logger.error("decrypt_failed error=%s", e, extra={'request_id': '', 'stage': 'PSEUDO_LOAD'})
                self._mapping_cache = {"real_to_pseudo": {}, "pseudo_to_real": {}}
                return self._mapping_cache

    def _read_disk_mappings(self):
        """저장 직전 디스크 매핑을 캐시 무시하고 직접 복호화. 없거나 실패 시 None."""
        path_exists = os.path.exists(self.mappings_path)
        logger.debug("path=%s exists=%s", self.mappings_path, path_exists, extra={'request_id': '', 'stage': 'PSEUDO_DISK'})
        if not path_exists:
            return None
        try:
            with open(self.mappings_path, 'rb') as f:
                return json.loads(self._cipher.decrypt(f.read()).decode('utf-8'))
        except Exception:
            return None

    def _save_mappings(self, data):
        with self._lock:
            # 🔴 데이터 보호(append-only): 저장은 항상 디스크의 기존 매핑과 병합한다.
            # 캐시가 비거나 부분이어도(로드 실패·경합 등) 기존 가명이 통째로 소실되지 않게 한다.
            data = data or {}
            real_count = len(data.get('real_to_pseudo', {}))
            pseudo_count = len(data.get('pseudo_to_real', {}))
            logger.info("real_count=%s pseudo_count=%s", real_count, pseudo_count, extra={'request_id': '', 'stage': 'PSEUDO_SAVE'})
            disk = self._read_disk_mappings()
            if disk is None and os.path.exists(self.mappings_path) \
                    and os.path.getsize(self.mappings_path) > 0:
                # 파일은 있는데 복호화 실패 → 덮어쓰기 전 원본 백업(복구 가능하게)
                try:
                    import shutil
                    shutil.copy2(self.mappings_path, self.mappings_path + '.corrupt.bak')
                except Exception:
                    pass
            if disk:
                # 기존(disk) 위에 신규(data)를 덧씌움 — 동일 real_id는 같은 가명이라 무손실.
                data = {
                    'real_to_pseudo': {**disk.get('real_to_pseudo', {}),
                                       **data.get('real_to_pseudo', {})},
                    'pseudo_to_real': {**disk.get('pseudo_to_real', {}),
                                       **data.get('pseudo_to_real', {})},
                }
            self._mapping_cache = data
            raw = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
            try:
                encrypted = self._cipher.encrypt(raw)
            except Exception as e:
                logger.error("encrypt_failed error=%s", e, extra={'request_id': '', 'stage': 'PSEUDO_SAVE'})
                return
            os.makedirs(os.path.dirname(self.mappings_path), exist_ok=True)
            logger.debug("file_size=%s", len(encrypted), extra={'request_id': '', 'stage': 'PSEUDO_SAVE'})
            # 원자적 파일 쓰기: 임시 파일 → os.replace() (Windows 호환)
            tmp_path = self.mappings_path + '.tmp'
            with open(tmp_path, 'wb') as f:
                f.write(encrypted)
            os.replace(tmp_path, self.mappings_path)

    def _maybe_save(self, data):
        """일괄 모드면 저장을 보류(dirty 표시)하고, 아니면 즉시 저장한다.

        대용량 배치에서 새 가명마다 파일 전체를 재암호화·재기록하던 O(n²)
        병목을 제거하기 위함. 기본값(_defer_save=False)은 종전 즉시 저장 동작.
        """
        with self._lock:
            if self._defer_save:
                self._dirty = True
            else:
                self._save_mappings(data)

    @contextmanager
    def bulk_mode(self):
        """블록 동안 새 가명을 메모리(_mapping_cache)에만 누적하고, 종료 시 1회 저장.

        정상/예외 종료 모두 finally에서 flush 되므로 블록을 빠져나오면
        그때까지 생성된 모든 매핑이 디스크에 반영된다.
        """
        logger.info("mode=enter", extra={'request_id': '', 'stage': 'PSEUDO_BULK'})
        with self._lock:
            self._defer_save = True
        try:
            yield self
        finally:
            with self._lock:
                self._defer_save = False
                if self._dirty:
                    self._save_mappings(self._mapping_cache)
                    self._dirty = False
            logger.info("mode=exit", extra={'request_id': '', 'stage': 'PSEUDO_BULK'})

    def flush(self):
        """보류된 변경(_dirty)을 즉시 디스크에 반영한다."""
        logger.info("dirty=%s", self._dirty, extra={'request_id': '', 'stage': 'PSEUDO_FLUSH'})
        with self._lock:
            if self._dirty:
                self._save_mappings(self._mapping_cache)
                self._dirty = False

    def get_pseudonym(self, real_id):
        if not real_id or not str(real_id).strip():
            logger.warning("empty_input=True", extra={'request_id': '', 'stage': 'PSEUDO_GET'})
            return real_id
        real_id = str(real_id).strip()
        # 🔴 멱등화: 이미 가명(평가자_XXXXXX)인 값은 다시 가명화하지 않고 그대로 반환한다.
        # 실사번은 PSEUDONYM_PREFIX로 시작할 수 없으므로 안전하며, 이중 가명화를 원천 차단한다.
        if real_id.startswith(PSEUDONYM_PREFIX):
            logger.info("already_pseudonym passthrough real_id=%s", real_id,
                        extra={'request_id': '', 'stage': 'PSEUDO_GET'})
            return real_id
        logger.info("real_id=%s", _mask_real_id(real_id), extra={'request_id': '', 'stage': 'PSEUDO_GET'})
        with self._lock:
            data = self._load_mappings()
            if real_id in data["real_to_pseudo"]:
                pseudo = data["real_to_pseudo"][real_id]
                logger.debug("existing_mapping=True pseudo=%s", pseudo, extra={'request_id': '', 'stage': 'PSEUDO_GET'})
                return pseudo
            pseudo = f"{PSEUDONYM_PREFIX}{uuid.uuid4().hex[:6].upper()}"
            data["real_to_pseudo"][real_id] = pseudo
            data["pseudo_to_real"][pseudo] = real_id
            self._maybe_save(data)
            logger.info("new_pseudo=True pseudo=%s", pseudo, extra={'request_id': '', 'stage': 'PSEUDO_GET'})
            return pseudo

    def get_real_id(self, pseudonym):
        if not pseudonym or not str(pseudonym).strip():
            return pseudonym
        pseudonym = str(pseudonym).strip()
        # 20_09 §3.1: 대량 호출 구간(직원 1.9만명×최대4필드)에서 매 호출 무조건 로깅되던 것을
        # debug로 낮춤(반환값·매핑 로직 불변, 로깅 레벨만 변경). found=False는 미가명화 값의
        # 정상 경로라 anomaly 아님 — warning은 과다 로깅 원인이라 판단해 함께 낮춤.
        logger.debug("pseudo=%s", pseudonym, extra={'request_id': '', 'stage': 'PSEUDO_REAL'})
        with self._lock:
            data = self._load_mappings()
            real = data["pseudo_to_real"].get(pseudonym, pseudonym)
            if real != pseudonym:
                logger.debug("found=True real_id=%s", _mask_real_id(real), extra={'request_id': '', 'stage': 'PSEUDO_REAL'})
            else:
                logger.debug("found=False returned_as_is=%s", pseudonym, extra={'request_id': '', 'stage': 'PSEUDO_REAL'})
            return real

    def get_real_id_map(self):
        """대량 역변환용 스냅샷 — pseudo→real 매핑의 얕은 복사본을 락 1회로 반환.

        20_09 §3.2: 목록 응답(직원 1.9만명 × 최대 4필드)에서 get_real_id()를
        건건이 부르면 락 획득·로깅이 최대 7.6만 회 누적된다. 호출부가 이 스냅샷을
        받아 로컬 dict 조회로 역변환하면 같은 결과를 락 1회로 얻는다.

        - 복사본을 주는 이유: 내부 캐시(_mapping_cache)를 그대로 넘기면 호출부가
          매핑 원본을 건드릴 수 있다. 가명 매핑은 절대 규칙 대상이라 읽기 전용
          사본만 내보낸다.
        - 이 스냅샷은 호출 시점의 값이다. 역변환(조회) 전용이며, 새 가명을
          만드는 경로(get_pseudonym)에는 쓰지 않는다.
        """
        with self._lock:
            data = self._load_mappings()
            return dict(data["pseudo_to_real"])

    def link_mapping(self, pseudonym, real_id):
        with self._lock:
            data = self._load_mappings()
            data["real_to_pseudo"][real_id] = pseudonym
            data["pseudo_to_real"][pseudonym] = real_id
            self._maybe_save(data)

    def get_all_mappings(self):
        with self._lock:
            data = self._load_mappings()
            return list(data["real_to_pseudo"].items())

    def apply_pseudonyms_to_dict(self, d, fields):
        with self._lock:
            result = {}
            for k, v in d.items():
                if k in fields and isinstance(v, str):
                    result[k] = self.get_pseudonym(v)
                else:
                    result[k] = v
            return result

    def restore_pseudonyms_in_dict(self, d, fields):
        with self._lock:
            result = {}
            for k, v in d.items():
                if k in fields and isinstance(v, str):
                    result[k] = self.get_real_id(v)
                else:
                    result[k] = v
            return result
