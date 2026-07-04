/* ═══════════════════════════════════════════════════════════════════════
   Re-Life — Weather UI
   Header chip + weather details modal.
   ═══════════════════════════════════════════════════════════════════════ */

function weatherTr(key, fallback) {
    const value = tr(key);
    return value === key ? fallback : value;
}

async function resolveWeatherCoordinates(forcePrompt = false) {
    if (!navigator.geolocation) {
        return null;
    }

    if (!forcePrompt && navigator.permissions && navigator.permissions.query) {
        try {
            const permission = await navigator.permissions.query({ name: 'geolocation' });
            if (permission.state === 'denied') {
                return null;
            }
        } catch (_) {
            // Some browsers, including iOS Safari variants, do not expose a
            // usable Permissions API for geolocation. Fall through and ask
            // the Geolocation API directly so the native prompt can appear.
        }
    }

    return new Promise(resolve => {
        const geolocationOptions = {
            enableHighAccuracy: false,
            timeout: forcePrompt ? 5000 : 2500,
            maximumAge: forcePrompt ? 0 : 300000,
        };
        navigator.geolocation.getCurrentPosition(
            position => {
                resolve({
                    latitude: position.coords.latitude,
                    longitude: position.coords.longitude,
                });
            },
            () => resolve(null),
            geolocationOptions,
        );
    });
}

function updateWeatherUI() {
    const weather = state.weather || {};
    const widget = document.getElementById('header-weather');
    const emojiEl = document.getElementById('header-weather-emoji');
    const tempEl = document.getElementById('header-weather-temp');
    const cityEl = document.getElementById('header-weather-city');
    const localizedSummary = localizeWeatherSummary(weather.summary);
    const defaultTitle = weatherTr('weather.header.defaultTitle', 'Hong Kong weather');

    if (emojiEl) emojiEl.textContent = weather.emoji || '🌤️';
    if (tempEl) tempEl.textContent = Number.isFinite(weather.temperature) ? `${Math.round(weather.temperature)}°` : '--°';
    if (cityEl) cityEl.textContent = localizeWeatherLocation(weather.location);

    if (widget) {
        const readableSummary = localizedSummary || defaultTitle;
        const readableTemp = Number.isFinite(weather.temperature) ? ` • ${Math.round(weather.temperature)}°C` : '';
        const tapForDetails = weatherTr('weather.header.tapForDetails', 'Tap for details');
        const ariaDetails = weatherTr('weather.header.ariaDetails', 'Tap for weather details.');
        widget.title = `${readableSummary}${readableTemp} • ${tapForDetails}`;
        widget.setAttribute('aria-label', `${readableSummary}${readableTemp}. ${ariaDetails}`);
        widget.setAttribute('aria-expanded', state.weatherDetailsOpen ? 'true' : 'false');
        widget.classList.toggle('is-loading', !weather.loaded);
        if (!weather.loaded && !state.weather) {
            widget.setAttribute('aria-busy', 'true');
        } else {
            widget.removeAttribute('aria-busy');
        }
    }

    if (state.weatherDetailsOpen) {
        renderWeatherDetails();
    }
}

async function fetchHeaderWeatherPayload(forcePrompt = false) {
    const coords = await resolveWeatherCoordinates(forcePrompt);
    const query = coords ? `?lat=${encodeURIComponent(coords.latitude)}&lon=${encodeURIComponent(coords.longitude)}` : '';
    try {
        const response = await fetch(`/api/weather/header${query}`, {
            headers: { Accept: 'application/json' },
        });
        if (!response.ok) {
            throw new Error(`weather ${response.status}`);
        }
        const payload = await response.json();
        return {
            ...payload,
            temperature: Number.isFinite(payload.temperature) ? payload.temperature : null,
            loaded: true,
        };
    } catch (_) {
        return {
            emoji: '🌤️',
            summary: 'Hong Kong weather',
            temperature: null,
            location: 'Hong Kong',
            loaded: true,
        };
    }
}

async function commitHeaderWeather(requestId, forcePrompt = false) {
    const payload = await fetchHeaderWeatherPayload(forcePrompt);
    if (requestId !== state.weatherRequestId) {
        return payload;
    }
    state.weather = payload;
    updateWeatherUI();
    const widget = document.getElementById('header-weather');
    if (widget && MOTION_ENABLED) {
        gsap.fromTo(widget, { y: -4, opacity: 0.5, scale: 0.98 }, { y: 0, opacity: 1, scale: 1, duration: 0.35, ease: 'power2.out', overwrite: 'auto' });
    }
    return state.weather;
}

async function loadHeaderWeather() {
    if (state.weatherLoadPromise) return state.weatherLoadPromise;

    const requestId = ++state.weatherRequestId;
    state.weatherLoadPromise = (async () => commitHeaderWeather(requestId, false))();
    return state.weatherLoadPromise;
}

async function refreshHeaderWeather() {
    const requestId = ++state.weatherRequestId;
    state.weatherLoadPromise = (async () => commitHeaderWeather(requestId, true))();
    return state.weatherLoadPromise;
}

function formatWeatherUpdatedAt(value) {
    if (!value) return weatherTr('weather.detail.liveData', state.lang === 'zh' ? '即時資料' : 'Live data');
    const stamp = new Date(value);
    if (Number.isNaN(stamp.getTime())) return weatherTr('weather.detail.liveData', state.lang === 'zh' ? '即時資料' : 'Live data');
    return stamp.toLocaleString(state.lang === 'zh' ? 'zh-HK' : 'en-HK', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
    });
}

function getWeatherDetailModel() {
    const weather = state.weather || {};
    const fallback = {
        emoji: '🌤️',
        summary: 'Hong Kong weather',
        temperature: null,
        location: 'Hong Kong',
        updated_at: null,
        source: 'HKO Open Data',
        callout: {
            title: weatherTr('weather.callout.default.title', 'Hong Kong weather'),
            body: weatherTr(
                'weather.callout.default.body',
                'Small habits make the city easier to breathe in. Recycle what you can and keep the air cleaner.',
            ),
        },
    };
    return { ...fallback, ...weather, callout: { ...fallback.callout, ...(weather.callout || {}) } };
}

function getWeatherLanguage() {
    return state.lang === 'zh' ? 'zh' : 'en';
}

function localizeWeatherSummary(summary) {
    const defaultSummary = weatherTr('weather.summary.default', 'Hong Kong weather');
    const key = !summary || summary === 'Hong Kong weather' ? 'weather.summary.default' : `weather.summary.${summary}`;
    return weatherTr(key, summary || defaultSummary);
}

function localizeWeatherLocation(location) {
    if (getWeatherLanguage() !== 'zh') {
        return location || weatherTr('weather.location.hongKong', 'Hong Kong');
    }
    if (!location || location === 'Hong Kong') {
        return weatherTr('weather.location.hongKong', '香港');
    }
    return location;
}

function localizeWeatherSource(source) {
    if (getWeatherLanguage() !== 'zh') {
        return source || weatherTr('weather.source.hkoOpenData', 'HKO Open Data');
    }
    if (source === 'Fallback') {
        return weatherTr('weather.source.fallback', '後備資料');
    }
    if (!source || source === 'HKO Open Data') {
        return weatherTr('weather.source.hkoOpenData', '香港天文台開放資料');
    }
    return source;
}

function localizeWeatherCallout(model) {
    const defaultTitle = weatherTr('weather.callout.default.title', 'Hong Kong weather');
    const defaultBody = weatherTr(
        'weather.callout.default.body',
        'Small habits make the city easier to breathe in. Recycle what you can and keep the air cleaner.',
    );
    const key = (model?.callout?.title && model.callout.title !== 'Hong Kong weather')
        ? model.callout.title
        : (model?.summary && model.summary !== 'Hong Kong weather')
            ? model.summary
            : 'default';
    return {
        title: weatherTr(`weather.callout.${key}.title`, defaultTitle),
        body: weatherTr(`weather.callout.${key}.body`, defaultBody),
    };
}

function getWeatherSubtitle(model) {
    const baseLocation = localizeWeatherLocation(model.location);
    if (model.temperature_place && model.temperature_place !== model.location) {
        return state.lang === 'zh' ? `${baseLocation} · ${model.temperature_place}` : `${baseLocation} • ${model.temperature_place}`;
    }
    return baseLocation;
}

function renderWeatherDetails() {
    const model = getWeatherDetailModel();
    const titleEl = document.getElementById('weather-detail-title');
    const subtitleEl = document.getElementById('weather-detail-subtitle');
    const emojiEl = document.getElementById('weather-detail-emoji');
    const tempEl = document.getElementById('weather-detail-temp');
    const locationEl = document.getElementById('weather-detail-location');
    const updatedEl = document.getElementById('weather-detail-updated');
    const sourceEl = document.getElementById('weather-detail-source');
    const calloutTitleEl = document.getElementById('weather-detail-callout-title');
    const calloutEl = document.getElementById('weather-detail-callout');
    const closeButton = document.querySelector('.weather-close');
    const callout = localizeWeatherCallout(model);

    if (titleEl) titleEl.textContent = localizeWeatherSummary(model.summary);
    if (subtitleEl) {
        subtitleEl.textContent = getWeatherSubtitle(model);
    }
    if (emojiEl) emojiEl.textContent = model.emoji || '🌤️';
    if (tempEl) tempEl.textContent = Number.isFinite(model.temperature) ? `${Math.round(model.temperature)}°C` : '--°C';
    if (locationEl) locationEl.textContent = localizeWeatherLocation(model.location);
    if (updatedEl) updatedEl.textContent = formatWeatherUpdatedAt(model.updated_at);
    if (sourceEl) sourceEl.textContent = localizeWeatherSource(model.source);
    if (calloutTitleEl) calloutTitleEl.textContent = callout.title;
    if (calloutEl) {
        calloutEl.textContent = callout.body;
    }
    if (closeButton) closeButton.setAttribute('aria-label', weatherTr('weather.detail.close', tr('closeBtn')));
}

function openWeatherDetails() {
    const overlay = document.getElementById('weather-overlay');
    const panel = document.getElementById('weather-panel');
    if (!overlay || !panel) return;

    state.weatherDetailsOpen = true;
    renderWeatherDetails();
    updateWeatherUI();
    overlay.classList.add('is-shown');
    overlay.setAttribute('aria-hidden', 'false');

    if (MOTION_ENABLED) {
        gsap.killTweensOf([overlay, panel]);
        gsap.fromTo(
            overlay,
            { autoAlpha: 0 },
            { autoAlpha: 1, duration: 0.18, ease: 'power1.out', overwrite: 'auto' },
        );
        gsap.fromTo(
            panel,
            { y: 14, scale: 0.97, autoAlpha: 0 },
            { y: 0, scale: 1, autoAlpha: 1, duration: 0.34, ease: 'back.out(1.35)', overwrite: 'auto' },
        );
    } else {
        overlay.style.opacity = '1';
        panel.style.opacity = '1';
        panel.style.transform = 'none';
    }
}

function closeWeatherDetails() {
    const overlay = document.getElementById('weather-overlay');
    const panel = document.getElementById('weather-panel');
    if (!overlay || !panel || !state.weatherDetailsOpen) return;

    state.weatherDetailsOpen = false;
    updateWeatherUI();

    const finalizeClose = () => {
        overlay.classList.remove('is-shown');
        overlay.setAttribute('aria-hidden', 'true');
        overlay.style.opacity = '';
        panel.style.opacity = '';
        panel.style.transform = '';
    };

    if (MOTION_ENABLED) {
        gsap.killTweensOf([overlay, panel]);
        gsap.to(panel, { y: 10, scale: 0.97, autoAlpha: 0, duration: 0.18, ease: 'power2.in', overwrite: 'auto' });
        gsap.to(overlay, { autoAlpha: 0, duration: 0.18, ease: 'power1.in', overwrite: 'auto', onComplete: finalizeClose });
    } else {
        finalizeClose();
    }
}

async function toggleWeatherDetails() {
    if (state.weatherDetailsOpen) {
        closeWeatherDetails();
        return;
    }

    openWeatherDetails();
    refreshHeaderWeather().catch(() => {});
}

document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
        closeWeatherDetails();
    }
});
