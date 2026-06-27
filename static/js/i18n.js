/* ═══════════════════════════════════════════════════════════════════════
   Re-Life — i18n Loader
   Fetches i18n/{lang}.json, caches it, exposes tr(key).
   ═══════════════════════════════════════════════════════════════════════ */

const I18N = (() => {
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

    async function load(lang) {
        if (_loaded && lang === _currentLang) return;
        // Try localStorage cache first
        const cacheKey = `I18N_CACHE_${lang}`;
        try {
            const cached = localStorage.getItem(cacheKey);
            if (cached) {
                _strings = JSON.parse(cached);
                _currentLang = lang;
                _loaded = true;
                // Refresh cache in background
                fetch(`/static/i18n/${lang}.json`).then(r => r.json()).then(data => {
                    _strings = data;
                    localStorage.setItem(cacheKey, JSON.stringify(data));
                }).catch(() => {});
                return;
            }
        } catch {}
        try {
            const res = await fetch(`/static/i18n/${lang}.json`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            _strings = await res.json();
            _currentLang = lang;
            _loaded = true;
            try { localStorage.setItem(cacheKey, JSON.stringify(_strings)); } catch {}
        } catch (e) {
            console.error(`[I18N] Failed to load ${lang}:`, e);
            if (lang !== 'en') {
                try {
                    const res = await fetch('/static/i18n/en.json');
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

    return { load, tr, getLang };
})();
