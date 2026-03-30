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
const alarmsPanel = document.getElementById('alarmsPanel');
const alarmsList = document.getElementById('alarmsList');

const STATUS_LABELS = {
    idle: '待机中',
    listening: '聆听中...',
    processing: '思考中...',
    speaking: '回复中...',
};

let ws = null;
let micActive = false;
let micSending = false;  // controls whether audio frames are actually sent
let audioContext = null;
let micStream = null;
let scriptProcessor = null;
let reconnectTimer = null;
let voiceEnabled = true;

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
        // 3 rounds of double-beep (like a classic alarm)
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
        case 'alarm':
            showAlarm(msg);
            break;
        case 'audio':
            if (voiceEnabled) playAudioChunk(msg.data);
            break;
    }
}

function updateState(state) {
    statusDot.className = 'status-dot ' + state;
    statusText.textContent = STATUS_LABELS[state] || state;
    // Show stop button when processing or speaking
    stopBtn.style.display = (state === 'processing' || state === 'speaking') ? 'flex' : 'none';
}

// ---- Stop / interrupt ----
stopBtn.addEventListener('click', () => {
    send({ type: 'command', action: 'stop' });
});

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
    // 1. Stop sending audio frames immediately
    micSending = false;
    micActive = false;
    micBtn.classList.remove('active');

    // 2. Tear down audio pipeline
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

    // 3. Tell server to process after all audio frames have stopped
    send({ type: 'mic_stop' });
}

micBtn.addEventListener('click', toggleMic);

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

// ---- Alarm display ----
function showAlarm(msg) {
    playAlarmSound();
    alarmsPanel.style.display = 'block';
    const item = document.createElement('div');
    item.className = 'alarm-item';
    item.innerHTML = `<span>${msg.label || 'Alarm'}</span><span>${msg.time || ''}</span>`;
    alarmsList.appendChild(item);
    appendMessage('assistant', `Alarm: ${msg.label || 'Alarm'}`);
}

// ---- Init ----
connect();
