// Jarvis Voice Assistant — Frontend
const WS_URL = `ws://${location.host}/ws`;

const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const conversation = document.getElementById('conversation');
const textInput = document.getElementById('textInput');
const sendBtn = document.getElementById('sendBtn');
const micBtn = document.getElementById('micBtn');
const voiceToggleBtn = document.getElementById('voiceToggleBtn');
const stopBtn = document.getElementById('stopBtn');
const taskListEl = document.getElementById('taskList');
const tasksEmptyState = document.getElementById('tasksEmptyState');
const tasksBadge = document.getElementById('tasks-badge');

const STATUS_LABELS = {
    idle: '待机中',
    listening: '聆听中...',
    processing: '思考中...',
    speaking: '回复中...',
};

const TASK_TYPE_LABELS = {
    reminder: '提醒',
    action: '操作',
    recurring: '循环',
};

let ws = null;
let currentTab = 'chat';
let micActive = false;
let micSending = false;
let audioContext = null;
let micStream = null;
let scriptProcessor = null;
let reconnectTimer = null;
let voiceEnabled = true;

// Always-listen mode: continuous audio streaming for server-side wake word detection
let alwaysListening = false;
let listenAudioCtx = null;
let listenMicStream = null;
let listenProcessor = null;

// ---- Tab switching ----
document.querySelectorAll('.tab-btn[data-tab]').forEach(btn => {
    btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;
        if (tab) switchTab(tab);
    });
});

function switchTab(name) {
    currentTab = name;
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(`tab-${name}`).classList.add('active');
    document.querySelector(`[data-tab="${name}"]`).classList.add('active');
    document.getElementById('input-bar').style.display = name === 'chat' ? '' : 'none';
    if (name === 'tasks') clearTasksBadge();
}

function showTasksBadge() {
    tasksBadge.hidden = false;
}

function clearTasksBadge() {
    tasksBadge.hidden = true;
}

// ---- Sound effects (Web Audio API) ----
function playNotificationSound() {
    try {
        const ctx = new AudioContext();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.value = 880;
        osc.type = 'sine';
        gain.gain.setValueAtTime(0.3, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.3);
    } catch (e) {}
}

function playAlarmSound() {
    try {
        const ctx = new AudioContext();
        const t = ctx.currentTime;
        const notes = [
            [t + 0.0, 1047], [t + 0.15, 1319],
            [t + 0.5, 1047], [t + 0.65, 1319],
            [t + 1.0, 1047], [t + 1.15, 1319],
        ];
        notes.forEach(([start, freq]) => {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.frequency.value = freq;
            osc.type = 'sine';
            gain.gain.setValueAtTime(0.4, start);
            gain.gain.exponentialRampToValueAtTime(0.01, start + 0.12);
            osc.start(start);
            osc.stop(start + 0.12);
        });
    } catch (e) {}
}

// ---- WebSocket ----
function connect() {
    if (ws && ws.readyState <= 1) return;
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
        console.log('[ws] connected');
        if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
        startAlwaysListen();
    };

    ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        handleMessage(msg);
    };

    ws.onclose = () => {
        console.log('[ws] disconnected, reconnecting...');
        reconnectTimer = setTimeout(connect, 2000);
    };

    ws.onerror = () => ws.close();
}

function send(msg) {
    if (ws && ws.readyState === 1) {
        ws.send(JSON.stringify(msg));
    }
}

// ---- Message handling ----
function handleMessage(msg) {
    switch (msg.type) {
        case 'state_change':
            updateState(msg.state);
            break;
        case 'user_message':
            appendMessage('user', msg.text);
            break;
        case 'assistant_message':
            appendMessage('assistant', msg.text);
            break;
        case 'error':
            appendMessage('error', msg.text);
            break;
        case 'wake_detected':
            playNotificationSound();
            break;
        case 'scheduled_task_fire':
            handleTaskFire(msg.task);
            break;
        case 'tasks_updated':
            renderTaskList(msg.tasks);
            break;
        case 'audio':
            if (voiceEnabled) playAudioChunk(msg.data);
            break;
    }
}

function updateState(state) {
    statusDot.className = 'status-dot ' + state;
    statusText.textContent = STATUS_LABELS[state] || state;
    stopBtn.style.display = (state === 'processing' || state === 'speaking') ? 'flex' : 'none';
}

// ---- Stop / interrupt ----
stopBtn.addEventListener('click', () => {
    send({ type: 'command', action: 'stop' });
});

// ---- Chat messages ----
function appendMessage(role, text) {
    const welcome = conversation.querySelector('.welcome-msg');
    if (welcome) welcome.remove();

    const div = document.createElement('div');
    div.className = `msg ${role}`;
    if (role === 'assistant' && typeof marked !== 'undefined') {
        div.innerHTML = marked.parse(text);
    } else {
        div.textContent = text;
    }
    conversation.appendChild(div);
    conversation.scrollTop = conversation.scrollHeight;
}

function appendChatNotification(label) {
    const welcome = conversation.querySelector('.welcome-msg');
    if (welcome) welcome.remove();

    const div = document.createElement('div');
    div.className = 'msg notification';
    div.innerHTML = `<span class="notification-icon">&#128276;</span> ${escapeHtml(label)}`;
    conversation.appendChild(div);
    conversation.scrollTop = conversation.scrollHeight;
}

function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}

// ---- Task fire handling ----
function handleTaskFire(task) {
    playAlarmSound();
    appendChatNotification(task.label || 'Task fired');
    if (currentTab !== 'chat') showTasksBadge();
}

// ---- Task list rendering ----
function renderTaskList(tasks) {
    // Remove all task rows (keep empty state element)
    taskListEl.querySelectorAll('.task-row').forEach(el => el.remove());

    if (!tasks || tasks.length === 0) {
        tasksEmptyState.style.display = '';
        return;
    }

    tasksEmptyState.style.display = 'none';

    tasks.forEach(task => {
        const row = document.createElement('div');
        row.className = 'task-row';
        row.dataset.taskId = task.id;

        const isActive = task.status === 'active';
        const typeLabel = TASK_TYPE_LABELS[task.type] || task.type;

        row.innerHTML = `
            <label class="task-toggle">
                <input type="checkbox" ${isActive ? 'checked' : ''}>
                <span class="task-toggle-slider"></span>
            </label>
            <div class="task-info">
                <span class="task-label ${!isActive ? 'task-inactive' : ''}">${escapeHtml(task.label)}</span>
                <span class="task-meta">
                    <span class="type-badge type-${task.type}">${typeLabel}</span>
                    ${task.fire_at ? `<span class="task-time">${formatFireAt(task.fire_at)}</span>` : ''}
                    ${task.cron_expr ? `<span class="task-time">${escapeHtml(task.cron_expr)}</span>` : ''}
                </span>
            </div>
            <span class="task-status-label ${task.status}">${formatStatus(task.status)}</span>
        `;

        const checkbox = row.querySelector('input[type="checkbox"]');
        checkbox.addEventListener('change', () => {
            toggleTask(task.id, task.status);
        });

        taskListEl.appendChild(row);
    });
}

function toggleTask(taskId, currentStatus) {
    const action = currentStatus === 'active' ? 'cancel' : 'reactivate';
    send({ type: 'task_toggle', task_id: taskId, action });
}

function formatFireAt(isoStr) {
    try {
        const d = new Date(isoStr);
        return d.toLocaleString('zh-CN', {
            month: 'numeric',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    } catch {
        return isoStr;
    }
}

function formatStatus(status) {
    const labels = { active: '活跃', fired: '已触发', cancelled: '已取消' };
    return labels[status] || status;
}

// ---- Text input ----
function sendText() {
    const text = textInput.value.trim();
    if (!text) return;
    send({ type: 'text_input', text, voice_reply: voiceEnabled });
    textInput.value = '';
}

sendBtn.addEventListener('click', sendText);
textInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendText();
    }
});

// ---- Voice reply toggle ----
voiceToggleBtn.addEventListener('click', () => {
    voiceEnabled = !voiceEnabled;
    voiceToggleBtn.classList.toggle('active', voiceEnabled);
    voiceToggleBtn.title = voiceEnabled ? '语音回复: 开' : '语音回复: 关';
});

// ---- Browser microphone ----
async function toggleMic() {
    if (micActive) {
        stopMic();
    } else {
        await startMic();
    }
}

async function startMic() {
    try {
        micStream = await navigator.mediaDevices.getUserMedia({
            audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true }
        });
        audioContext = new AudioContext({ sampleRate: 16000 });
        const source = audioContext.createMediaStreamSource(micStream);

        scriptProcessor = audioContext.createScriptProcessor(2048, 1, 1);
        scriptProcessor.onaudioprocess = (e) => {
            if (!micSending) return;
            const data = e.inputBuffer.getChannelData(0);
            const int16 = new Int16Array(data.length);
            for (let i = 0; i < data.length; i++) {
                int16[i] = Math.max(-32768, Math.min(32767, Math.round(data[i] * 32767)));
            }
            const bytes = new Uint8Array(int16.buffer);
            const b64 = btoa(String.fromCharCode(...bytes));
            send({ type: 'audio_chunk', data: b64, sample_rate: 16000 });
        };
        source.connect(scriptProcessor);
        scriptProcessor.connect(audioContext.destination);

        micActive = true;
        micSending = true;
        micBtn.classList.add('active');
        playNotificationSound();
        send({ type: 'mic_start', voice_reply: voiceEnabled });
    } catch (err) {
        console.error('Mic error:', err);
        appendMessage('error', 'Mic error: ' + err.message);
    }
}

function stopMic() {
    micSending = false;
    micActive = false;
    micBtn.classList.remove('active');

    if (scriptProcessor) {
        scriptProcessor.disconnect();
        scriptProcessor = null;
    }
    if (micStream) {
        micStream.getTracks().forEach(t => t.stop());
        micStream = null;
    }
    if (audioContext) {
        audioContext.close();
        audioContext = null;
    }

    send({ type: 'mic_stop' });
}

micBtn.addEventListener('click', toggleMic);

// ---- Always-listen mode (server-side wake word) ----
async function startAlwaysListen() {
    if (alwaysListening) return;
    try {
        listenMicStream = await navigator.mediaDevices.getUserMedia({
            audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true }
        });
        listenAudioCtx = new AudioContext({ sampleRate: 16000 });
        await listenAudioCtx.resume();
        const source = listenAudioCtx.createMediaStreamSource(listenMicStream);

        listenProcessor = listenAudioCtx.createScriptProcessor(2048, 1, 1);
        listenProcessor.onaudioprocess = (e) => {
            const data = e.inputBuffer.getChannelData(0);
            const int16 = new Int16Array(data.length);
            for (let i = 0; i < data.length; i++) {
                int16[i] = Math.max(-32768, Math.min(32767, Math.round(data[i] * 32767)));
            }
            const bytes = new Uint8Array(int16.buffer);
            const b64 = btoa(String.fromCharCode(...bytes));
            send({ type: 'audio_chunk', data: b64, sample_rate: 16000 });
        };
        source.connect(listenProcessor);
        listenProcessor.connect(listenAudioCtx.destination);

        alwaysListening = true;
    } catch (err) {
        console.error('Always-listen error:', err);
    }
}

// ---- Audio playback (TTS from server) ----
async function playAudioChunk(b64Data) {
    if (!b64Data || !voiceEnabled) return;
    try {
        const ctx = new AudioContext();
        const binary = atob(b64Data);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        const buffer = await ctx.decodeAudioData(bytes.buffer);
        const source = ctx.createBufferSource();
        source.buffer = buffer;
        source.connect(ctx.destination);
        source.start();
    } catch (err) {
        console.error('Audio playback error:', err);
    }
}

// ---- Init ----
connect();
