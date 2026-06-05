/**
 * WordCloudPreset.js
 * localStorage 기반 워드클라우드 설정 프리셋 관리.
 * 모든 페이지에서 동일한 키(wc_presets)를 공유하므로
 * 한 페이지에서 저장한 프리셋을 다른 페이지에서 바로 불러올 수 있음.
 */
class WordCloudPreset {
    static _KEY = 'wc_presets';
    static _LAST_KEY = 'wc_last_preset_id';

    static list() {
        try {
            return JSON.parse(localStorage.getItem(this._KEY) || '[]');
        } catch {
            return [];
        }
    }

    /**
     * 프리셋 저장. 동일한 이름이 있으면 덮어씀.
     * @param {string} name
     * @param {object} options
     * @returns {string} id
     */
    static save(name, options) {
        const presets = this.list();
        const existing = presets.findIndex(p => p.name === name);
        const id = existing >= 0 ? presets[existing].id : String(Date.now());
        const entry = { id, name, savedAt: new Date().toISOString(), options };
        if (existing >= 0) presets[existing] = entry;
        else presets.push(entry);
        localStorage.setItem(this._KEY, JSON.stringify(presets));
        return id;
    }

    /**
     * @param {string} id
     * @returns {{id, name, savedAt, options}|null}
     */
    static load(id) {
        return this.list().find(p => p.id === id) || null;
    }

    /** @param {string} id */
    static delete(id) {
        const filtered = this.list().filter(p => p.id !== id);
        localStorage.setItem(this._KEY, JSON.stringify(filtered));
    }

    static setLastUsed(id) {
        try { localStorage.setItem(this._LAST_KEY, id || ''); } catch {}
    }

    static getLastUsed() {
        try { return localStorage.getItem(this._LAST_KEY) || ''; } catch { return ''; }
    }

    // ── UI 헬퍼 ────────────────────────────────────────────────────────────────

    /**
     * <select> 엘리먼트를 저장된 프리셋 목록으로 채움.
     * @param {HTMLSelectElement} selectEl
     */
    static populateSelect(selectEl) {
        const current = selectEl.value;
        selectEl.innerHTML = '<option value="">-- 저장된 프리셋 --</option>';
        this.list().forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = p.name;
            selectEl.appendChild(opt);
        });
        if (current) selectEl.value = current;
    }
}
