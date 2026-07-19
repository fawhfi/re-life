/* ReAgent UI: consent, resumable tool approvals, and chat rendering. */

let agentConversationId = null;
let agentDataConsent = false;
let agentBusy = false;
let agentAttachment = null;
let agentAttachmentDataUrl = '';
const AGENT_ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024;
const AGENT_ATTACHMENT_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);

function agentTr(key, fallback) {
    const value = tr(`agent.${key}`);
    return value === `agent.${key}` ? fallback : value;
}

function setAgentStatus(text, busy = false) {
    const status = document.getElementById('agent-status');
    if (status) text && (status.textContent = text);
    const send = document.getElementById('agent-send');
    const input = document.getElementById('agent-input');
    const attach = document.getElementById('agent-attach');
    const removeAttachment = document.getElementById('agent-attachment-remove');
    agentBusy = busy;
    if (send) send.disabled = busy;
    if (input) input.disabled = busy;
    if (attach) attach.disabled = busy;
    if (removeAttachment) removeAttachment.disabled = busy;
    document.querySelector('.agent-shell')?.classList.toggle('agent-is-busy', busy);
}

function appendAgentMessage(role, text, options = {}) {
    const list = document.getElementById('agent-messages');
    if (!list || (!text && !options.imageUrl && !options.hasImage)) return;
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
    if (options.imageUrl) {
        const image = document.createElement('img');
        image.className = 'agent-message-image';
        image.src = options.imageUrl;
        image.alt = agentTr('photoAttached', 'Photo attached');
        bubble.appendChild(image);
    } else if (options.hasImage) {
        const attachment = document.createElement('div');
        attachment.className = 'agent-message-attachment';
        attachment.textContent = `📎 ${agentTr('photoAttached', 'Photo attached')}`;
        bubble.appendChild(attachment);
    }
    if (text) {
        const messageText = document.createElement('span');
        messageText.className = 'agent-message-text';
        messageText.textContent = String(text);
        bubble.appendChild(messageText);
    }
    content.append(author, bubble);
    row.appendChild(content);
    list.appendChild(row);
    list.scrollTop = list.scrollHeight;
}

function clearAgentAttachment() {
    agentAttachment = null;
    agentAttachmentDataUrl = '';
    const input = document.getElementById('agent-image-input');
    const preview = document.getElementById('agent-attachment-preview');
    const image = document.getElementById('agent-attachment-image');
    if (input) input.value = '';
    if (image) image.src = '';
    preview?.classList.add('hidden');
}

function handleAgentAttachment(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!AGENT_ATTACHMENT_TYPES.has(file.type)) {
        clearAgentAttachment();
        showToast(agentTr('imageInvalid', 'Choose an image file.'), 'warning');
        return;
    }
    if (file.size > AGENT_ATTACHMENT_MAX_BYTES) {
        clearAgentAttachment();
        showToast(agentTr('imageTooLarge', 'The photo must be 10 MB or smaller.'), 'warning');
        return;
    }

    const reader = new FileReader();
    reader.onload = () => {
        agentAttachment = file;
        agentAttachmentDataUrl = String(reader.result || '');
        const image = document.getElementById('agent-attachment-image');
        const name = document.getElementById('agent-attachment-name');
        if (image) image.src = agentAttachmentDataUrl;
        if (name) name.textContent = file.name || agentTr('photoAttached', 'Photo attached');
        document.getElementById('agent-attachment-preview')?.classList.remove('hidden');
    };
    reader.readAsDataURL(file);
}

async function analyzeAgentAttachment(file) {
    const form = new FormData();
    form.append('file', file);
    form.append('mode', 'dispose');
    form.append('item_type', 'general');
    form.append('item_state', 'expire');
    form.append('lang', state.lang);
    const response = await fetch('/api/scan/ai', {
        method: 'POST',
        credentials: 'same-origin',
        body: form,
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
        const error = new Error(result.error || 'Image analysis failed');
        error.code = 'AGENT_IMAGE_ANALYSIS_FAILED';
        throw error;
    }

    const observations = {
        name: result.name || result.waste_label,
        brand: result.brand,
        category: result.category,
        material: result.material || result.disposal_info?.type,
        waste_type: result.waste_type,
        description: result.description || result.text || result.disposal_guide,
    };
    const bounded = {};
    Object.entries(observations).forEach(([key, value]) => {
        const text = String(value || '').trim();
        if (text) bounded[key] = text.slice(0, key === 'description' ? 800 : 160);
    });
    if (!Object.keys(bounded).length) {
        const error = new Error('Image analysis returned no observations');
        error.code = 'AGENT_IMAGE_ANALYSIS_FAILED';
        throw error;
    }
    return bounded;
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
        const locationAllowed = await requestAgentDialog('agent-location-dialog', 'allow');
        const coords = locationAllowed ? await resolveWeatherCoordinates(true) : null;
        const next = await sendAgentRequest({
            conversation_id: agentConversationId,
            request_id: payload.action.request_id,
            ...(coords ? {
                location: {
                    latitude: coords.latitude,
                    longitude: coords.longitude,
                },
            } : { location_error: locationAllowed ? 'unavailable' : 'denied' }),
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
    const typedMessage = String(input?.value || '').trim();
    const attachedFile = agentAttachment;
    const attachedDataUrl = agentAttachmentDataUrl;
    if (!typedMessage && !attachedFile) return;
    if (!await ensureAgentConsent()) {
        setAgentStatus(agentTr('consentDeclined', 'Permission not granted.'));
        return;
    }

    const message = typedMessage || agentTr('photoPrompt', 'How should I recycle this item?');
    appendAgentMessage('user', message, { imageUrl: attachedDataUrl });
    input.value = '';
    input.style.height = '';
    clearAgentAttachment();
    setAgentStatus(agentTr('working', 'Working...'), true);
    try {
        let imageAnalysis = null;
        if (attachedFile) {
            setAgentToolStatus(agentTr('analyzingPhoto', 'Analyzing photo...'));
            imageAnalysis = await analyzeAgentAttachment(attachedFile);
        }
        const payload = await sendAgentRequest({
            message,
            conversation_id: agentConversationId,
            language: state.lang,
            data_consent: agentDataConsent,
            ...(imageAnalysis ? { image_analysis: imageAnalysis } : {}),
        });
        await processAgentPayload(payload);
        setAgentStatus(agentTr('ready', 'Ready'));
    } catch (error) {
        if (error.code === 'AGENT_DATA_CONSENT_REQUIRED') agentDataConsent = false;
        const safetyBlocked = error.code === 'AGENT_SAFETY_BLOCKED';
        const safetyUnavailable = error.code === 'AGENT_SAFETY_UNAVAILABLE';
        const imageAnalysisFailed = error.code === 'AGENT_IMAGE_ANALYSIS_FAILED';
        const fallback = imageAnalysisFailed
            ? agentTr('imageAnalysisFailed', 'I could not analyze that photo. Try another image or describe the item.')
            : safetyBlocked
            ? agentTr('safetyBlocked', "I can't help with unsafe requests or requests that try to bypass permissions.")
            : safetyUnavailable
            ? agentTr('safetyUnavailable', 'The safety check is temporarily unavailable. No Agent tools were run.')
            : error.code === 'AGENT_NOT_CONFIGURED'
            ? agentTr('notConfigured', 'Agent is not configured on this server.')
            : agentTr('unavailable', 'Agent is temporarily unavailable.');
        appendAgentMessage('assistant', fallback);
        setAgentStatus(
            safetyBlocked || imageAnalysisFailed ? agentTr('ready', 'Ready') : agentTr('error', 'Unavailable')
        );
    } finally {
        setAgentToolStatus('');
        setAgentStatus(document.getElementById('agent-status')?.textContent || agentTr('ready', 'Ready'), false);
        input?.focus();
    }
}

async function resetAgentConversation() {
    agentConversationId = null;
    agentDataConsent = false;
    clearAgentAttachment();
    initializeAgentMessages();
    setAgentStatus(agentTr('ready', 'Ready'));
    document.getElementById('agent-input')?.focus();
}

function renderAgentHistory(conversations) {
    const list = document.getElementById('agent-history-list');
    if (!list) return;
    list.replaceChildren();
    if (!Array.isArray(conversations) || !conversations.length) {
        const empty = document.createElement('p');
        empty.className = 'agent-history-empty';
        empty.textContent = agentTr('historyEmpty', 'No previous chats yet.');
        list.appendChild(empty);
        return;
    }
    conversations.forEach(conversation => {
        const row = document.createElement('div');
        row.className = 'agent-history-item';

        const open = document.createElement('button');
        open.type = 'button';
        open.className = 'agent-history-open';
        open.addEventListener('click', () => loadAgentConversation(conversation.conversation_id));

        const title = document.createElement('strong');
        title.textContent = conversation.title || agentTr('historyUntitled', 'Untitled chat');
        const preview = document.createElement('span');
        preview.textContent = conversation.preview || '';
        open.append(title, preview);

        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'agent-history-delete';
        remove.textContent = '×';
        remove.setAttribute('aria-label', agentTr('historyDelete', 'Delete chat'));
        remove.title = agentTr('historyDelete', 'Delete chat');
        remove.addEventListener('click', () => deleteAgentConversation(conversation.conversation_id));
        row.append(open, remove);
        list.appendChild(row);
    });
}

async function openAgentHistory() {
    const dialog = document.getElementById('agent-history-dialog');
    const list = document.getElementById('agent-history-list');
    if (!dialog || !list) return;
    list.textContent = agentTr('historyLoading', 'Loading chats...');
    if (typeof dialog.showModal === 'function' && !dialog.open) dialog.showModal();
    try {
        const response = await fetch('/api/agent/conversations', {
            credentials: 'same-origin',
            headers: { Accept: 'application/json' },
        });
        if (!response.ok) throw new Error(`History request failed (${response.status})`);
        renderAgentHistory(await response.json());
    } catch (_) {
        list.textContent = agentTr('historyError', 'Chat history is unavailable.');
    }
}

async function loadAgentConversation(conversationId) {
    try {
        const response = await fetch(`/api/agent/conversations/${encodeURIComponent(conversationId)}`, {
            credentials: 'same-origin',
            headers: { Accept: 'application/json' },
        });
        if (!response.ok) throw new Error(`Conversation request failed (${response.status})`);
        const payload = await response.json();
        agentConversationId = payload.conversation_id;
        agentDataConsent = true;
        initializeAgentMessages();
        (payload.messages || []).forEach(message => {
            if (message?.role === 'user' || message?.role === 'assistant') {
                appendAgentMessage(message.role, message.text, { hasImage: Boolean(message.has_image) });
            }
        });
        document.getElementById('agent-history-dialog')?.close();
        setAgentStatus(agentTr('ready', 'Ready'));
        document.getElementById('agent-input')?.focus();
    } catch (_) {
        const list = document.getElementById('agent-history-list');
        if (list) list.textContent = agentTr('historyError', 'Chat history is unavailable.');
    }
}

async function deleteAgentConversation(conversationId) {
    try {
        const response = await fetch(`/api/agent/conversations/${encodeURIComponent(conversationId)}`, {
            method: 'DELETE',
            credentials: 'same-origin',
            headers: { Accept: 'application/json' },
        });
        if (!response.ok) throw new Error(`Conversation delete failed (${response.status})`);
        if (agentConversationId === conversationId) resetAgentConversation();
        await openAgentHistory();
    } catch (_) {
        const list = document.getElementById('agent-history-list');
        if (list) list.textContent = agentTr('historyError', 'Chat history is unavailable.');
    }
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
        'agent-consent-body': agentTr('consentBody', 'Your messages and attached photos may be processed by the AI and safety providers configured by this service. ReAgent only reads account data after a separate approval.'),
        'agent-consent-cancel': agentTr('cancel', 'Cancel'),
        'agent-consent-allow': agentTr('allow', 'Allow'),
        'agent-location-title': agentTr('locationTitle', 'Share your location?'),
        'agent-location-body': agentTr('locationBody', 'Allow ReAgent to use your current location once for this request. Your coordinates are not shown in the chat.'),
        'agent-location-deny': agentTr('locationDeny', 'Not now'),
        'agent-location-allow': agentTr('locationAllowOnce', 'Share once'),
        'agent-history-title': agentTr('historyTitle', 'Chat history'),
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
    const attach = document.getElementById('agent-attach');
    if (attach) {
        attach.setAttribute('aria-label', agentTr('attachImage', 'Attach photo'));
        attach.title = agentTr('attachImage', 'Attach photo');
    }
    const removeAttachment = document.getElementById('agent-attachment-remove');
    if (removeAttachment) {
        removeAttachment.setAttribute('aria-label', agentTr('removeImage', 'Remove photo'));
        removeAttachment.title = agentTr('removeImage', 'Remove photo');
    }
    const reset = document.getElementById('agent-new-conversation');
    if (reset) {
        reset.setAttribute('aria-label', agentTr('newConversation', 'New conversation'));
        reset.title = agentTr('newConversation', 'New conversation');
    }
    const history = document.getElementById('agent-open-history');
    if (history) {
        history.setAttribute('aria-label', agentTr('historyTitle', 'Chat history'));
        history.title = agentTr('historyTitle', 'Chat history');
    }
    const historyClose = document.getElementById('agent-history-close');
    if (historyClose) {
        historyClose.setAttribute('aria-label', agentTr('close', 'Close'));
        historyClose.title = agentTr('close', 'Close');
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
