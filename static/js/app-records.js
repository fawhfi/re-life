/* ═══════════════════════════════════════════════════════════════════════
   Re-Life — Records UI
   Record cache, render, CRUD, and stats.
   ═══════════════════════════════════════════════════════════════════════ */

function getRecordsCacheKey() {
    return [state.currentUser || '', state.userId || '', state.userKey || ''].join('|');
}

function canonicalizeRecordMode(record) {
    const mode = record?.mode || record?.status;
    return mode === 'purchase' ? 'purchase' : 'dispose';
}

function syncRecordsView() {
    renderRecords();
    updateStats();
}

function invalidateRecordsCache({ clear = false } = {}) {
    state.recordsDirty = true;
    state.recordsLoadedFor = '';
    state.recordsLoadToken += 1;
    state.recordsLoadPromise = null;
    state.recordsLoadPromiseToken = 0;
    if (clear) {
        state.records = [];
        syncRecordsView();
    }
}

function upsertRecordCache(record) {
    if (!record) return;
    const normalized = {
        id: record.id ?? null,
        name: record.name || 'Scanned Item',
        mode: record.mode || record.status || 'dispose',
        status: record.status || record.mode || 'dispose',
        createdAt: record.createdAt || new Date().toISOString(),
        description: record.description || '',
        image_url: record.image_url || record.photoUrl || record.photo_url || '',
        photoUrl: record.photoUrl || record.image_url || record.photo_url || '',
        dealtWithMethod: record.disposal_guide || record.dealtWithMethod || record.dealt_with_method || '',
        disposal_guide: record.disposal_guide || record.dealtWithMethod || record.dealt_with_method || '',
        dealtWithDate: record.dealtWithDate || record.dealt_with_date || null,
        eco_rate: record.eco_rate ?? 3,
        recycle_rate: record.recycle_rate ?? 4,
        overall_score: record.overall_score ?? 0,
        material: record.material || '',
        grade: record.grade || '',
        grade_color: record.grade_color || null,
        grade_advice: record.grade_advice || null,
        brand: record.brand || '',
        category: record.category || '',
        weighted_scores: record.weighted_scores || record.weightedScores || {},
        schema_id: record.schema_id || record.schemaId || '',
        alternative: record.alternative || null,
        reuse_tip: record.reuse_tip || record.reuse || '',
        precaution: record.precaution || null,
        image: (record.mode || record.status) === 'purchase' ? '🥛' : '🗑️',
    };
    state.recordsLoadToken += 1;
    state.records = [normalized, ...state.records.filter(r => String(r.id) !== String(normalized.id))];
    state.recordsLoadedFor = getRecordsCacheKey();
    state.recordsDirty = false;
    syncRecordsView();
}

function removeRecordCache(recordId) {
    state.recordsLoadToken += 1;
    state.records = state.records.filter(r => String(r.id) !== String(recordId));
    state.recordsLoadedFor = getRecordsCacheKey();
    state.recordsDirty = false;
    syncRecordsView();
}

async function loadRecords({ force = false } = {}) {
    if (typeof FB === 'undefined') { console.warn('[App] FB not ready, retrying...'); setTimeout(() => loadRecords({ force }), 500); return; }
    if (!state.currentUser && !state.userId && !state.userKey) {
        invalidateRecordsCache({ clear: true });
        return [];
    }

    const cacheKey = getRecordsCacheKey();
    if (!force && !state.recordsDirty && state.recordsLoadedFor === cacheKey) {
        syncRecordsView();
        return state.records;
    }

    if (state.recordsLoadPromise && state.recordsLoadPromiseToken === state.recordsLoadToken) {
        return state.recordsLoadPromise;
    }

    const loadToken = ++state.recordsLoadToken;
    const loadPromise = (async () => {
        try {
            state.records = [];
            syncRecordsView();
            const items = await FB.getItems();
            if (loadToken !== state.recordsLoadToken || cacheKey !== getRecordsCacheKey()) return state.records;
            state.records = items.map(it => ({
                id: it.id,
                name: it.name,
                mode: it.status,
                eco_rate: it.eco_rate,
                recycle_rate: it.recycle_rate,
                overall_score: it.overall_score,
                material: it.material,
                grade: it.grade,
                description: it.description,
                image_url: it.photoUrl,
                disposal_guide: it.dealtWithMethod,
                disposal_info: null,
                precaution: null,
                alternative: it.alternative,
                weighted_scores: it.weighted_scores,
                schema_id: it.schema_id,
                brand: it.brand,
                category: it.category,
                reuse_tip: it.reuse_tip || it.reuse || '',
                image: it.status === 'purchase' ? '🥛' : '🗑️',
            }));
            state.recordsLoadedFor = cacheKey;
            state.recordsDirty = false;
            syncRecordsView();
            return state.records;
        } catch (e) {
            console.error('Failed to load records:', e);
            throw e;
        }
    })();

    state.recordsLoadPromise = loadPromise;
    state.recordsLoadPromiseToken = loadToken;
    try {
        return await loadPromise;
    } finally {
        if (state.recordsLoadPromise === loadPromise && state.recordsLoadPromiseToken === loadToken) {
            state.recordsLoadPromise = null;
            state.recordsLoadPromiseToken = 0;
        }
    }
}

function renderRecords() {
    const container = document.getElementById('records-list');
    const empty = document.getElementById('records-empty');

    if (!state.records.length) {
        container.innerHTML = '';
        empty.classList.remove('hidden');
        return;
    }

    empty.classList.add('hidden');
    container.innerHTML = state.records.map(r => {
        const schemaId = r.schema_id || 'food_new';
        const badgeMode = canonicalizeRecordMode(r);
        const overall = r.overall_score ||
            calcWeighted(r.weighted_scores || { a: 50, b: 50, c: 50, d: 50, e: 50 }, schemaId);
        const grade = getGrade(overall);

        let altHtml = '';
        if (r.alternative) {
            altHtml = `
                <div class="alternative-card">
                    <div class="alternative-card-label">${tr('alternativeProduct')}</div>
                    <div class="alternative-card-name">${esc(r.alternative.name)}</div>
                    <div class="alternative-card-ratings">
                        <div class="rating-item">
                            <span class="rating-label">${tr('ecoRate')}:</span>
                            <div class="star-rating">${buildStars(r.alternative.eco_rate)}</div>
                        </div>
                        <div class="rating-item">
                            <span class="rating-label">${tr('recycleRate')}:</span>
                            <div class="star-rating">${buildStars(r.alternative.recycle_rate)}</div>
                        </div>
                    </div>
                </div>`;
        }

        let guideHtml = '';
        if (r.disposal_guide || r.disposal_info) {
            guideHtml = `
                <div class="disposal-guide">
                    <div class="disposal-guide-title">♻️ ${tr('disposalGuide')}</div>
                    ${r.disposal_info ? `
                        <div class="disposal-guide-row"><span class="disposal-guide-label">${tr('material')}:</span> ${esc(r.disposal_info.type)}</div>
                        <div class="disposal-guide-row"><span class="disposal-guide-label">${tr('method')}:</span> ${esc(r.disposal_info.method)}</div>
                        <div class="disposal-guide-row"><span class="disposal-guide-label">${tr('location')}:</span> ${esc(r.disposal_info.location)}</div>
                    ` : ''}
                    ${r.disposal_guide ? `<div class="disposal-guide-row" style="margin-top:3px">${esc(r.disposal_guide)}</div>` : ''}
                    ${r.precaution ? `<div class="disposal-guide-precaution">⚠️ ${esc(r.precaution)}</div>` : ''}
                </div>`;
        }

        const photoHtml = r.image_url
            ? `<img src="${esc(r.image_url)}" loading="lazy" decoding="async" style="width:100%;height:100%;object-fit:cover;border-radius:8px" alt="">`
            : (r.image || '📦');

        return `
        <div class="record-card" id="rec-${r.id}" onclick="viewRecordDetail('${r.id}')" style="cursor:pointer">
            <div class="record-card-inner">
                <div class="record-card-image">${photoHtml}</div>
                <div class="record-card-info">
                    <div class="record-card-name">${esc(r.name)}</div>
                    <div class="record-card-meta">
                        <span class="record-card-badge record-card-badge--${badgeMode}">${badgeMode === 'purchase' ? tr('purchaseBadge') : tr('disposeBadge')}</span>
                        <span class="grade-tag" style="background:${grade.color};font-size:8px">${grade.grade}</span>
                    </div>
                    <div class="record-card-ratings">
                        <div class="rating-item">
                            <span class="rating-label">${tr('ecoRate')}</span>
                            <div class="star-rating">${buildStars(r.eco_rate)}</div>
                        </div>
                        <div class="rating-item">
                            <span class="rating-label">${tr('recycleRate')}</span>
                            <div class="star-rating">${buildStars(r.recycle_rate)}</div>
                        </div>
                        <div class="rating-item">
                            <span class="rating-label">${tr('ecoGradeLabel')}</span>
                            <span style="font-size:13px;font-weight:900;color:${grade.color}">${overall}/100</span>
                        </div>
                    </div>
                    ${altHtml}
                    ${guideHtml}
                </div>
            </div>
            <div class="record-card-actions">
                <button class="btn btn--outline btn--small" onclick="event.stopPropagation();viewRecordDetail('${r.id}')">🔍 Details</button>
                <button class="btn btn--danger" onclick="event.stopPropagation();deleteRecord('${r.id}')">🗑️</button>
            </div>
        </div>`;
    }).join('');

    if (MOTION_ENABLED) {
        const cards = Array.from(document.querySelectorAll('#records-list .record-card')).slice(0, 8);
        if (cards.length) {
            gsap.fromTo(cards,
                { opacity: 0, y: 24 },
                { opacity: 1, y: 0, duration: 0.4, stagger: 0.06, ease: "power2.out" }
            );
        }
    }
}

async function deleteRecord(id) {
    try {
        await FB.deleteItem(id);
        closeModal();
        removeRecordCache(id);
    } catch (e) {
        console.error('Failed to delete record:', e);
    }
}

function viewRecordDetail(id) {
    const r = state.records.find(rec => String(rec.id) === String(id));
    if (!r) return;

    const badgeMode = canonicalizeRecordMode(r);
    const grade = getGrade(r.overall_score || 50);
    const photoHtml = r.image_url
        ? `<img src="${esc(r.image_url)}" loading="lazy" decoding="async" style="width:100%;max-height:200px;object-fit:cover;border-radius:12px;margin-bottom:12px" alt="">`
        : `<div style="font-size:48px;text-align:center;margin-bottom:12px">${r.image || '📦'}</div>`;

    const guideHtml = (r.disposal_guide || r.material) ? `
        <div class="disposal-guide" style="margin-top:12px">
            <div class="disposal-guide-title">♻️ ${tr('disposalGuide')}</div>
            ${r.material ? `<div class="disposal-guide-row"><span class="disposal-guide-label">${tr('material')}:</span> ${esc(r.material)}</div>` : ''}
            ${r.reuse_tip ? `<div class="disposal-guide-row"><span class="disposal-guide-label">${tr('reuse')}:</span> ${esc(r.reuse_tip)}</div>` : ''}
            ${r.disposal_guide ? `<div class="disposal-guide-row">${esc(r.disposal_guide)}</div>` : ''}
        </div>` : '';

    document.getElementById('modal-icon').textContent = '';
    document.getElementById('modal-title').textContent = r.name;
    document.getElementById('modal-body').innerHTML = `
        ${photoHtml}
        <div style="font-size:11px;color:var(--color-gray-500);margin-bottom:8px">${esc(r.description || '')}</div>
        <div style="display:flex;gap:6px;align-items:center;margin-bottom:8px">
            <span class="record-card-badge record-card-badge--${badgeMode}">${badgeMode === 'purchase' ? tr('purchaseBadge') : tr('disposeBadge')}</span>
            <span class="grade-tag" style="background:${grade.color}">${grade.grade}</span>
        </div>
        <div style="display:flex;gap:16px;margin-bottom:10px">
            <div class="rating-item"><span class="rating-label">${tr('ecoRate')}</span><div class="star-rating">${buildStars(r.eco_rate)}</div></div>
            <div class="rating-item"><span class="rating-label">${tr('recycleRate')}</span><div class="star-rating">${buildStars(r.recycle_rate)}</div></div>
        </div>
        <div class="overall-row"><span class="overall-label">${tr('overallScore')}</span><div><span class="overall-value">${r.overall_score || 50}</span><span class="overall-max">/100</span></div></div>
        <div class="overall-bar" style="margin-bottom:0"><div class="overall-bar-fill" style="width:${r.overall_score || 50}%;background:${grade.color}"></div></div>
        ${guideHtml}
    `;
    document.getElementById('modal-actions').innerHTML = `
        <button class="btn btn--outline btn--full" onclick="closeModal()">${tr('closeBtn')}</button>
        <button class="btn btn--danger" onclick="closeModal();deleteRecord('${r.id}')">🗑️ ${tr('clearAll') || 'Delete'}</button>
    `;
    document.getElementById('modal-overlay').classList.add('is-shown');
}

async function clearAllRecords() {
    showConfirm(tr('confirmClear'), async () => {
        await FB.clearAllItems();
        closeModal();
        invalidateRecordsCache({ clear: true });
    });
}

function updateStats() {
    const n = state.records.length;
    const itemsEl = document.getElementById('stat-items');
    const ecoEl = document.getElementById('stat-eco');
    const recycleEl = document.getElementById('stat-recycle');

    const animateEl = (el, value) => {
        if (!el) return;
        el.textContent = value;
        if (!MOTION_ENABLED) return;
        el.classList.remove('anim-entrance');
        requestAnimationFrame(() => el.classList.add('anim-entrance'));
    };

    animateEl(itemsEl, n);
    animateEl(ecoEl, n
        ? (state.records.reduce((s, r) => s + (r.eco_rate || 3), 0) / n).toFixed(1)
        : '0');
    animateEl(recycleEl, n
        ? (state.records.reduce((s, r) => s + (r.recycle_rate || 3), 0) / n).toFixed(1)
        : '0');
}
