/* ═══════════════════════════════════════════════════════════════════════
   Re-Life — i18n Loader
   Fetches i18n/{lang}.json, caches it, exposes tr(key).
   ═══════════════════════════════════════════════════════════════════════ */

const I18N = (() => {
    let _strings = {};       // current language strings
    let _currentLang = 'en';
    let _loaded = false;

    async function load(lang) {
        if (_loaded && lang === _currentLang) return;
        try {
            const res = await fetch(`/static/i18n/${lang}.json`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            _strings = await res.json();
            _currentLang = lang;
            _loaded = true;
        } catch (e) {
            console.error(`[I18N] Failed to load ${lang}:`, e);
            // Fallback to en
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
        return _strings[key] || key;
    }

    function getLang() { return _currentLang; }

    return { load, tr, getLang };
})();
