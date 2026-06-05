import os
import json
import uuid
import base64
import hashlib
import threading
from datetime import datetime

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

    @property
    def _cipher(self):
        if self._fernet is None:
            from cryptography.fernet import Fernet
            self._fernet = Fernet(self._key)
        return self._fernet

    def _load_mappings(self):
        with self._lock:
            if self._mapping_cache is not None:
                return self._mapping_cache
            if not os.path.exists(self.mappings_path):
                self._mapping_cache = {"real_to_pseudo": {}, "pseudo_to_real": {}}
                return self._mapping_cache
            try:
                with open(self.mappings_path, 'rb') as f:
                    encrypted = f.read()
                decrypted = self._cipher.decrypt(encrypted)
                data = json.loads(decrypted.decode('utf-8'))
                self._mapping_cache = data
                return data
            except Exception:
                self._mapping_cache = {"real_to_pseudo": {}, "pseudo_to_real": {}}
                return self._mapping_cache

    def _save_mappings(self, data):
        with self._lock:
            self._mapping_cache = data
            raw = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
            encrypted = self._cipher.encrypt(raw)
            os.makedirs(os.path.dirname(self.mappings_path), exist_ok=True)
            # 원자적 파일 쓰기: 임시 파일 → os.replace() (Windows 호환)
            tmp_path = self.mappings_path + '.tmp'
            with open(tmp_path, 'wb') as f:
                f.write(encrypted)
            os.replace(tmp_path, self.mappings_path)

    def get_pseudonym(self, real_id):
        if not real_id or not str(real_id).strip():
            return real_id
        real_id = str(real_id).strip()
        with self._lock:
            data = self._load_mappings()
            if real_id in data["real_to_pseudo"]:
                return data["real_to_pseudo"][real_id]
            pseudo = f"{PSEUDONYM_PREFIX}{uuid.uuid4().hex[:6].upper()}"
            data["real_to_pseudo"][real_id] = pseudo
            data["pseudo_to_real"][pseudo] = real_id
            self._save_mappings(data)
            return pseudo

    def get_real_id(self, pseudonym):
        if not pseudonym or not str(pseudonym).strip():
            return pseudonym
        pseudonym = str(pseudonym).strip()
        with self._lock:
            data = self._load_mappings()
            return data["pseudo_to_real"].get(pseudonym, pseudonym)

    def link_mapping(self, pseudonym, real_id):
        with self._lock:
            data = self._load_mappings()
            data["real_to_pseudo"][real_id] = pseudonym
            data["pseudo_to_real"][pseudonym] = real_id
            self._save_mappings(data)

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
