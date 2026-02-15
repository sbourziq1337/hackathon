/* ─── 2020 AI Agent — Authorized Personnel Dashboard ───────── */

const API = '';
const sevEmoji = { CRITICAL: '🔴', HIGH: '🟠', MODERATE: '🟡', LOW: '🟢' };
const srcIcon = { phone_call: '📞', text: '📝', voice_upload: '🎙', telegram: '💬' };

// ═══════════════════════════════════════════════════════════
//  AUTHENTICATION
// ═══════════════════════════════════════════════════════════

let authToken = localStorage.getItem('triageToken') || '';
let currentUser = null;

async function checkAuth() {
    if (!authToken) { showLogin(); return; }
    try {
        const r = await fetch(API + '/api/auth/validate?token=' + authToken);
        const d = await r.json();
        if (d.valid) {
            currentUser = d;
            showApp();
        } else {
            authToken = '';
            localStorage.removeItem('triageToken');
            showLogin();
        }
    } catch {
        showLogin();
    }
}

function showLogin() {
    document.getElementById('loginScreen').style.display = 'flex';
    document.getElementById('appContainer').style.display = 'none';
}

function showApp() {
    document.getElementById('loginScreen').style.display = 'none';
    document.getElementById('appContainer').style.display = '';
    document.body.style.display = 'flex';

    const ui = document.getElementById('userInfo');
    if (currentUser) {
        ui.innerHTML = `<span class="user-name">${escapeHtml(currentUser.full_name)}</span><span class="user-role">${escapeHtml(currentUser.role)} — ${escapeHtml(currentUser.organization)}</span>`;
    }

    checkHealth();
    connectSSE();
    loadDashboard();
    updateCallbackBadge();
}

async function handleLogin(e) {
    e.preventDefault();
    const btn = document.getElementById('loginBtn');
    const errEl = document.getElementById('loginError');
    btn.querySelector('.btn-text').style.display = 'none';
    btn.querySelector('.btn-loading').style.display = 'inline';
    btn.disabled = true;
    errEl.style.display = 'none';

    try {
        const r = await fetch(API + '/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username: document.getElementById('loginUser').value.trim(),
                password: document.getElementById('loginPass').value,
            }),
        });
        const d = await r.json();
        if (!r.ok) throw new Error(d.detail || 'Authentication failed.');

        authToken = d.token;
        localStorage.setItem('triageToken', authToken);
        currentUser = { full_name: d.full_name, role: d.role, organization: d.organization };
        showApp();
    } catch (err) {
        errEl.textContent = err.message;
        errEl.style.display = 'block';
    } finally {
        btn.disabled = false;
        btn.querySelector('.btn-text').style.display = 'inline';
        btn.querySelector('.btn-loading').style.display = 'none';
    }
}

function handleLogout() {
    fetch(API + '/api/auth/logout?token=' + authToken, { method: 'POST' }).catch(() => {});
    authToken = '';
    currentUser = null;
    localStorage.removeItem('triageToken');
    showLogin();
}


// ═══════════════════════════════════════════════════════════
//  TAB SWITCHING & UTILITIES
// ═══════════════════════════════════════════════════════════

function switchTab(tab) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));
    document.getElementById('tab-' + tab).classList.add('active');
    document.querySelector(`[data-tab="${tab}"]`).classList.add('active');
    if (tab === 'history') loadReports();
    if (tab === 'dashboard') loadDashboard();
    if (tab === 'callbacks') loadCallbacks();
    document.getElementById('sidebar').classList.remove('open');
}
function toggleSidebar() { document.getElementById('sidebar').classList.toggle('open'); }

function toast(msg, type = 'success', duration = 4000) {
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), duration);
}
function escapeHtml(t) { if (!t) return ''; const d = document.createElement('div'); d.textContent = t; return d.innerHTML; }


// ═══════════════════════════════════════════════════════════
//  CONVERSATIONAL VOICE INTERVIEW
// ═══════════════════════════════════════════════════════════

let interviewSessionId = null;
let interviewActive = false;
let recognition = null;
let isListening = false;
let voiceMode = true; // true = speak & listen, false = type only
let waitingForAI = false;

function checkSpeechSupport() {
    const hasSynthesis = 'speechSynthesis' in window;
    // We use ElevenLabs STT via mic recording — just need getUserMedia
    const hasRecognition = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
    return { hasSynthesis, hasRecognition };
}

async function startVoiceInterview() {
    voiceMode = document.getElementById('voiceModeToggle').checked;
    const { hasRecognition } = checkSpeechSupport();

    if (voiceMode && !hasRecognition) {
        toast('Speech recognition not supported. Switching to text mode.', 'error');
        voiceMode = false;
        document.getElementById('voiceModeToggle').checked = false;
    }

    try {
        const r = await fetch(API + '/api/interview/start', { method: 'POST' });
        const d = await r.json();
        interviewSessionId = d.session_id;
        interviewActive = true;

        // Show active state
        document.getElementById('voiceIdleState').style.display = 'none';
        document.getElementById('voiceActiveState').style.display = 'block';
        document.getElementById('voiceCompleteState').style.display = 'none';
        document.getElementById('voiceBadge').style.display = 'inline';
        document.getElementById('chatMessages').innerHTML = '';
        document.getElementById('chatTurnCount').textContent = 'Turn 0';

        // Show AI's opening message
        addChatBubble('ai', d.ai_message);

        // Speak the AI's opening message if voice mode
        if (voiceMode) {
            speakAndListen(d.ai_message);
        }

    } catch (err) {
        toast('Failed to start conversation: ' + err.message, 'error');
    }
}

// ── Chat bubble management ──────────────────────────────────

function addChatBubble(role, text) {
    const container = document.getElementById('chatMessages');
    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${role}`;
    const label = role === 'ai' ? 'AI Operator' : 'You';
    bubble.innerHTML = `<span class="bubble-label">${label}</span>${escapeHtml(text)}`;
    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;
}

function addTypingIndicator() {
    const container = document.getElementById('chatMessages');
    const typing = document.createElement('div');
    typing.className = 'chat-typing';
    typing.id = 'typingIndicator';
    typing.innerHTML = `<div class="typing-dots"><span></span><span></span><span></span></div><span>AI is thinking...</span>`;
    container.appendChild(typing);
    container.scrollTop = container.scrollHeight;
}

function removeTypingIndicator() {
    const el = document.getElementById('typingIndicator');
    if (el) el.remove();
}

// ── Send a message (from text input or speech) ──────────────

async function sendMessage(text) {
    if (!text.trim() || !interviewSessionId || !interviewActive || waitingForAI) return;

    // Stop listening if active
    stopListening();
    speechSynthesis.cancel();

    // Show user message
    addChatBubble('user', text);
    document.getElementById('chatTextInput').value = '';

    // Show typing indicator
    waitingForAI = true;
    addTypingIndicator();
    setInputState(false);

    try {
        const r = await fetch(API + `/api/interview/${interviewSessionId}/message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text }),
        });
        const d = await r.json();

        removeTypingIndicator();
        waitingForAI = false;

        // Update turn count
        document.getElementById('chatTurnCount').textContent = `Turn ${d.turn_count}`;

        // Show AI response
        addChatBubble('ai', d.ai_message);

        if (d.is_complete) {
            // Interview completed by the AI
            interviewActive = false;
            document.getElementById('voiceBadge').style.display = 'none';
            setInputState(false);
            showInterviewResult(d.report);
        } else {
            setInputState(true);
            // Speak the AI's response and listen for the next message
            if (voiceMode) {
                speakAndListen(d.ai_message);
            }
        }

    } catch (err) {
        removeTypingIndicator();
        waitingForAI = false;
        setInputState(true);
        toast('Error: ' + err.message, 'error');
    }
}

function sendTextMessage() {
    const input = document.getElementById('chatTextInput');
    sendMessage(input.value);
}

function setInputState(enabled) {
    document.getElementById('chatTextInput').disabled = !enabled;
    document.getElementById('sendBtn').disabled = !enabled;
    document.getElementById('micBtn').disabled = !enabled;
}

// ── Speech synthesis (AI speaks via ElevenLabs TTS) ─────────

async function speakAndListen(text) {
    if (!voiceMode) return;

    const speakEl = document.getElementById('aiSpeakingIndicator');
    speakEl.style.display = 'flex';

    try {
        // Try ElevenLabs TTS first
        const resp = await fetch(API + '/api/interview/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text }),
        });

        if (resp.ok) {
            const audioBlob = await resp.blob();
            const audioUrl = URL.createObjectURL(audioBlob);
            const audio = new Audio(audioUrl);

            audio.onended = () => {
                speakEl.style.display = 'none';
                URL.revokeObjectURL(audioUrl);
                if (interviewActive && voiceMode) startListening();
            };
            audio.onerror = () => {
                speakEl.style.display = 'none';
                URL.revokeObjectURL(audioUrl);
                if (interviewActive && voiceMode) startListening();
            };

            await audio.play();
            return;
        }
    } catch (e) {
        console.warn('ElevenLabs TTS failed, falling back to browser speech:', e);
    }

    // Fallback: browser built-in speech synthesis
    if ('speechSynthesis' in window) {
        const utter = new SpeechSynthesisUtterance(text);
        utter.rate = 0.95;
        utter.pitch = 1;
        utter.lang = 'en-US';

        utter.onend = () => {
            speakEl.style.display = 'none';
            if (interviewActive && voiceMode) startListening();
        };
        utter.onerror = () => {
            speakEl.style.display = 'none';
            if (interviewActive && voiceMode) startListening();
        };

        speechSynthesis.cancel();
        speechSynthesis.speak(utter);
    } else {
        speakEl.style.display = 'none';
        if (interviewActive && voiceMode) startListening();
    }
}

// ── Speech recognition via ElevenLabs STT (mic recording) ───

let mediaRecorder = null;
let audioChunks = [];
let recordingStream = null;

async function startListening() {
    if (isListening || !interviewActive || waitingForAI) return;

    try {
        recordingStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(recordingStream, { mimeType: 'audio/webm' });
        audioChunks = [];

        mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) audioChunks.push(e.data);
        };

        mediaRecorder.onstop = async () => {
            // Stop mic access
            if (recordingStream) {
                recordingStream.getTracks().forEach(t => t.stop());
                recordingStream = null;
            }

            if (audioChunks.length === 0) {
                stopListeningUI();
                return;
            }

            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            audioChunks = [];

            // Show transcribing state
            document.getElementById('micStatus').innerHTML = '<span class="mic-dot transcribing"></span> Transcribing...';

            try {
                const formData = new FormData();
                formData.append('audio', audioBlob, 'recording.webm');

                const resp = await fetch(API + '/api/interview/stt', {
                    method: 'POST',
                    body: formData,
                });

                if (resp.ok) {
                    const data = await resp.json();
                    const transcript = data.text?.trim();
                    stopListeningUI();
                    if (transcript) {
                        sendMessage(transcript);
                    } else {
                        toast('Could not understand audio. Try again or type your message.', 'error');
                        if (interviewActive && voiceMode) {
                            setTimeout(() => startListening(), 1000);
                        }
                    }
                } else {
                    console.warn('STT request failed:', resp.status);
                    stopListeningUI();
                    // Fallback to browser speech recognition
                    startBrowserListening();
                }
            } catch (err) {
                console.warn('STT error:', err);
                stopListeningUI();
                startBrowserListening();
            }
        };

        mediaRecorder.start();
        isListening = true;
        document.getElementById('micStatus').style.display = 'flex';
        document.getElementById('micStatus').innerHTML = '<span class="mic-dot recording"></span> Listening... (click mic to stop)';
        document.getElementById('micBtn').classList.add('listening');

        // Auto-stop after 15 seconds to avoid huge uploads
        setTimeout(() => {
            if (mediaRecorder && mediaRecorder.state === 'recording') {
                mediaRecorder.stop();
            }
        }, 15000);

    } catch (err) {
        console.error('Microphone access error:', err);
        toast('Microphone access denied. Please allow mic access or type your message.', 'error');
        voiceMode = false;
        stopListeningUI();
    }
}

function startBrowserListening() {
    // Fallback: browser Web Speech API
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onstart = () => {
        isListening = true;
        document.getElementById('micStatus').style.display = 'flex';
        document.getElementById('micStatus').innerHTML = '<span class="mic-dot recording"></span> Listening (browser)...';
        document.getElementById('micBtn').classList.add('listening');
    };
    recognition.onresult = (e) => {
        stopListeningUI();
        sendMessage(e.results[0][0].transcript);
    };
    recognition.onerror = () => stopListeningUI();
    recognition.onend = () => stopListeningUI();
    try { recognition.start(); } catch {}
}

function stopListening() {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
        return; // onstop handler will process the audio
    }
    if (recognition) {
        try { recognition.abort(); } catch {}
        recognition = null;
    }
    if (recordingStream) {
        recordingStream.getTracks().forEach(t => t.stop());
        recordingStream = null;
    }
    stopListeningUI();
}

function stopListeningUI() {
    isListening = false;
    document.getElementById('micStatus').style.display = 'none';
    document.getElementById('micBtn').classList.remove('listening');
}

function toggleMic() {
    if (waitingForAI) return;
    if (isListening) {
        stopListening();
    } else {
        speechSynthesis.cancel();
        document.getElementById('aiSpeakingIndicator').style.display = 'none';
        startListening();
    }
}

// ── End / Cancel ────────────────────────────────────────────

async function endConversation() {
    if (!interviewSessionId || !interviewActive) return;

    stopListening();
    speechSynthesis.cancel();
    waitingForAI = true;
    addTypingIndicator();
    setInputState(false);

    try {
        const r = await fetch(API + `/api/interview/${interviewSessionId}/end`, { method: 'POST' });
        const d = await r.json();

        removeTypingIndicator();
        waitingForAI = false;
        interviewActive = false;
        document.getElementById('voiceBadge').style.display = 'none';

        if (d.ai_message) addChatBubble('ai', d.ai_message);
        showInterviewResult(d.report);

    } catch (err) {
        removeTypingIndicator();
        waitingForAI = false;
        toast('Failed to end conversation: ' + err.message, 'error');
    }
}

function cancelInterview() {
    interviewActive = false;
    interviewSessionId = null;
    stopListening();
    speechSynthesis.cancel();
    document.getElementById('voiceIdleState').style.display = 'block';
    document.getElementById('voiceActiveState').style.display = 'none';
    document.getElementById('voiceCompleteState').style.display = 'none';
    document.getElementById('voiceBadge').style.display = 'none';
}

function resetVoiceInterview() {
    document.getElementById('voiceIdleState').style.display = 'block';
    document.getElementById('voiceActiveState').style.display = 'none';
    document.getElementById('voiceCompleteState').style.display = 'none';
}

function showInterviewResult(report) {
    if (!report) return;
    document.getElementById('voiceActiveState').style.display = 'none';
    document.getElementById('voiceCompleteState').style.display = 'block';

    const c = document.getElementById('voiceResult');
    c.innerHTML = `
        <div class="severity-banner ${report.severity}">
            <span>${sevEmoji[report.severity]} ${report.severity} — Priority ${report.estimated_response_priority}/10</span>
            <span style="font-size:0.85rem;font-weight:400;">${Math.round(report.confidence * 100)}% confidence</span>
        </div>
        <div class="result-body">
            <div class="ambulance-badge ${report.needs_human_callback ? 'yes' : 'no'}">
                ${report.needs_human_callback ? 'HUMAN CALLBACK REQUIRED' : 'Logged — callback optional'}
            </div>
            <div class="result-meta">
                <div class="meta-item"><div class="meta-label">Patient</div><div class="meta-value">${report.patient_name || '—'}</div></div>
                <div class="meta-item"><div class="meta-label">Age</div><div class="meta-value">${report.age != null ? report.age : '—'}</div></div>
                <div class="meta-item"><div class="meta-label">Location</div><div class="meta-value">${report.location || '—'}</div></div>
                <div class="meta-item"><div class="meta-label">Conscious</div><div class="meta-value">${report.is_conscious === true ? 'Yes' : report.is_conscious === false ? 'NO' : '?'}</div></div>
                <div class="meta-item"><div class="meta-label">Breathing</div><div class="meta-value">${report.is_breathing === true ? 'Yes' : report.is_breathing === false ? 'NO' : '?'}</div></div>
                <div class="meta-item"><div class="meta-label">Bleeding</div><div class="meta-value">${report.has_heavy_bleeding === true ? 'YES' : report.has_heavy_bleeding === false ? 'No' : '?'}</div></div>
            </div>
            ${report.detected_risk_factors && report.detected_risk_factors.length ? `<div class="result-section"><h4>Risk Factors</h4><p style="color:var(--critical);font-weight:600;">${report.detected_risk_factors.join(', ')}</p></div>` : ''}
            <div class="result-section"><h4>AI Reasoning</h4><p>${escapeHtml(report.reasoning)}</p></div>
            ${report.situation_description ? `<div class="result-section"><h4>Situation Summary</h4><p>${escapeHtml(report.situation_description)}</p></div>` : ''}
            <div class="result-actions">
                <button class="btn btn-outline btn-sm" onclick="openReportModal('${report.report_id}')">Full Report</button>
                <button class="btn btn-outline btn-sm" onclick="downloadReportPDF('${report.report_id}')">PDF</button>
            </div>
        </div>`;
    toast(`Conversation complete: ${sevEmoji[report.severity]} ${report.severity}`);
}


// ═══════════════════════════════════════════════════════════
//  HEALTH CHECK
// ═══════════════════════════════════════════════════════════

async function checkHealth() {
    try {
        const r = await fetch(API + '/health');
        const d = await r.json();
        document.getElementById('statusDot').className = 'status-dot ' + (d.status === 'ok' ? 'online' : 'offline');
        document.getElementById('statusText').textContent = d.status === 'ok' ? `Online — ${d.total_reports} cases` : 'Error';
    } catch {
        document.getElementById('statusDot').className = 'status-dot offline';
        document.getElementById('statusText').textContent = 'Offline';
    }
}


// ═══════════════════════════════════════════════════════════
//  SSE — Real-time
// ═══════════════════════════════════════════════════════════

let liveReports = [];

function connectSSE() {
    const setStatus = (text, cls) => {
        document.querySelectorAll('.sse-status').forEach(el => { el.textContent = text; el.className = 'sse-status ' + cls; });
    };
    setStatus('Connecting...', 'connecting');
    const es = new EventSource(API + '/api/events');
    es.addEventListener('connected', () => {
        setStatus('Connected — Listening', 'connected');
        document.getElementById('liveBadge').style.display = 'inline';
    });
    es.addEventListener('new_report', (e) => {
        const rpt = JSON.parse(e.data).report;
        liveReports.unshift(rpt);
        if (liveReports.length > 50) liveReports.pop();
        renderLiveFeed();
        // Only beep for non-live reports (confidence > 0 means finalized or manual)
        if (rpt.confidence > 0) {
            playBeep(rpt.severity);
            toast(`${sevEmoji[rpt.severity]} New ${rpt.severity} case — ${rpt.patient_name || 'Unknown'}`, 'success');
        } else {
            toast(`📡 New live Telegram session started`, 'success');
        }
        checkHealth();
        if (document.getElementById('tab-dashboard').classList.contains('active')) loadDashboard();
        updateCallbackBadge();
    });

    // Real-time report updates (streaming data from ongoing conversations)
    es.addEventListener('report_update', (e) => {
        const rpt = JSON.parse(e.data).report;
        // Update the report in liveReports array
        const idx = liveReports.findIndex(r => r.report_id === rpt.report_id);
        if (idx !== -1) {
            liveReports[idx] = rpt;
        } else {
            liveReports.unshift(rpt);
            if (liveReports.length > 50) liveReports.pop();
        }
        renderLiveFeed();
        // If confidence > 0, it means the triage just finalized
        if (rpt.confidence > 0 && rpt.reasoning && !rpt.reasoning.includes('currently interviewing')) {
            playBeep(rpt.severity);
            toast(`${sevEmoji[rpt.severity]} Triage complete — ${rpt.patient_name || 'Unknown'} → ${rpt.severity}`, 'success');
        }
        if (document.getElementById('tab-dashboard').classList.contains('active')) loadDashboard();
        updateCallbackBadge();
    });

    es.addEventListener('callback_update', () => { loadCallbacks(); updateCallbackBadge(); });

    // CRITICAL ALERT — immediate notification when life-threatening indicators detected
    es.addEventListener('critical_alert', (e) => {
        const data = JSON.parse(e.data);
        const risks = data.risk_factors ? data.risk_factors.join(', ') : '';
        // Aggressive notification
        playBeep('CRITICAL');
        setTimeout(() => playBeep('CRITICAL'), 300);
        setTimeout(() => playBeep('CRITICAL'), 600);
        toast(`🚨 CRITICAL ALERT: ${data.patient_name || 'Unknown'} — ${risks}`, 'error', 10000);
        // Show a persistent critical banner
        showCriticalBanner(data);
    });

    // Listen for victim messages (from Telegram → dashboard)
    es.addEventListener('victim_message', (e) => {
        const data = JSON.parse(e.data);
        if (!chatMessages[data.report_id]) chatMessages[data.report_id] = [];
        chatMessages[data.report_id].push(data);
        // If the modal is open for this report, update the chat
        if (currentModalReportId === data.report_id) renderOperatorChat(data.report_id);
        toast(`💬 New message from victim (${data.report_id.slice(0,8)})`, 'success');
    });

    // Listen for operator messages (echo back to dashboard)
    es.addEventListener('operator_message', (e) => {
        const data = JSON.parse(e.data);
        if (!chatMessages[data.report_id]) chatMessages[data.report_id] = [];
        chatMessages[data.report_id].push(data);
        if (currentModalReportId === data.report_id) renderOperatorChat(data.report_id);
    });

    es.onerror = () => {
        setStatus('Disconnected', 'disconnected');
        document.getElementById('liveBadge').style.display = 'none';
        setTimeout(() => { es.close(); connectSSE(); }, 3000);
    };
}

function playBeep(sev) {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.connect(g); g.connect(ctx.destination); g.gain.value = 0.12;
        o.frequency.value = sev === 'CRITICAL' ? 880 : sev === 'HIGH' ? 660 : 440;
        o.type = sev === 'CRITICAL' ? 'square' : 'sine';
        o.start(); setTimeout(() => { g.gain.value = 0; o.stop(); ctx.close(); }, 200);
    } catch {}
}

function showCriticalBanner(data) {
    // Remove existing banner if any
    document.querySelectorAll('.critical-alert-banner').forEach(el => el.remove());
    const risks = data.risk_factors ? data.risk_factors.join(' • ') : 'Unknown threat';
    const banner = document.createElement('div');
    banner.className = 'critical-alert-banner';
    banner.innerHTML = `
        <div class="critical-alert-content">
            <div class="critical-alert-icon">🚨</div>
            <div class="critical-alert-text">
                <strong>CRITICAL ALERT — IMMEDIATE RESPONSE REQUIRED</strong><br>
                <span>Patient: <b>${data.patient_name || 'Unknown'}</b> | Severity: <b>${data.severity}</b></span><br>
                <span>Risk Factors: ${risks}</span>
                ${data.report_id ? `<br><a href="#" onclick="openReportModal('${data.report_id}');document.querySelector('.critical-alert-banner')?.remove();return false;" style="color:#fff;text-decoration:underline;font-weight:600;">OPEN REPORT →</a>` : ''}
            </div>
            <button class="critical-alert-close" onclick="this.parentElement.parentElement.remove()">✕</button>
        </div>
    `;
    document.body.prepend(banner);
    // Auto-dismiss after 15 seconds
    setTimeout(() => banner.remove(), 15000);
}


// ═══════════════════════════════════════════════════════════
//  LIVE FEED
// ═══════════════════════════════════════════════════════════

function renderLiveFeed() {
    const c = document.getElementById('liveFeedList');
    if (!c) return;
    if (!liveReports.length) { c.innerHTML = '<div class="empty-state"><div class="empty-icon">📡</div><p>Waiting for incoming cases...</p></div>'; return; }
    c.innerHTML = liveReports.map((r, i) => renderLiveCard(r, i === 0)).join('');
    setTimeout(() => document.querySelectorAll('.live-card.new-arrival').forEach(el => el.classList.remove('new-arrival')), 3000);
}

function renderLiveCard(r, isNew) {
    const time = new Date(r.timestamp).toLocaleTimeString();
    const preview = (r.situation_description || '').slice(0, 100);
    const cb = r.needs_human_callback ? '<span class="ambulance-badge yes" style="margin:0;padding:0.2rem 0.6rem;font-size:0.7rem;">Callback Needed</span>' : '';
    const isLive = r.confidence === 0 || (r.reasoning && r.reasoning.includes('currently interviewing'));
    const liveTag = isLive ? '<span class="live-tag">🔴 LIVE</span>' : '';
    return `
    <div class="live-card ${r.severity} ${isNew ? 'new-arrival' : ''} ${isLive ? 'live-active' : ''}" onclick="openReportModal('${r.report_id}')">
        <div class="live-card-header">
            <div class="live-card-header-left">
                <span class="severity-tag ${r.severity}">${sevEmoji[r.severity]} ${r.severity}</span>
                <span style="font-weight:600;">P${r.estimated_response_priority}</span>
                ${liveTag}
                ${cb}
            </div>
            <div class="live-card-header-right">
                <span>${srcIcon[r.input_source] || '📝'} ${r.input_source}</span>
                <span>${time}</span>
            </div>
        </div>
        <div class="live-card-body">
            <div class="live-card-details">
                <div class="detail-item"><span class="detail-label">Patient:</span><span class="detail-value ${r.patient_name ? '' : 'streaming'}">${r.patient_name || (isLive ? '⏳ waiting...' : '—')}</span></div>
                <div class="detail-item"><span class="detail-label">Age:</span><span class="detail-value ${r.age != null ? '' : 'streaming'}">${r.age != null ? r.age : (isLive ? '⏳' : '—')}</span></div>
                <div class="detail-item"><span class="detail-label">Location:</span><span class="detail-value ${r.location ? '' : 'streaming'}">${r.location || (isLive ? '⏳ waiting...' : '—')}</span></div>
                <div class="detail-item"><span class="detail-label">Conscious:</span><span class="detail-value">${r.is_conscious === true ? 'Yes' : r.is_conscious === false ? 'NO' : (isLive ? '⏳' : '?')}</span></div>
                <div class="detail-item"><span class="detail-label">Breathing:</span><span class="detail-value">${r.is_breathing === true ? 'Yes' : r.is_breathing === false ? 'NO' : (isLive ? '⏳' : '?')}</span></div>
                <div class="detail-item"><span class="detail-label">Bleeding:</span><span class="detail-value">${r.has_heavy_bleeding === true ? 'YES' : r.has_heavy_bleeding === false ? 'No' : (isLive ? '⏳' : '?')}</span></div>
            </div>
            ${preview ? `<div class="live-card-report">${escapeHtml(preview)}</div>` : ''}
            ${r.detected_risk_factors && r.detected_risk_factors.length ? `<div style="margin-top:0.4rem;"><span style="color:var(--critical);font-size:0.8rem;font-weight:600;">Risk: ${r.detected_risk_factors.join(', ')}</span></div>` : ''}
        </div>
        <div class="live-card-actions">
            <button class="btn btn-outline btn-sm" onclick="event.stopPropagation(); openReportModal('${r.report_id}')">Full Report</button>
            ${!isLive ? `<button class="btn btn-outline btn-sm" onclick="event.stopPropagation(); downloadReportPDF('${r.report_id}')">PDF</button>` : ''}
            ${r.needs_human_callback && r.callback_status === 'pending' && !isLive ? `<button class="btn btn-primary btn-sm" onclick="event.stopPropagation(); markCallback('${r.report_id}','in_progress')">Take Callback</button>` : ''}
        </div>
    </div>`;
}


// ═══════════════════════════════════════════════════════════
//  CALLBACK QUEUE
// ═══════════════════════════════════════════════════════════

async function loadCallbacks() {
    const c = document.getElementById('callbackList');
    if (!c) return;
    c.innerHTML = '<div class="loading">Loading...</div>';
    try {
        const r = await fetch(API + '/api/reports/pending');
        const data = await r.json();
        if (!data.length) { c.innerHTML = '<div class="empty-state"><div class="empty-icon">✅</div><p>No pending callbacks</p></div>'; return; }
        c.innerHTML = data.map(rpt => renderLiveCard(rpt, false)).join('');
    } catch { c.innerHTML = '<div class="empty-state"><p>Failed to load</p></div>'; }
}

async function markCallback(id, status) {
    try {
        await fetch(API + `/api/triage/${id}/callback?status=${status}`, { method: 'PATCH' });
        toast(`Callback ${status === 'in_progress' ? 'taken' : status}!`);
        loadCallbacks();
        updateCallbackBadge();
    } catch { toast('Failed to update', 'error'); }
}

async function updateCallbackBadge() {
    try {
        const r = await fetch(API + '/api/reports/pending');
        const data = await r.json();
        const badge = document.getElementById('callbackBadge');
        if (data.length > 0) { badge.textContent = data.length; badge.style.display = 'inline'; }
        else { badge.style.display = 'none'; }
    } catch {}
}


// ═══════════════════════════════════════════════════════════
//  MANUAL INTAKE
// ═══════════════════════════════════════════════════════════

async function submitIntake(e) {
    e.preventDefault();
    const btn = document.getElementById('intakeBtn');
    btn.querySelector('.btn-text').style.display = 'none';
    btn.querySelector('.btn-loading').style.display = 'inline';
    btn.disabled = true;

    const boolVal = v => v === 'true' ? true : v === 'false' ? false : null;
    const body = {
        is_conscious: boolVal(document.getElementById('fConscious').value),
        is_breathing: boolVal(document.getElementById('fBreathing').value),
        has_heavy_bleeding: boolVal(document.getElementById('fBleeding').value),
        patient_name: document.getElementById('fName').value.trim() || null,
        age: document.getElementById('fAge').value ? parseInt(document.getElementById('fAge').value) : null,
        gender: document.getElementById('fGender').value || null,
        location: document.getElementById('fLocation').value.trim() || null,
        is_trapped: boolVal(document.getElementById('fTrapped').value),
        indoor_outdoor: document.getElementById('fIndoor').value || null,
        situation_description: document.getElementById('fSituation').value.trim(),
        disaster_type: document.getElementById('fDisaster').value || null,
        num_victims: document.getElementById('fVictims').value ? parseInt(document.getElementById('fVictims').value) : null,
        environmental_dangers: document.getElementById('fDangers').value.trim() || null,
    };

    try {
        const r = await fetch(API + '/api/triage/text', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || 'Failed');
        renderIntakeResult(data);
        toast('Case classified and logged!');
    } catch (err) { toast(err.message, 'error'); }
    finally {
        btn.disabled = false;
        btn.querySelector('.btn-text').style.display = 'inline';
        btn.querySelector('.btn-loading').style.display = 'none';
    }
}

function renderIntakeResult(r) {
    const c = document.getElementById('intakeResult');
    c.innerHTML = `
        <div class="severity-banner ${r.severity}">
            <span>${sevEmoji[r.severity]} ${r.severity} — Priority ${r.estimated_response_priority}/10</span>
            <span style="font-size:0.85rem;font-weight:400;">${Math.round(r.confidence * 100)}% confidence</span>
        </div>
        <div class="result-body">
            <div class="ambulance-badge ${r.needs_human_callback ? 'yes' : 'no'}">
                ${r.needs_human_callback ? 'HUMAN CALLBACK REQUIRED' : 'Logged — callback optional'}
            </div>
            <div class="result-section"><h4>Risk Factors</h4><p>${r.detected_risk_factors.length ? r.detected_risk_factors.join(', ') : 'None detected'}</p></div>
            <div class="result-section"><h4>Reasoning</h4><p>${escapeHtml(r.reasoning)}</p></div>
            <div class="result-actions">
                <button class="btn btn-outline btn-sm" onclick="openReportModal('${r.report_id}')">Full Report</button>
                <button class="btn btn-outline btn-sm" onclick="downloadReportPDF('${r.report_id}')">PDF</button>
            </div>
        </div>`;
    c.style.display = 'block';
    c.scrollIntoView({ behavior: 'smooth' });
}


// ═══════════════════════════════════════════════════════════
//  REPORT HISTORY
// ═══════════════════════════════════════════════════════════

async function loadReports() {
    const c = document.getElementById('reportsList');
    c.innerHTML = '<div class="loading">Loading...</div>';
    const p = new URLSearchParams();
    const sev = document.getElementById('filterSeverity').value;
    const src = document.getElementById('filterSource').value;
    const cb = document.getElementById('filterCallback').value;
    if (sev) p.set('severity', sev);
    if (src) p.set('input_source', src);
    if (cb) p.set('callback_status', cb);
    p.set('limit', '100');
    try {
        const r = await fetch(API + '/api/reports?' + p.toString());
        const data = await r.json();
        if (!data.length) { c.innerHTML = '<div class="empty-state"><div class="empty-icon">📋</div><p>No reports.</p></div>'; return; }
        c.innerHTML = data.map(rpt => {
            const time = new Date(rpt.timestamp).toLocaleString();
            const preview = (rpt.situation_description || '').slice(0, 70);
            return `<div class="report-row" onclick="openReportModal('${rpt.report_id}')">
                <span class="severity-tag ${rpt.severity}">${sevEmoji[rpt.severity]} ${rpt.severity}</span>
                <span class="report-preview">${rpt.patient_name || '—'} | ${escapeHtml(preview)}</span>
                <span class="report-source">${srcIcon[rpt.input_source] || '📝'}</span>
                <span class="report-time">${time}</span>
            </div>`;
        }).join('');
    } catch { c.innerHTML = '<div class="empty-state"><p>Failed to load.</p></div>'; }
}


// ═══════════════════════════════════════════════════════════
//  REPORT MODAL + HUMAN↔VICTIM CHAT
// ═══════════════════════════════════════════════════════════

// Store chat messages per report
const chatMessages = {};
let currentModalReportId = null;

async function openReportModal(id) {
    try {
        const r = await fetch(API + `/api/reports/${id}`);
        const d = await r.json();
        if (!r.ok) throw new Error();
        currentModalReportId = id;
        if (!chatMessages[id]) chatMessages[id] = [];

        const isTelegram = d.input_source === 'telegram';
        const mc = document.getElementById('modalContent');
        mc.innerHTML = `
            <div class="severity-banner ${d.severity}" style="border-radius:var(--radius-sm);">
                <span>${sevEmoji[d.severity]} ${d.severity} — Priority ${d.estimated_response_priority}/10</span>
                <span style="font-size:0.85rem;font-weight:400;">${Math.round(d.confidence * 100)}%</span>
            </div>
            <div style="margin-top:1rem;">
                <div class="ambulance-badge ${d.needs_human_callback ? 'yes' : 'no'}">
                    ${d.needs_human_callback ? 'CALLBACK REQUIRED — ' + d.callback_status : 'Logged'}
                </div>
                <div class="result-meta">
                    <div class="meta-item"><div class="meta-label">Patient</div><div class="meta-value">${d.patient_name || '—'}</div></div>
                    <div class="meta-item"><div class="meta-label">Age</div><div class="meta-value">${d.age != null ? d.age : '—'}</div></div>
                    <div class="meta-item"><div class="meta-label">Gender</div><div class="meta-value">${d.gender || '—'}</div></div>
                    <div class="meta-item"><div class="meta-label">Source</div><div class="meta-value">${srcIcon[d.input_source] || '💬'} ${d.input_source}</div></div>
                    <div class="meta-item"><div class="meta-label">Time</div><div class="meta-value">${new Date(d.timestamp).toLocaleString()}</div></div>
                </div>
                <div class="result-section"><h4>Safety Assessment</h4>
                    <div class="result-meta">
                        <div class="meta-item"><div class="meta-label">Conscious</div><div class="meta-value">${d.is_conscious === true ? 'Yes' : d.is_conscious === false ? 'NO' : 'Unknown'}</div></div>
                        <div class="meta-item"><div class="meta-label">Breathing</div><div class="meta-value">${d.is_breathing === true ? 'Yes' : d.is_breathing === false ? 'NO' : 'Unknown'}</div></div>
                        <div class="meta-item"><div class="meta-label">Heavy Bleeding</div><div class="meta-value">${d.has_heavy_bleeding === true ? 'YES' : d.has_heavy_bleeding === false ? 'No' : 'Unknown'}</div></div>
                        <div class="meta-item"><div class="meta-label">Trapped</div><div class="meta-value">${d.is_trapped === true ? 'YES' : d.is_trapped === false ? 'No' : 'Unknown'}</div></div>
                    </div>
                </div>
                <div class="result-section"><h4>Location</h4><p>${d.location || 'Not provided'} ${d.indoor_outdoor ? `(${d.indoor_outdoor})` : ''}</p></div>
                <div class="result-section"><h4>Situation</h4><p style="background:var(--bg-input);padding:0.75rem;border-radius:var(--radius-sm);border-left:3px solid var(--accent);">${escapeHtml(d.situation_description)}</p></div>
                <div class="result-section"><h4>Details</h4>
                    <div class="result-meta">
                        <div class="meta-item"><div class="meta-label">Disaster</div><div class="meta-value">${d.disaster_type || '—'}</div></div>
                        <div class="meta-item"><div class="meta-label">Victims</div><div class="meta-value">${d.num_victims != null ? d.num_victims : '—'}</div></div>
                        <div class="meta-item"><div class="meta-label">Dangers</div><div class="meta-value">${d.environmental_dangers || '—'}</div></div>
                    </div>
                </div>
                <div class="result-section"><h4>AI Classification</h4><p>${escapeHtml(d.reasoning)}</p>
                    ${d.detected_risk_factors.length ? `<p style="margin-top:0.5rem;color:var(--critical);font-weight:600;">Risk factors: ${d.detected_risk_factors.join(', ')}</p>` : ''}
                </div>
                ${d.conversation_transcript ? `<div class="result-section"><h4>Conversation Transcript</h4><pre style="background:var(--bg-input);padding:0.75rem;border-radius:var(--radius-sm);font-size:0.8rem;white-space:pre-wrap;color:var(--text-dim);">${escapeHtml(d.conversation_transcript)}</pre></div>` : ''}

                ${isTelegram ? `
                <div class="result-section operator-chat-section">
                    <h4>💬 Chat with Victim (via Telegram)</h4>
                    <p style="font-size:0.8rem;color:var(--text-dim);margin-bottom:0.5rem;">Send messages directly to the victim on Telegram. Their replies will appear here in real-time.</p>
                    <div class="operator-chat-messages" id="operatorChatMessages"></div>
                    <div class="operator-chat-input">
                        <input type="text" id="operatorChatInput" placeholder="Type a message to the victim..." onkeydown="if(event.key==='Enter')sendOperatorMessage('${d.report_id}')">
                        <button class="btn btn-primary btn-sm" onclick="sendOperatorMessage('${d.report_id}')">Send</button>
                    </div>
                </div>
                ` : ''}

                <div class="result-actions">
                    <button class="btn btn-outline btn-sm" onclick="downloadReportPDF('${d.report_id}')">PDF</button>
                    <button class="btn btn-outline btn-sm" onclick="copyJSON('${d.report_id}')">Copy JSON</button>
                    ${d.needs_human_callback && d.callback_status === 'pending' ? `<button class="btn btn-primary btn-sm" onclick="markCallback('${d.report_id}','in_progress'); closeModal();">Take Callback</button>` : ''}
                    ${d.callback_status === 'in_progress' ? `<button class="btn btn-outline btn-sm" style="border-color:var(--low);color:var(--low);" onclick="markCallback('${d.report_id}','completed'); closeModal();">Mark Complete</button>` : ''}
                </div>
            </div>`;
        document.getElementById('modalOverlay').classList.add('open');

        // Render existing chat messages
        if (isTelegram) renderOperatorChat(id);
    } catch { toast('Failed to load report.', 'error'); }
}

function renderOperatorChat(reportId) {
    const container = document.getElementById('operatorChatMessages');
    if (!container) return;
    const msgs = chatMessages[reportId] || [];
    if (!msgs.length) {
        container.innerHTML = '<div style="text-align:center;color:var(--text-dim);font-size:0.8rem;padding:1rem;">No messages yet. Send a message to start chatting with the victim.</div>';
        return;
    }
    container.innerHTML = msgs.map(m => {
        const time = new Date(m.timestamp).toLocaleTimeString();
        const isOperator = m.sender === 'operator';
        return `<div class="op-chat-msg ${isOperator ? 'op-sent' : 'op-received'}">
            <div class="op-chat-bubble ${isOperator ? 'sent' : 'received'}">
                <span class="op-chat-sender">${isOperator ? '👨‍⚕️ ' + (m.sender_name || 'Responder') : '🆘 Victim'}</span>
                <span class="op-chat-text">${escapeHtml(m.message)}</span>
                <span class="op-chat-time">${time}</span>
            </div>
        </div>`;
    }).join('');
    container.scrollTop = container.scrollHeight;
}

async function sendOperatorMessage(reportId) {
    const input = document.getElementById('operatorChatInput');
    if (!input) return;
    const msg = input.value.trim();
    if (!msg) return;
    input.value = '';
    input.disabled = true;

    const senderName = currentUser ? currentUser.full_name : 'Responder';

    try {
        const r = await fetch(API + `/api/reports/${reportId}/message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: msg, sender_name: senderName }),
        });
        if (!r.ok) {
            const d = await r.json();
            toast(d.detail || 'Failed to send message', 'error');
        }
    } catch {
        toast('Failed to send message', 'error');
    } finally {
        input.disabled = false;
        input.focus();
    }
}

function closeModal() {
    document.getElementById('modalOverlay').classList.remove('open');
    currentModalReportId = null;
}


// ═══════════════════════════════════════════════════════════
//  DASHBOARD
// ═══════════════════════════════════════════════════════════

async function loadDashboard() {
    try {
        const [statsR, reportsR] = await Promise.all([fetch(API + '/api/reports/stats'), fetch(API + '/api/reports?limit=10')]);
        const stats = await statsR.json();
        const reports = await reportsR.json();
        document.getElementById('statTotal').textContent = stats.total_reports;
        document.getElementById('statCritical').textContent = stats.severity_distribution.CRITICAL || 0;
        document.getElementById('statHigh').textContent = stats.severity_distribution.HIGH || 0;
        document.getElementById('statModerate').textContent = stats.severity_distribution.MODERATE || 0;
        document.getElementById('statLow').textContent = stats.severity_distribution.LOW || 0;
        const dist = stats.severity_distribution;
        const mx = Math.max(...Object.values(dist), 1);
        document.getElementById('chartBars').innerHTML = ['CRITICAL', 'HIGH', 'MODERATE', 'LOW'].map(l => {
            const n = dist[l] || 0;
            return `<div class="chart-bar-row"><span class="chart-bar-label">${l}</span><div class="chart-bar-track"><div class="chart-bar-fill ${l}" style="width:${Math.max(n/mx*100,5)}%">${n}</div></div></div>`;
        }).join('');
        const el = document.getElementById('recentReports');
        if (!reports.length) { el.innerHTML = '<div class="empty-state"><p>No cases yet.</p></div>'; return; }
        el.innerHTML = reports.map(r => {
            const time = new Date(r.timestamp).toLocaleTimeString();
            const name = r.patient_name || 'Unknown';
            return `<div class="recent-item" style="cursor:pointer" onclick="openReportModal('${r.report_id}')">
                <span class="severity-tag ${r.severity}">${sevEmoji[r.severity]} ${r.severity}</span>
                <span>${srcIcon[r.input_source] || '📝'}</span>
                <span class="recent-text">${escapeHtml(name)} — ${escapeHtml((r.situation_description||'').slice(0,50))}</span>
                ${r.needs_human_callback && r.callback_status === 'pending' ? '<span style="color:var(--critical);font-size:0.75rem;font-weight:600;">CALLBACK</span>' : ''}
                <span class="recent-time">${time}</span>
            </div>`;
        }).join('');
    } catch { toast('Failed to load dashboard.', 'error'); }
}


// ═══════════════════════════════════════════════════════════
//  HELPERS
// ═══════════════════════════════════════════════════════════

function downloadReportPDF(id) { window.open(API + `/api/reports/${id}/pdf`, '_blank'); }
function downloadSummaryPDF() { window.open(API + '/api/reports/pdf/summary', '_blank'); }
async function copyJSON(id) {
    try { const r = await fetch(API + `/api/reports/${id}`); const d = await r.json(); await navigator.clipboard.writeText(JSON.stringify(d, null, 2)); toast('Copied!'); }
    catch { toast('Failed', 'error'); }
}


// ═══════════════════════════════════════════════════════════
//  INIT — check auth first
// ═══════════════════════════════════════════════════════════

checkAuth();
setInterval(checkHealth, 15000);
