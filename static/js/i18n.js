/* ═══════════════════════════════════════════════════════════════════════
   Re-Life — i18n Loader
   Fetches i18n/{lang}.json, caches it, exposes tr(key).
   ═══════════════════════════════════════════════════════════════════════ */

const I18N = (() => {
    const ASSET_SUFFIX = '.json?v=20260719-agent4';
    let _strings = {};       // current language strings
    let _currentLang = 'en';
    let _loaded = false;

    function getNestedValue(source, key) {
        if (!key) return undefined;
        return String(key).split('.').reduce((acc, part) => {
            if (acc && typeof acc === 'object' && Object.prototype.hasOwnProperty.call(acc, part)) {
                return acc[part];
            }
            return undefined;
        }, source);
    }

    function normalizeLang(lang) {
        const value = String(lang || 'en').trim().toLowerCase();
        if (!value || value === 'en') return 'en';
        if (['zh', 'cn', 'zh-cn', 'zh_cn', 'zh-hans', 'zh_hans', 'simplified_chinese'].includes(value)) {
            return 'zh_simplified';
        }
        if (['hk', 'tw', 'zh-hk', 'zh_hk', 'zh-tw', 'zh_tw', 'zh-hant', 'zh_hant', 'traditional_chinese'].includes(value)) {
            return 'zh_traditional';
        }
        return value;
    }

    async function load(lang) {
        lang = normalizeLang(lang);
        if (_loaded && lang === _currentLang) return;
        // Try localStorage cache first
        const cacheKey = `I18N_CACHE_20260719_AGENT4_${lang}`;
        try {
            const cached = localStorage.getItem(cacheKey);
            if (cached) {
                _strings = JSON.parse(cached);
                _currentLang = lang;
                _loaded = true;
                // Refresh cache in background
                fetch(`/static/i18n/${lang}${ASSET_SUFFIX}`).then(r => r.json()).then(data => {
                    _strings = data;
                    localStorage.setItem(cacheKey, JSON.stringify(data));
                }).catch(() => {});
                return;
            }
        } catch {}
        try {
            const res = await fetch(`/static/i18n/${lang}${ASSET_SUFFIX}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            _strings = await res.json();
            _currentLang = lang;
            _loaded = true;
            try { localStorage.setItem(cacheKey, JSON.stringify(_strings)); } catch {}
        } catch (e) {
            console.error(`[I18N] Failed to load ${lang}:`, e);
            if (lang !== 'en') {
                try {
                    const res = await fetch(`/static/i18n/en${ASSET_SUFFIX}`);
                    _strings = await res.json();
                    _currentLang = 'en';
                    _loaded = true;
                } catch {}
            }
        }
    }

    function tr(key) {
        const value = getNestedValue(_strings, key);
        return typeof value === 'string' ? value : key;
    }

    function getLang() { return _currentLang; }

    return { load, tr, getLang, normalizeLang };
})();
