/* Re-Life auth language helper. Keeps login/register in sync with the app. */
(function () {
    const LANGS = ['en', 'zh_simplified', 'zh_traditional'];

    function normalize(lang) {
        const value = String(lang || 'en').trim().toLowerCase();
        if (!value || value === 'en') return 'en';
        if (['zh_traditional', 'zh-hk', 'zh_hk', 'zh-tw', 'zh_tw', 'zh-hant', 'zh_hant', 'hk', 'tw', 'traditional_chinese'].includes(value)) {
            return 'zh_traditional';
        }
        if (['zh_simplified', 'zh', 'zh-cn', 'zh_cn', 'zh-hans', 'zh_hans', 'cn', 'simplified_chinese'].includes(value) || value.startsWith('zh')) {
            return 'zh_simplified';
        }
        return 'en';
    }

    function next(lang) {
        const index = LANGS.indexOf(normalize(lang));
        return LANGS[(index + 1) % LANGS.length];
    }

    function htmlLang(lang) {
        const normalized = normalize(lang);
        if (normalized === 'zh_simplified') return 'zh-CN';
        if (normalized === 'zh_traditional') return 'zh-HK';
        return 'en';
    }

    function label(lang) {
        const normalized = normalize(lang);
        if (normalized === 'zh_simplified') return '简中';
        if (normalized === 'zh_traditional') return '繁中';
        return 'EN';
    }

    function text(lang, en, zhSimplified, zhTraditional) {
        const normalized = normalize(lang);
        if (normalized === 'zh_simplified') return zhSimplified;
        if (normalized === 'zh_traditional') return zhTraditional;
        return en;
    }

    window.AUTH_LANG = { LANGS, normalize, next, htmlLang, label, text };
})();
