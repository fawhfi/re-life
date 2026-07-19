/* ReAgent UI: consent, resumable tool approvals, and chat rendering. */

let agentConversationId = null;
let agentDataConsent = false;
let agentBusy = false;

function agentTr(key, fallback) {
    const value = tr(`agent.${key}`);
    return value === `agent.${key}` ? fallback : value;
}

function setAgentStatus(text, busy = false) {
    const status = document.getElementById('agent-status');
    if (status) text && (status.textContent = text);
    const send = document.getElementById('agent-send');
    const input = document.getElementById('agent-input');
    agentBusy = busy;
    if (send) send.disabled = busy;
    if (input) input.disabled = busy;
    document.querySelector('.agent-shell')?.classList.toggle('agent-is-busy', busy);
}

function appendAgentMessage(role, text) {
    const list = document.getElementById('agent-messages');
    if (!list || !text) return;
    document.getElementById('agent-welcome')?.remove();
    const row = document.createElement('div');
    row.className = `agent-message agent-message--${role}`;
    if (role === 'assistant') {
        const avatar = document.createElement('span');
        avatar.className = 'agent-message-avatar';
        avatar.textContent = 'R';
        avatar.setAttribute('aria-hidden', 'true');
        row.appendChild(avatar);
    }
    const content = document.createElement('div');
    content.className = 'agent-message-content';
    const author = document.createElement('span');
    author.className = 'agent-message-author';
    author.textContent = role === 'assistant'
        ? agentTr('assistantLabel', 'ReAgent')
        : agentTr('userLabel', 'You');
    const bubble = document.createElement('div');
    bubble.className = 'agent-message-bubble';
    bubble.textContent = String(text);
    content.append(author, bubble);
    row.appendChild(content);
    list.appendChild(row);
    list.scrollTop = list.scrollHeight;
}

function submitAgentSuggestion(kind) {
    const prompts = {
        nearby: agentTr('suggestionNearbyPrompt', 'Find recycling points near me.'),
        sorting: agentTr('suggestionSortingPrompt', 'How should I recycle this item?'),
        records: agentTr('suggestionRecordsPrompt', 'What have I recycled recently?'),
    };
    const input = document.getElementById('agent-input');
    if (!input || !prompts[kind]) return;
    input.value = prompts[kind];
    input.dispatchEvent(new Event('input'));
    document.getElementById('agent-form')?.requestSubmit();
}

function safeAgentUrl(value) {
    try {
        const url = new URL(String(value || ''), window.location.origin);
        return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
    } catch (_) {
        return '';
    }
}

function formatAgentDistance(value) {
    const meters = Number(value);
    if (!Number.isFinite(meters)) return '';
    return meters < 1000 ? `${Math.round(meters)} m` : `${(meters / 1000).toFixed(1)} km`;
}

function renderAgentPoints(points) {
    if (!Array.isArray(points) || !points.length) return;
    const list = document.getElementById('agent-messages');
    if (!list) return;
    const group = document.createElement('div');
    group.className = 'agent-points';
    points.forEach(point => {
        const item = document.createElement('div');
        item.className = 'agent-point';

        const name = document.createElement('div');
        name.className = 'agent-point-name';
        name.textContent = point.name || agentTr('pointFallback', 'Recycling point');
        item.appendChild(name);

        const meta = [
            formatAgentDistance(point.distance_m),
            Array.isArray(point.materials) ? point.materials.slice(0, 4).join(', ') : '',
        ].filter(Boolean).join(' · ');
        if (meta) {
            const detail = document.createElement('div');
            detail.className = 'agent-point-meta';
            detail.textContent = meta;
            item.appendChild(detail);
        }

        const mapUrl = safeAgentUrl(point.maps_url || point.detail_url);
        if (mapUrl) {
            const link = document.createElement('a');
            link.href = mapUrl;
            link.target = '_blank';
            link.rel = 'noopener';
            link.textContent = agentTr('navigate', 'Navigate');
            item.appendChild(link);
        }
        group.appendChild(item);
    });
    list.appendChild(group);
    list.scrollTop = list.scrollHeight;
}

function setAgentToolStatus(text) {
    const status = document.getElementById('agent-tool-status');
    if (!status) return;
    status.textContent = text || '';
    status.classList.toggle('hidden', !text);
}

function requestAgentDialog(dialogId, allowedValue) {
    const dialog = document.getElementById(dialogId);
    if (!dialog || typeof dialog.showModal !== 'function') {
        return Promise.resolve(window.confirm(
            dialog?.querySelector('p')?.textContent || agentTr('consentBody', 'Allow Agent data access?')
        ));
    }
    return new Promise(resolve => {
        const onClose = () => resolve(dialog.returnValue === allowedValue);
        dialog.addEventListener('close', onClose, { once: true });
        dialog.showModal();
    });
}

async function ensureAgentConsent() {
    if (agentDataConsent) return true;
    const allowed = await requestAgentDialog('agent-consent-dialog', 'allow');
    if (allowed) agentDataConsent = true;
    return allowed;
}

async function sendAgentRequest(body) {
    const response = await fetch('/api/agent/messages', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
        const error = new Error(payload.error || `Agent request failed (${response.status})`);
        error.code = payload.error || '';
        throw error;
    }
    return payload;
}

async function processAgentPayload(payload, depth = 0) {
    if (depth > 5) throw new Error('Agent approval loop exceeded');
    agentConversationId = payload.conversation_id || agentConversationId;
    if (payload.status !== 'requires_action') {
        appendAgentMessage('assistant', payload.message);
        renderAgentPoints(payload.points);
        setAgentToolStatus('');
        return;
    }

    if (payload.action.type === 'get_user_location') {
        appendAgentMessage('assistant', agentTr('locationRequest', 'Allow location access to continue.'));
        setAgentToolStatus(agentTr('locating', 'Waiting for location permission...'));
        const coords = await resolveWeatherCoordinates(true);
        const next = await sendAgentRequest({
            conversation_id: agentConversationId,
            request_id: payload.action.request_id,
            ...(coords ? {
                location: {
                    latitude: coords.latitude,
                    longitude: coords.longitude,
                },
            } : { location_error: 'unavailable' }),
            language: state.lang,
            data_consent: agentDataConsent,
        });
        await processAgentPayload(next, depth + 1);
        return;
    }

    if (payload.action.type === 'read_user_records') {
        appendAgentMessage('assistant', agentTr('recordsRequest', 'Allow access to your recent recycling records?'));
        const approved = await requestAgentDialog('agent-records-dialog', 'allow');
        const next = await sendAgentRequest({
            conversation_id: agentConversationId,
            approval: {
                type: 'read_user_records',
                request_id: payload.action.request_id,
                approved,
            },
            language: state.lang,
            data_consent: agentDataConsent,
        });
        await processAgentPayload(next, depth + 1);
        return;
    }

    throw new Error('Unsupported Agent approval request');
}

async function handleAgentSubmit(event) {
    event.preventDefault();
    if (agentBusy) return;
    const input = document.getElementById('agent-input');
    const message = String(input?.value || '').trim();
    if (!message) return;
    if (!await ensureAgentConsent()) {
        setAgentStatus(agentTr('consentDeclined', 'Permission not granted.'));
        return;
    }

    appendAgentMessage('user', message);
    input.value = '';
    input.style.height = '';
    setAgentStatus(agentTr('working', 'Working...'), true);
    try {
        const payload = await sendAgentRequest({
            message,
            conversation_id: agentConversationId,
            language: state.lang,
            data_consent: agentDataConsent,
        });
        await processAgentPayload(payload);
        setAgentStatus(agentTr('ready', 'Ready'));
    } catch (error) {
        if (error.code === 'AGENT_DATA_CONSENT_REQUIRED') agentDataConsent = false;
        const safetyBlocked = error.code === 'AGENT_SAFETY_BLOCKED';
        const fallback = safetyBlocked
            ? agentTr('safetyBlocked', "I can't follow requests that try to change my rules or bypass permissions.")
            : error.code === 'AGENT_NOT_CONFIGURED'
            ? agentTr('notConfigured', 'Agent is not configured on this server.')
            : agentTr('unavailable', 'Agent is temporarily unavailable.');
        appendAgentMessage('assistant', fallback);
        setAgentStatus(safetyBlocked ? agentTr('ready', 'Ready') : agentTr('error', 'Unavailable'));
    } finally {
        setAgentStatus(document.getElementById('agent-status')?.textContent || agentTr('ready', 'Ready'), false);
        input?.focus();
    }
}

async function resetAgentConversation() {
    const previous = agentConversationId;
    agentConversationId = null;
    agentDataConsent = false;
    if (previous) {
        fetch(`/api/agent/conversations/${encodeURIComponent(previous)}`, {
            method: 'DELETE',
            credentials: 'same-origin',
        }).catch(() => {});
    }
    initializeAgentMessages();
    setAgentStatus(agentTr('ready', 'Ready'));
    document.getElementById('agent-input')?.focus();
}

function initializeAgentMessages() {
    const list = document.getElementById('agent-messages');
    if (!list) return;
    const template = document.getElementById('agent-welcome-template');
    list.replaceChildren(template?.content.cloneNode(true) || document.createTextNode(''));
    refreshAgentWelcomeLanguage();
}

function refreshAgentWelcomeLanguage() {
    const labels = {
        'agent-greeting': agentTr('greeting', 'What can we sort out?'),
        'agent-suggestion-nearby': agentTr('suggestionNearby', 'Find nearby points'),
        'agent-suggestion-sorting': agentTr('suggestionSorting', 'Sort an item'),
        'agent-suggestion-records': agentTr('suggestionRecords', 'Recent scans'),
    };
    Object.entries(labels).forEach(([id, value]) => {
        const element = document.getElementById(id);
        if (element) element.textContent = value;
    });
}

function refreshAgentLanguage() {
    const labels = {
        'agent-title': agentTr('title', 'ReAgent'),
        'agent-consent-title': agentTr('consentTitle', 'Use ReAgent?'),
        'agent-consent-body': agentTr('consentBody', 'Your messages will be processed by the AI provider configured by this service. ReAgent only reads account data after a separate approval.'),
        'agent-consent-cancel': agentTr('cancel', 'Cancel'),
        'agent-consent-allow': agentTr('allow', 'Allow'),
        'agent-records-title': agentTr('recordsTitle', 'Share recent records?'),
        'agent-records-body': agentTr('recordsBody', 'Allow this Agent run to read a short summary of your recent recycling records.'),
        'agent-records-deny': agentTr('deny', 'Deny'),
        'agent-records-allow': agentTr('allowOnce', 'Allow once'),
    };
    Object.entries(labels).forEach(([id, value]) => {
        const element = document.getElementById(id);
        if (element) element.textContent = value;
    });
    refreshAgentWelcomeLanguage();
    const input = document.getElementById('agent-input');
    if (input) {
        input.placeholder = agentTr('placeholder', 'Ask about recycling...');
        input.setAttribute('aria-label', agentTr('inputLabel', 'Message ReAgent'));
    }
    const send = document.getElementById('agent-send');
    if (send) {
        send.setAttribute('aria-label', agentTr('send', 'Send message'));
        send.title = agentTr('send', 'Send message');
    }
    const reset = document.getElementById('agent-new-conversation');
    if (reset) {
        reset.setAttribute('aria-label', agentTr('newConversation', 'New conversation'));
        reset.title = agentTr('newConversation', 'New conversation');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    if (!document.getElementById('tab-agent')) return;
    initializeAgentMessages();
    refreshAgentLanguage();
    const input = document.getElementById('agent-input');
    input?.addEventListener('input', () => {
        input.style.height = 'auto';
        input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
    });
    input?.addEventListener('keydown', event => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            document.getElementById('agent-form')?.requestSubmit();
        }
    });
});
