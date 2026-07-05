/* ═══════════════════════════════════════════════════════════════════════
   Re-Life — Nearby Recycling Points
   Uses the official Hong Kong recycling map through our API proxy.
   ═══════════════════════════════════════════════════════════════════════ */

function recyclingTr(key, fallback) {
    const value = tr(key);
    return value === key ? fallback : value;
}

function getRecyclingPointMaterial(item = {}) {
    return item.material || item.category || item.standard_type || item.name || '';
}

function formatRecyclingDistance(distanceM) {
    const meters = Number(distanceM);
    if (!Number.isFinite(meters)) return '';
    if (meters < 1000) return `${Math.max(0, Math.round(meters))} m`;
    return `${(meters / 1000).toFixed(meters < 10000 ? 1 : 0)} km`;
}

function getOfficialRecyclingMapUrl(material = '') {
    const query = material ? `?search_api_fulltext=${encodeURIComponent(material)}` : '';
    return `https://www.wastereduction.gov.hk/zh-hk/recycling-map${query}`;
}

function setNearbyRecyclingVisible(visible) {
    const panel = document.getElementById('nearby-recycling');
    if (panel) panel.classList.toggle('hidden', !visible);
}

function setNearbyRecyclingStatus(message, status = 'idle') {
    state.nearbyRecyclingStatus = status;
    const statusEl = document.getElementById('nearby-recycling-status');
    const refresh = document.getElementById('nearby-recycling-refresh');
    if (statusEl) statusEl.textContent = message;
    if (refresh) {
        refresh.disabled = status === 'loading';
        refresh.classList.toggle('is-loading', status === 'loading');
        refresh.setAttribute('aria-label', recyclingTr('recycling.refresh', 'Refresh nearby recycling points'));
        refresh.title = recyclingTr('recycling.refresh', 'Refresh nearby recycling points');
    }
}

function resetNearbyRecyclingUI() {
    state.nearbyRecyclingPoints = [];
    state.nearbyRecyclingStatus = 'idle';
    state.nearbyRecyclingSourceUrl = '';
    const titleEl = document.getElementById('lbl-nearby-recycling-title');
    const listEl = document.getElementById('nearby-recycling-list');
    const sourceEl = document.getElementById('nearby-recycling-source');
    if (titleEl) titleEl.textContent = recyclingTr('recycling.nearbyTitle', 'Nearby Recycling Points');
    if (listEl) listEl.innerHTML = '';
    if (sourceEl) {
        sourceEl.href = getOfficialRecyclingMapUrl();
        sourceEl.textContent = recyclingTr('recycling.openMap', 'Open recycling map');
        sourceEl.classList.add('hidden');
    }
    setNearbyRecyclingStatus(recyclingTr('recycling.ready', 'Use your location to find nearby options.'), 'idle');
    setNearbyRecyclingVisible(false);
}

function renderNearbyRecyclingPoints(points = [], sourceUrl = '') {
    state.nearbyRecyclingPoints = points;
    state.nearbyRecyclingSourceUrl = sourceUrl || getOfficialRecyclingMapUrl(getRecyclingPointMaterial(state.lastScanResult || {}));
    const listEl = document.getElementById('nearby-recycling-list');
    const sourceEl = document.getElementById('nearby-recycling-source');

    if (listEl) {
        if (!points.length) {
            listEl.innerHTML = `<div class="nearby-recycling-empty">${esc(recyclingTr('recycling.empty', 'No nearby points found. Try the official map.'))}</div>`;
        } else {
            listEl.innerHTML = points.map(point => {
                const materials = Array.isArray(point.materials) ? point.materials.slice(0, 4).join(', ') : '';
                const distance = formatRecyclingDistance(point.distance_m);
                const mapsUrl = point.maps_url || sourceUrl || getOfficialRecyclingMapUrl();
                const detailUrl = point.detail_url || sourceUrl || getOfficialRecyclingMapUrl();
                const meta = [distance, materials].filter(Boolean).join(' · ');
                return `
                    <div class="nearby-recycling-card">
                        <div class="nearby-recycling-card-main">
                            <div class="nearby-recycling-name">${esc(point.name || recyclingTr('recycling.unnamed', 'Recycling point'))}</div>
                            ${meta ? `<div class="nearby-recycling-meta">${esc(meta)}</div>` : ''}
                            ${point.open_hours ? `<div class="nearby-recycling-note">${esc(point.open_hours)}</div>` : ''}
                            ${point.accessibility ? `<div class="nearby-recycling-note">${esc(point.accessibility)}</div>` : ''}
                        </div>
                        <div class="nearby-recycling-actions">
                            <a href="${esc(mapsUrl)}" target="_blank" rel="noopener">${esc(recyclingTr('recycling.navigate', 'Navigate'))}</a>
                            <a href="${esc(detailUrl)}" target="_blank" rel="noopener">${esc(recyclingTr('recycling.details', 'Details'))}</a>
                        </div>
                    </div>`;
            }).join('');
        }
    }

    if (sourceEl) {
        sourceEl.href = state.nearbyRecyclingSourceUrl;
        sourceEl.textContent = recyclingTr('recycling.openMap', 'Open recycling map');
        sourceEl.classList.remove('hidden');
    }
}

async function refreshNearbyRecyclingPoints() {
    const item = state.lastScanResult || {};
    const material = getRecyclingPointMaterial(item);
    const requestId = ++state.nearbyRecyclingRequestId;
    setNearbyRecyclingVisible(true);
    setNearbyRecyclingStatus(recyclingTr('recycling.locating', 'Getting your location...'), 'loading');

    const coords = await resolveWeatherCoordinates(true);
    if (requestId !== state.nearbyRecyclingRequestId) return;
    if (!coords) {
        const sourceUrl = getOfficialRecyclingMapUrl(material);
        renderNearbyRecyclingPoints([], sourceUrl);
        setNearbyRecyclingStatus(recyclingTr('recycling.locationUnavailable', 'Location unavailable. Open the official map instead.'), 'error');
        return;
    }

    setNearbyRecyclingStatus(recyclingTr('recycling.loading', 'Finding nearby recycling points...'), 'loading');
    const params = new URLSearchParams({
        lat: String(coords.latitude),
        lon: String(coords.longitude),
        material,
    });
    try {
        const response = await fetch(`/api/recycling/nearby?${params.toString()}`, {
            headers: { Accept: 'application/json' },
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(payload.error || `recycling ${response.status}`);
        }
        if (requestId !== state.nearbyRecyclingRequestId) return;
        renderNearbyRecyclingPoints(payload.points || [], payload.source_url || '');
        const count = Array.isArray(payload.points) ? payload.points.length : 0;
        const message = count
            ? recyclingTr('recycling.loaded', 'Nearest recycling points')
            : recyclingTr('recycling.empty', 'No nearby points found. Try the official map.');
        setNearbyRecyclingStatus(message, count ? 'loaded' : 'empty');
    } catch (_) {
        if (requestId !== state.nearbyRecyclingRequestId) return;
        const sourceUrl = getOfficialRecyclingMapUrl(material);
        renderNearbyRecyclingPoints([], sourceUrl);
        setNearbyRecyclingStatus(recyclingTr('recycling.unavailable', 'Recycling map is unavailable. Try the official map.'), 'error');
    }
}

async function loadNearbyRecyclingPointsForScan(item) {
    if (!item || item.mode === 'purchase') {
        resetNearbyRecyclingUI();
        return;
    }
    setNearbyRecyclingVisible(true);
    state.lastScanResult = item;
    await refreshNearbyRecyclingPoints();
}
