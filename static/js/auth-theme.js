(function () {
    const STORAGE_KEY = 'RE_LIFE_THEME';
    const THEMES = [
        { value: 'light', label: 'Light', icon: '🌿' },
        { value: 'dark', label: 'Dark', icon: '🌙' },
        { value: 'forest', label: 'Forest', icon: '🌲' },
        { value: 'ocean', label: 'Ocean', icon: '🌊' },
        { value: 'sunset', label: 'Sunset', icon: '🌅' },
        { value: 'midnight', label: 'Midnight', icon: '✨' },
    ];
    const VALID_THEMES = THEMES.map((theme) => theme.value);

    function normalizeTheme(theme) {
        return VALID_THEMES.includes(theme) ? theme : 'light';
    }

    function themeConfig(theme) {
        return THEMES.find((entry) => entry.value === theme) || THEMES[0];
    }

    function readStoredTheme() {
        try {
            return normalizeTheme(localStorage.getItem(STORAGE_KEY));
        } catch (_) {
            return 'light';
        }
    }

    function writeStoredTheme(theme) {
        try {
            localStorage.setItem(STORAGE_KEY, theme);
        } catch (_) {
            // Private browsing modes can block localStorage; the page still gets the theme.
        }
    }

    function syncThemeControls(theme) {
        const config = themeConfig(theme);
        document.querySelectorAll('[data-auth-theme-select]').forEach((select) => {
            select.value = config.value;
            select.title = `Theme: ${config.label}`;
        });
        document.querySelectorAll('[data-auth-theme-icon]').forEach((icon) => {
            icon.textContent = config.icon;
        });
    }

    function applyAuthTheme(theme) {
        const nextTheme = normalizeTheme(theme);
        document.documentElement.setAttribute('data-theme', nextTheme);
        writeStoredTheme(nextTheme);
        syncThemeControls(nextTheme);
        return nextTheme;
    }

    function toggleTheme() {
        const currentTheme = normalizeTheme(document.documentElement.getAttribute('data-theme') || readStoredTheme());
        return applyAuthTheme(currentTheme === 'dark' ? 'light' : 'dark');
    }

    const initialTheme = applyAuthTheme(readStoredTheme());
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => syncThemeControls(initialTheme), { once: true });
    } else {
        syncThemeControls(initialTheme);
    }

    window.applyAuthTheme = applyAuthTheme;
    window.toggleTheme = toggleTheme;
})();
