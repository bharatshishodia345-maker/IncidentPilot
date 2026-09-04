/**
 * IncidentPilot — Real-time AI Co-Commander & Agora Live War Room
 */

// Voice State Machine
const VoiceState = {
  IDLE: 'IDLE',
  LISTENING: 'LISTENING',
  THINKING: 'THINKING',
  SPEAKING: 'SPEAKING',
  WAITING_FOR_USER: 'WAITING_FOR_USER',
};

// Application State
const state = {
  currentIncidentId: null,
  incidents: [],
  currentRole: 'incident_commander',
  currentUser: {
    id: '00000000-0000-0000-0000-000000000001',
    name: 'Alice (Commander)',
    email: 'commander@example.test',
  },
  token: null,
  agoraClient: null,
  localAudioTrack: null,
  micStream: null,
  speechRecognition: null,
  isVoiceConnected: false,
  isMuted: false,
  voiceState: VoiceState.IDLE,
  detectedLanguage: 'english', // 'english', 'hindi', 'hinglish'
  lastSpokenText: '',
  lastIngestedText: '',
  lastIngestedTime: 0,
  isAnalyzing: false,
  isSpeakingTTS: false, // Explicit TTS active flag (prevents SR restart race)
  conversationTurn: 0,  // Tracks which turn we are in the conversation
  audioContext: null,
  analyser: null,
  micSource: null,
  participants: [],
  intelligence: {
    facts: [],
    hypotheses: [],
    conflicts: [],
    unknowns: [],
    actions: [],
    decisions: [],
    timeline: [],
    summary: '',
  },
  transcriptHistory: [],
};

// DOM Elements Cache
const elements = {
  incidentSelect: document.getElementById('incident-select'),
  severityBadge: document.getElementById('incident-severity-badge'),
  statusBadge: document.getElementById('incident-status-badge'),
  btnDeclareModal: document.getElementById('btn-declare-modal'),
  declareModal: document.getElementById('declare-modal'),
  btnCloseDeclareModal: document.getElementById('btn-close-declare-modal'),
  btnCancelDeclare: document.getElementById('btn-cancel-declare'),
  declareForm: document.getElementById('declare-incident-form'),
  roleSelect: document.getElementById('principal-role-select'),

  // Voice Elements
  voiceStatus: document.getElementById('voice-connection-status'),
  agoraChannelName: document.getElementById('agora-channel-name'),
  audioActivityStatus: document.getElementById('audio-activity-status'),
  btnJoinVoice: document.getElementById('btn-join-voice'),
  btnToggleMic: document.getElementById('btn-toggle-mic'),
  btnLeaveVoice: document.getElementById('btn-leave-voice'),
  audioCanvas: document.getElementById('audio-canvas'),
  participantList: document.getElementById('participant-list'),
  participantCount: document.getElementById('participant-count'),
  btnRefreshPresence: document.getElementById('btn-refresh-presence'),
  btnSpeakSummary: document.getElementById('btn-speak-summary'),
  aiSpokenText: document.getElementById('ai-spoken-text'),
  micErrorBanner: document.getElementById('mic-error-banner'),
  micErrorMessage: document.getElementById('mic-error-message'),
  liveSpeechBox: document.getElementById('live-speech-box'),
  liveInterimText: document.getElementById('live-interim-text'),

  // Intelligence Tabs & Matrix
  tabBtns: document.querySelectorAll('.tab-btn'),
  tabContents: document.querySelectorAll('.tab-content'),
  factsContainer: document.getElementById('facts-container'),
  hypothesesContainer: document.getElementById('hypotheses-container'),
  conflictsContainer: document.getElementById('conflicts-container'),
  unknownsContainer: document.getElementById('unknowns-container'),
  remediationsContainer: document.getElementById('remediations-container'),
  conflictBadge: document.getElementById('conflict-badge'),
  approvalBadge: document.getElementById('approval-badge'),
  btnRunPaymentDemo: document.getElementById('btn-run-payment-demo'),

  // Transcript & Timeline
  transcriptFeed: document.getElementById('transcript-feed'),
  transcriptForm: document.getElementById('transcript-form'),
  speakerInput: document.getElementById('speaker-input'),
  utteranceInput: document.getElementById('utterance-input'),
  lifecycleStepper: document.getElementById('lifecycle-stepper'),
  timelineStream: document.getElementById('timeline-stream'),
  auditStream: document.getElementById('audit-stream'),
  btnAddNoteModal: document.getElementById('btn-add-note-modal'),
};

// ==========================================================================
// Voice State Management
// ==========================================================================

function setVoiceState(newState) {
  const oldState = state.voiceState;
  state.voiceState = newState;
  console.info(`[VoiceState] State transition: ${oldState} -> ${newState}`);

  if (!state.isVoiceConnected) {
    elements.audioActivityStatus.textContent = 'Join voice room to transmit';
    elements.voiceStatus.className = 'connection-tag disconnected';
    elements.voiceStatus.textContent = 'Disconnected';
    return;
  }

  if (state.isMuted) {
    elements.audioActivityStatus.textContent = 'Microphone Muted';
    elements.voiceStatus.className = 'connection-tag connected';
    elements.voiceStatus.textContent = 'Muted';
    return;
  }

  const hasActiveMic = Boolean(state.localAudioTrack || state.micStream);

  switch (newState) {
    case VoiceState.LISTENING:
      elements.audioActivityStatus.textContent = hasActiveMic
        ? 'Microphone Active — listening for incident statements'
        : 'Mic unavailable — text input mode';
      elements.voiceStatus.className = 'connection-tag connected';
      elements.voiceStatus.textContent = hasActiveMic ? 'Microphone ON' : 'Connected (No Mic)';
      if (elements.liveInterimText) elements.liveInterimText.textContent = 'Listening for speech...';
      break;

    case VoiceState.THINKING:
      elements.audioActivityStatus.textContent = '⚡ AI Co-Commander analyzing statement...';
      if (elements.liveInterimText) elements.liveInterimText.textContent = 'Processing speech with AI co-commander...';
      break;

    case VoiceState.SPEAKING:
      elements.audioActivityStatus.textContent = '🔊 AI Co-Commander speaking into room...';
      if (elements.liveInterimText) elements.liveInterimText.textContent = 'AI is speaking...';
      break;

    case VoiceState.WAITING_FOR_USER:
      elements.audioActivityStatus.textContent = 'Microphone Active — waiting for response';
      elements.voiceStatus.className = 'connection-tag connected';
      elements.voiceStatus.textContent = hasActiveMic ? 'Microphone ON' : 'Connected (No Mic)';
      if (elements.liveInterimText) elements.liveInterimText.textContent = 'Listening for next statement...';
      // Automatically transition to LISTENING
      state.voiceState = VoiceState.LISTENING;
      break;

    case VoiceState.IDLE:
    default:
      elements.audioActivityStatus.textContent = 'Join voice room to transmit';
      elements.voiceStatus.className = 'connection-tag disconnected';
      elements.voiceStatus.textContent = 'Disconnected';
      break;
  }
}

// ==========================================================================
// Authentication & Token Generator Helper
// ==========================================================================

async function authenticatePersona(role = 'incident_commander') {
  try {
    const res = await fetch('/v1/identity/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role: role }),
    });
    if (res.ok) {
      const data = await res.json();
      state.token = data.access_token;
      state.currentRole = data.principal.role;
      state.currentUser = {
        id: data.principal.user_id,
        name: data.display_name,
        email: data.email,
      };
      if (elements.roleSelect) {
        elements.roleSelect.value = state.currentRole;
      }
      if (elements.speakerInput) {
        elements.speakerInput.value = data.display_name;
      }
      updateRoleBadges();
      return true;
    }
  } catch (err) {
    console.warn('Failed to fetch persona token:', err);
  }
  return false;
}

function getAuthHeaders() {
  const headers = {
    'Content-Type': 'application/json',
    'X-Request-ID': 'web-' + Math.random().toString(36).substring(2, 9),
  };
  if (state.token) {
    headers['Authorization'] = `Bearer ${state.token}`;
  }
  return headers;
}

// ==========================================================================
// Initialization
// ==========================================================================

async function init() {
  setupEventListeners();
  initVisualizer();
  await authenticatePersona(state.currentRole);
  await loadIncidents();
}

function setupEventListeners() {
  // Incident Selector
  elements.incidentSelect.addEventListener('change', (e) => {
    if (e.target.value) {
      selectIncident(e.target.value);
    }
  });

  // Declare Incident Modal
  elements.btnDeclareModal.addEventListener('click', () => {
    elements.declareModal.classList.remove('hidden');
    elements.declareModal.setAttribute('aria-hidden', 'false');
  });

  const closeModal = () => {
    elements.declareModal.classList.add('hidden');
    elements.declareModal.setAttribute('aria-hidden', 'true');
  };

  elements.btnCloseDeclareModal.addEventListener('click', closeModal);
  elements.btnCancelDeclare.addEventListener('click', closeModal);

  elements.declareForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const title = document.getElementById('new-incident-title').value;
    const severity = document.getElementById('new-incident-severity').value;
    const statusVal = document.getElementById('new-incident-status').value;
    await declareIncident(title, severity, statusVal);
    closeModal();
  });

  // Persona switch
  elements.roleSelect.addEventListener('change', async (e) => {
    state.currentRole = e.target.value;
    await authenticatePersona(state.currentRole);
    if (state.currentIncidentId) {
      await refreshPresence();
    }
  });

  // Voice Controls
  elements.btnJoinVoice.addEventListener('click', joinVoiceRoom);
  elements.btnToggleMic.addEventListener('click', toggleMicrophone);
  elements.btnLeaveVoice.addEventListener('click', leaveVoiceRoom);
  elements.btnRefreshPresence.addEventListener('click', refreshPresence);
  elements.btnSpeakSummary.addEventListener('click', () => speakCurrentSummary());

  // Tabs
  elements.tabBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      elements.tabBtns.forEach((b) => b.classList.remove('active'));
      elements.tabContents.forEach((c) => c.classList.remove('active'));

      btn.classList.add('active');
      const tabId = btn.getAttribute('data-tab');
      document.getElementById(tabId).classList.add('active');
    });
  });

  // Demo Runner
  elements.btnRunPaymentDemo.addEventListener('click', runPaymentOutageDemo);

  // Transcript Form
  elements.transcriptForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const speaker = elements.speakerInput.value.trim() || state.currentUser.name;
    const text = elements.utteranceInput.value.trim();
    if (!text) return;

    elements.utteranceInput.value = '';
    await ingestUtterance(speaker, text);
  });

  // Lifecycle Steps
  elements.lifecycleStepper.querySelectorAll('.step-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const targetStatus = btn.getAttribute('data-target-status');
      await transitionIncidentStatus(targetStatus);
    });
  });

  // Add Note Button
  if (elements.btnAddNoteModal) {
    elements.btnAddNoteModal.addEventListener('click', () => {
      const note = prompt('Enter a timeline note or status update:');
      if (note && note.trim()) {
        addTimelineEvent(note.trim(), 'note');
        addAuditLog(`Responder added timeline note: "${note.trim()}"`, 'user');
      }
    });
  }
}

function updateRoleBadges() {
  const isCommander = state.currentRole === 'incident_commander';
  elements.lifecycleStepper.querySelectorAll('.step-btn').forEach((btn) => {
    btn.disabled = !isCommander;
    if (!isCommander) {
      btn.title = 'Restricted to Incident Commanders';
    } else {
      btn.title = '';
    }
  });
}

// ==========================================================================
// Incident Data & Lifecycle Management
// ==========================================================================

async function loadIncidents() {
  try {
    const res = await fetch('/v1/incidents', { headers: getAuthHeaders() });
    if (!res.ok) {
      await createInitialSeedIncident();
      return;
    }
    const data = await res.json();
    state.incidents = data;

    if (data.length === 0) {
      await createInitialSeedIncident();
      return;
    }

    renderIncidentSelect(data);
    selectIncident(data[0].id);
  } catch (err) {
    console.warn('API error loading incidents:', err);
    renderOfflineIncident();
  }
}

async function createInitialSeedIncident() {
  try {
    const payload = {
      title: 'Payment Gateway 503 Authorization Outage',
      severity: 'sev1',
      status: 'open',
    };
    const res = await fetch('/v1/incidents', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      const created = await res.json();
      state.incidents = [created];
      renderIncidentSelect(state.incidents);
      selectIncident(created.id);
    }
  } catch (err) {
    console.error('Failed to create seed incident:', err);
  }
}

function renderIncidentSelect(incidents) {
  elements.incidentSelect.innerHTML = incidents
    .map((inc) => `<option value="${inc.id}">${inc.title} (${inc.severity.toUpperCase()})</option>`)
    .join('');
}

function selectIncident(incidentId) {
  state.currentIncidentId = incidentId;
  const inc = state.incidents.find((i) => i.id === incidentId);

  // Clear conversation state for the selected incident
  state.transcriptHistory = [];
  state.conversationTurn = 0;
  state.detectedLanguage = 'english';
  state.intelligence = {
    facts: [],
    hypotheses: [],
    conflicts: [],
    unknowns: [],
    actions: [],
    decisions: [],
    timeline: [],
    summary: '',
  };
  renderTranscript();
  renderIntelligence(state.intelligence);
  renderCommanderState(null);
  elements.aiSpokenText.textContent = 'Incident co-commander ready. Join live voice room to transmit statements.';

  if (inc) {
    updateIncidentHeader(inc);
    elements.agoraChannelName.textContent = `Channel: incident-${incidentId.substring(0, 8)}`;
  }
  refreshPresence();
  refreshTimeline();
}

function updateIncidentHeader(inc) {
  elements.severityBadge.className = `severity-pill ${inc.severity.toLowerCase()}`;
  elements.severityBadge.textContent = inc.severity.toUpperCase();

  elements.statusBadge.className = `status-pill ${inc.status.toLowerCase()}`;
  elements.statusBadge.textContent = inc.status.toUpperCase();

  // Update lifecycle buttons
  elements.lifecycleStepper.querySelectorAll('.step-btn').forEach((btn) => {
    if (btn.getAttribute('data-target-status') === inc.status.toLowerCase()) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
}

async function declareIncident(title, severity, statusVal) {
  try {
    const payload = { title, severity, status: statusVal };
    const res = await fetch('/v1/incidents', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      const created = await res.json();
      state.incidents.unshift(created);
      renderIncidentSelect(state.incidents);
      selectIncident(created.id);
      addAuditLog(`Incident "${title}" declared as ${severity.toUpperCase()}`, 'user');
    }
  } catch (err) {
    console.error('Error declaring incident:', err);
  }
}

async function transitionIncidentStatus(newStatus) {
  if (!state.currentIncidentId) return;
  try {
    const res = await fetch(`/v1/incidents/${state.currentIncidentId}/status`, {
      method: 'PATCH',
      headers: getAuthHeaders(),
      body: JSON.stringify({ status: newStatus }),
    });
    if (res.ok) {
      const updated = await res.json();
      const idx = state.incidents.findIndex((i) => i.id === updated.id);
      if (idx !== -1) state.incidents[idx] = updated;
      updateIncidentHeader(updated);
      addTimelineEvent(`Status changed to ${newStatus.toUpperCase()}`, 'status_change');
      addAuditLog(`Status transitioned to ${newStatus.toUpperCase()}`, 'user');
    } else {
      const err = await res.json();
      alert(`Invalid transition: ${err.detail}`);
    }
  } catch (err) {
    console.error('Status transition error:', err);
  }
}

// ==========================================================================
// Agora Live Voice Room Implementation
// ==========================================================================

async function joinVoiceRoom() {
  if (!state.currentIncidentId) {
    console.warn('[VoiceRoom] Cannot join voice room: No active incident selected.');
    return;
  }

  elements.btnJoinVoice.disabled = true;
  elements.btnJoinVoice.textContent = 'Connecting...';
  elements.micErrorBanner.classList.add('hidden');

  try {
    // 1. Check audio input device availability
    let audioDevices = [];
    if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
      try {
        const allDevices = await navigator.mediaDevices.enumerateDevices();
        audioDevices = allDevices.filter((d) => d.kind === 'audioinput');
        if (audioDevices.length > 0) {
          console.info(`[VoiceRoom] Audio input device available: "${audioDevices[0].label || 'Default Microphone'}" (Total input devices detected: ${audioDevices.length})`);
        } else {
          console.warn('[VoiceRoom] Audio input device NOT available: No microphone input hardware found.');
        }
      } catch (enumErr) {
        console.warn('[VoiceRoom] Device enumeration warning:', enumErr.message);
      }
    }

    // 2. Query browser microphone permission state if Permissions API supported
    if (navigator.permissions && navigator.permissions.query) {
      try {
        const permStatus = await navigator.permissions.query({ name: 'microphone' });
        console.info(`[VoiceRoom] Initial browser microphone permission status: ${permStatus.state}`);
        permStatus.onchange = () => {
          console.info(`[VoiceRoom] Microphone permission state changed to: ${permStatus.state}`);
        };
      } catch (_) {
        // Permissions API query for microphone not supported in all browsers
      }
    }

    // 3. Obtain Agora RTC token & room configuration from backend
    const joinRes = await fetch(`/v1/incidents/${state.currentIncidentId}/room/join`, {
      method: 'POST',
      headers: getAuthHeaders(),
    });

    let roomData = {
      app_id: 'dev-incidentpilot-app',
      channel_name: `incident-${state.currentIncidentId}`,
      token: 'dev-token',
      uid: state.currentUser.id,
      is_publisher: true,
      participants: [],
    };

    if (joinRes.ok) {
      roomData = await joinRes.json();
      console.info(`[VoiceRoom] Obtained room authorization for channel "${roomData.channel_name}" (uid: ${roomData.uid}, publisher: ${roomData.is_publisher})`);
    } else {
      console.warn('[VoiceRoom] Backend join returned non-OK status, falling back to local session');
    }

    // 4. Acquire Real Microphone Track
    let localTrack = null;
    let micStream = null;

    if (window.AgoraRTC) {
      try {
        localTrack = await AgoraRTC.createMicrophoneAudioTrack({
          encoderConfig: 'speech_standard',
          AEC: true,
          ANS: true,
          AGC: true,
        });
        state.localAudioTrack = localTrack;
        console.info('[VoiceRoom] Microphone permission granted.');
        console.info(`[VoiceRoom] Local audio track created: Track ID=${localTrack.getTrackId()}`);

        localTrack.on('track-ended', () => {
          console.warn('[VoiceRoom] Audio state change: local audio track ended unexpectedly.');
        });

        const mediaStreamTrack = localTrack.getMediaStreamTrack();
        micStream = new MediaStream([mediaStreamTrack]);
        state.micStream = micStream;
      } catch (agoraTrackErr) {
        console.warn('[VoiceRoom] AgoraRTC.createMicrophoneAudioTrack failed, trying getUserMedia fallback:', agoraTrackErr.message || agoraTrackErr);
        try {
          micStream = await navigator.mediaDevices.getUserMedia({
            audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
          });
          state.micStream = micStream;
          console.info('[VoiceRoom] Microphone permission granted via getUserMedia.');
          localTrack = AgoraRTC.createCustomAudioTrack({
            mediaStreamTrack: micStream.getAudioTracks()[0],
          });
          state.localAudioTrack = localTrack;
          console.info(`[VoiceRoom] Local custom audio track created: Track ID=${localTrack.getTrackId()}`);
        } catch (gumErr) {
          console.error('[VoiceRoom] Microphone permission denied or capture failed:', gumErr.message || gumErr);
          elements.micErrorMessage.textContent = `Microphone Error: ${gumErr.message || gumErr.name || 'Permission Denied'}. Please allow microphone permissions in your browser.`;
          elements.micErrorBanner.classList.remove('hidden');
        }
      }
    } else {
      try {
        micStream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
        state.micStream = micStream;
        console.info('[VoiceRoom] Microphone permission granted via getUserMedia.');
      } catch (gumErr) {
        console.error('[VoiceRoom] Microphone permission denied or capture failed:', gumErr.message || gumErr);
        elements.micErrorMessage.textContent = `Microphone Error: ${gumErr.message || gumErr.name || 'Permission Denied'}. Please allow microphone permissions in your browser.`;
        elements.micErrorBanner.classList.remove('hidden');
      }
    }

    // 5. Connect mic stream to Web Audio AnalyserNode for live visualizer
    if (state.micStream) {
      try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        state.audioContext = new AudioCtx();
        state.analyser = state.audioContext.createAnalyser();
        state.analyser.fftSize = 256;
        state.micSource = state.audioContext.createMediaStreamSource(state.micStream);
        state.micSource.connect(state.analyser);
      } catch (audioCtxErr) {
        console.warn('[VoiceRoom] Web Audio Analyser setup warning:', audioCtxErr.message);
      }
    }

    // 6. Connect Agora Client, Join RTC Channel, and Publish Track
    if (window.AgoraRTC) {
      try {
        state.agoraClient = AgoraRTC.createClient({ mode: 'rtc', codec: 'vp8' });

        state.agoraClient.on('connection-state-change', (curState, prevState, reason) => {
          console.info(`[VoiceRoom] Agora client connection state changed: ${prevState} -> ${curState} (${reason})`);
        });

        state.agoraClient.on('user-joined', (user) => {
          console.info(`[VoiceRoom] Remote users detected: UID=${user.uid} entered the channel`);
          addAuditLog(`Remote responder ${user.uid} joined Agora voice room`, 'system');
          refreshPresence();
        });

        state.agoraClient.on('user-left', (user, reason) => {
          console.info(`[VoiceRoom] Remote users detected: UID=${user.uid} left the channel (${reason})`);
          addAuditLog(`Responder ${user.uid} left Agora voice room`, 'system');
          refreshPresence();
        });

        state.agoraClient.on('user-published', async (user, mediaType) => {
          console.info(`[VoiceRoom] Remote user published ${mediaType}: UID=${user.uid}`);
          await state.agoraClient.subscribe(user, mediaType);
          if (mediaType === 'audio' && user.audioTrack) {
            user.audioTrack.play();
            console.info(`[VoiceRoom] Audio playback active for remote responder UID=${user.uid}`);
          }
        });

        state.agoraClient.on('user-unpublished', (user, mediaType) => {
          console.info(`[VoiceRoom] Remote user unpublished ${mediaType}: UID=${user.uid}`);
        });

        await state.agoraClient.join(
          roomData.app_id,
          roomData.channel_name,
          roomData.token,
          roomData.uid
        );
        console.info(`[VoiceRoom] Agora client joined channel: "${roomData.channel_name}" as UID: "${roomData.uid}"`);

        if (state.localAudioTrack && roomData.is_publisher) {
          await state.agoraClient.publish([state.localAudioTrack]);
          console.info('[VoiceRoom] Local audio track published to Agora RTC channel.');
        }
      } catch (agoraErr) {
        console.warn('[VoiceRoom] Agora client connection notice:', agoraErr.message || agoraErr);
      }
    }

    // 7. Start continuous SpeechRecognition listener for voice-to-AI pipeline
    startSpeechRecognition();

    // 8. Update UI State & Voice State Machine
    const hasActiveMic = Boolean(state.localAudioTrack || state.micStream);
    state.isVoiceConnected = true;
    state.isMuted = false;

    setVoiceState(VoiceState.LISTENING);

    if (hasActiveMic) {
      elements.liveSpeechBox.classList.remove('hidden');
    } else {
      elements.liveSpeechBox.classList.add('hidden');
    }

    elements.btnJoinVoice.style.display = 'none';
    elements.btnToggleMic.disabled = false;
    elements.btnLeaveVoice.disabled = false;

    addAuditLog(`Joined voice channel "${roomData.channel_name}"${hasActiveMic ? ' with active microphone' : ' (no mic)'}`, 'user');
    await refreshPresence();
  } catch (err) {
    console.error('[VoiceRoom] Failed to join voice room:', err);
    elements.voiceStatus.textContent = 'Connection Failed';
    elements.btnJoinVoice.disabled = false;
    elements.btnJoinVoice.textContent = 'Join Live Room';
  }
}

/**
 * Starts continuous browser SpeechRecognition with echo isolation and state machine gating.
 */
function startSpeechRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    console.warn('[SpeechRecognition] Web Speech API not supported in this browser. You can still transmit statements via the Live Transcript input.');
    return;
  }

  if (state.speechRecognition) {
    state.speechRecognition.onend = null;
    state.speechRecognition.onerror = null;
    try { state.speechRecognition.stop(); } catch (_) {}
    state.speechRecognition = null;
  }

  const recognition = new SR();
  recognition.continuous = true;
  recognition.interimResults = true;
  // Language-adaptive: match SR lang to detected conversation language
  // Hindi and Hinglish both use hi-IN for best coverage of mixed Roman Hindi
  const srLangMap = { english: 'en-US', hindi: 'hi-IN', hinglish: 'hi-IN' };
  recognition.lang = srLangMap[state.detectedLanguage] || 'en-US';
  recognition.maxAlternatives = 1;
  state.speechRecognition = recognition;

  recognition.onstart = () => {
    console.info('[SpeechRecognition] Started — continuous voice recognition active.');
  };

  recognition.onresult = (event) => {
    // ECHO / SELF-LISTENING PROTECTION:
    // If AI is currently SPEAKING or Web Speech Synthesis is active, discard immediately.
    if (state.voiceState === VoiceState.SPEAKING || (window.speechSynthesis && window.speechSynthesis.speaking)) {
      console.info('[SpeechRecognition] Discarded speech during AI speaking state (self-echo protection)');
      return;
    }

    let interim = '';
    let finalText = '';

    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcript = event.results[i][0].transcript;
      if (event.results[i].isFinal) {
        finalText += transcript;
      } else {
        interim += transcript;
      }
    }

    if (elements.liveInterimText && (interim || finalText)) {
      elements.liveInterimText.textContent = interim || finalText || 'Listening...';
    }

    // On finalized phrase: validate and dispatch
    const cleanFinal = finalText.trim();
    if (cleanFinal && cleanFinal.length >= 3) {
      // Self-echo filter: Check if text is identical to last AI response
      const cleanLower = cleanFinal.toLowerCase();
      const lastSpokenLower = (state.lastSpokenText || '').toLowerCase();
      if (lastSpokenLower && (cleanLower === lastSpokenLower || (cleanLower.length > 12 && lastSpokenLower.includes(cleanLower)))) {
        console.info('[SpeechRecognition] Filtered out AI self-echo phrase:', cleanFinal);
        return;
      }

      // Debounce duplicate utterances within 2 seconds
      const now = Date.now();
      if (cleanFinal === state.lastIngestedText && (now - state.lastIngestedTime) < 2500) {
        console.info('[SpeechRecognition] Ignored duplicate rapid utterance:', cleanFinal);
        return;
      }

      state.lastIngestedText = cleanFinal;
      state.lastIngestedTime = now;

      console.info(`[SpeechRecognition] Final user utterance captured: "${cleanFinal}"`);
      ingestUtterance(state.currentUser.name, cleanFinal);
    }
  };

  recognition.onerror = (event) => {
    if (event.error !== 'no-speech') {
      console.warn(`[SpeechRecognition] Error (${event.error}):`, event);
      if (['network', 'audio-capture'].includes(event.error)) {
        setTimeout(() => {
          if (state.isVoiceConnected && !state.isMuted && state.speechRecognition === recognition) {
            try { recognition.start(); } catch (_) {}
          }
        }, 1500);
      }
    }
  };

  recognition.onend = () => {
    // Auto-restart ONLY when not in SPEAKING state (prevents self-listen race)
    const canRestart = (
      state.isVoiceConnected &&
      !state.isMuted &&
      !state.isSpeakingTTS &&
      state.voiceState !== VoiceState.SPEAKING &&
      state.speechRecognition === recognition
    );
    if (canRestart) {
      setTimeout(() => {
        const stillOk = (
          state.isVoiceConnected &&
          !state.isMuted &&
          !state.isSpeakingTTS &&
          state.voiceState !== VoiceState.SPEAKING &&
          state.speechRecognition === recognition
        );
        if (stillOk) {
          try { recognition.start(); } catch (_) {}
        }
      }, 350);
    }
  };

  try {
    recognition.start();
  } catch (err) {
    console.warn('[SpeechRecognition] Could not start:', err.message);
  }
}

async function toggleMicrophone() {
  if (!state.isVoiceConnected) return;

  state.isMuted = !state.isMuted;
  console.info(`[VoiceRoom] Audio state changes: local microphone ${state.isMuted ? 'MUTED' : 'UNMUTED'}`);

  // Mute/unmute Agora audio track
  if (state.localAudioTrack) {
    try {
      await state.localAudioTrack.setMuted(state.isMuted);
    } catch (muteErr) {
      console.warn('[VoiceRoom] Local audio track setMuted warning:', muteErr.message);
    }
  }

  // Mute/unmute native MediaStream tracks
  if (state.micStream) {
    state.micStream.getAudioTracks().forEach((t) => {
      t.enabled = !state.isMuted;
    });
  }

  // Pause/resume SpeechRecognition
  if (state.speechRecognition) {
    if (state.isMuted) {
      try { state.speechRecognition.stop(); } catch (_) {}
    } else {
      try { state.speechRecognition.start(); } catch (_) {}
    }
  }

  if (state.isMuted) {
    elements.btnToggleMic.classList.add('btn-danger');
    document.getElementById('mic-btn-label').textContent = 'Unmute Mic';
    setVoiceState(VoiceState.IDLE);
    elements.audioActivityStatus.textContent = 'Microphone Muted';
    elements.voiceStatus.textContent = 'Muted';
    elements.liveSpeechBox.classList.add('hidden');
  } else {
    elements.btnToggleMic.classList.remove('btn-danger');
    document.getElementById('mic-btn-label').textContent = 'Mute Mic';
    setVoiceState(VoiceState.LISTENING);
    if (state.micStream) elements.liveSpeechBox.classList.remove('hidden');
  }
}

async function leaveVoiceRoom() {
  if (!state.currentIncidentId) return;

  console.info('[VoiceRoom] Leaving voice room and releasing media resources...');

  try {
    // 1. Cancel any active speech synthesis
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }

    // 2. Stop SpeechRecognition
    if (state.speechRecognition) {
      state.speechRecognition.onend = null;
      state.speechRecognition.onerror = null;
      try { state.speechRecognition.stop(); } catch (_) {}
      state.speechRecognition = null;
    }

    // 3. Close Agora track and leave channel
    if (state.localAudioTrack) {
      state.localAudioTrack.close();
      state.localAudioTrack = null;
      console.info('[VoiceRoom] Audio state changes: local audio track closed.');
    }
    if (state.agoraClient) {
      try {
        await state.agoraClient.leave();
        console.info('[VoiceRoom] Agora client left channel.');
      } catch (leaveErr) {
        console.warn('[VoiceRoom] Agora leave notice:', leaveErr.message);
      }
      state.agoraClient = null;
    }

    // 4. Stop real microphone tracks
    if (state.micStream) {
      state.micStream.getTracks().forEach((t) => {
        t.stop();
      });
      state.micStream = null;
      console.info('[VoiceRoom] Native microphone stream stopped.');
    }

    // 5. Disconnect Web Audio nodes
    if (state.micSource) {
      try { state.micSource.disconnect(); } catch (_) {}
      state.micSource = null;
    }
    if (state.audioContext) {
      try { await state.audioContext.close(); } catch (_) {}
      state.audioContext = null;
      state.analyser = null;
    }

    await fetch(`/v1/incidents/${state.currentIncidentId}/room/leave`, {
      method: 'POST',
      headers: getAuthHeaders(),
    });

    state.isVoiceConnected = false;
    state.isMuted = false;
    setVoiceState(VoiceState.IDLE);

    elements.btnJoinVoice.style.display = 'inline-flex';
    elements.btnJoinVoice.disabled = false;
    elements.btnJoinVoice.textContent = 'Join Live Room';
    elements.btnToggleMic.disabled = true;
    elements.btnLeaveVoice.disabled = true;
    elements.liveSpeechBox.classList.add('hidden');
    elements.micErrorBanner.classList.add('hidden');

    addAuditLog('Left voice room — microphone released', 'user');
    await refreshPresence();
  } catch (err) {
    console.error('[VoiceRoom] Error leaving voice room:', err);
  }
}

async function refreshPresence() {
  if (!state.currentIncidentId) return;
  try {
    const res = await fetch(`/v1/incidents/${state.currentIncidentId}/room/presence`, {
      headers: getAuthHeaders(),
    });
    if (res.ok) {
      const participants = await res.json();
      state.participants = participants;
      renderParticipants(participants);
    }
  } catch (err) {
    renderParticipants([
      { display_name: 'Alice (Commander)', role: 'incident_commander', presence_state: state.isVoiceConnected ? 'joined' : 'left' },
      { display_name: 'Bob (Database Lead)', role: 'responder', presence_state: 'joined' },
      { display_name: 'Charlie (Infra)', role: 'responder', presence_state: 'joined' },
      { display_name: 'Dave (Release Lead)', role: 'responder', presence_state: 'joined' },
    ]);
  }
}

// Helper to escape HTML special characters to prevent XSS
function escapeHTML(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderParticipants(participants) {
  elements.participantCount.textContent = participants.filter((p) => p.presence_state === 'joined').length;
  elements.participantList.innerHTML = participants
    .map(
      (p) => `
      <div class="participant-card">
        <div class="participant-meta">
          <div class="p-avatar">${escapeHTML(p.display_name.charAt(0))}</div>
          <div class="p-details">
            <span class="p-name">${escapeHTML(p.display_name)}</span>
            <span class="p-role">${escapeHTML(formatRole(p.role))}</span>
          </div>
        </div>
        <span class="p-status-dot ${escapeHTML(p.presence_state)}" title="${p.presence_state === 'joined' ? 'In Voice Room' : 'Left'}"></span>
      </div>
    `
    )
    .join('');
}

function formatRole(role) {
  if (role === 'incident_commander') return 'Incident Commander';
  if (role === 'responder') return 'Technical Responder';
  return 'Observer';
}

// ==========================================================================
// Waveform Audio Visualizer
// ==========================================================================

function initVisualizer() {
  const canvas = elements.audioCanvas;
  const ctx = canvas.getContext('2d');
  let phase = 0;

  function renderWave() {
    requestAnimationFrame(renderWave);
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    ctx.fillStyle = '#060911';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const isTransmitting = state.isVoiceConnected && !state.isMuted;

    // Draw horizontal grid line
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.04)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, canvas.height / 2);
    ctx.lineTo(canvas.width, canvas.height / 2);
    ctx.stroke();

    ctx.lineWidth = 2;

    if (state.analyser && isTransmitting) {
      const bufferLength = state.analyser.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);
      state.analyser.getByteFrequencyData(dataArray);

      const barWidth = (canvas.width / bufferLength) * 2.5;
      let x = 0;

      for (let i = 0; i < bufferLength; i++) {
        const barHeight = (dataArray[i] / 255) * canvas.height * 0.8;
        const gradient = ctx.createLinearGradient(0, canvas.height, 0, canvas.height - barHeight);
        gradient.addColorStop(0, 'rgba(6, 182, 212, 0.9)');
        gradient.addColorStop(1, 'rgba(99, 102, 241, 0.6)');
        ctx.fillStyle = gradient;
        ctx.fillRect(x, canvas.height - barHeight, barWidth - 1, barHeight);
        x += barWidth;
      }
    } else {
      const baseAmp = isTransmitting ? 6 : 4;
      ctx.strokeStyle = isTransmitting ? '#06b6d4' : '#64748b';
      ctx.beginPath();

      for (let x = 0; x < canvas.width; x++) {
        const y =
          canvas.height / 2 +
          Math.sin(x * 0.04 + phase) * baseAmp * Math.sin(x * 0.01) +
          Math.cos(x * 0.08 - phase) * (baseAmp * 0.5);
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      phase += isTransmitting ? 0.04 : 0.02;
    }
  }

  renderWave();
}

// ==========================================================================
// Incident Intelligence Processing & Live Conversation Flow
// ==========================================================================

async function ingestUtterance(speaker, text) {
  if (!text || !text.trim()) return;
  if (!state.currentIncidentId) return;

  if (state.isAnalyzing) {
    console.warn('[Ingest] Intelligence analysis already in-flight. Skipping duplicate call.');
    return;
  }
  state.isAnalyzing = true;

  setVoiceState(VoiceState.THINKING);

  const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  state.transcriptHistory.push({ speaker, text: text.trim(), time: now });
  renderTranscript();

  // Increment conversation turn for every new user utterance
  state.conversationTurn += 1;

  try {
    const payload = {
      messages: state.transcriptHistory.map((t) => ({
        speaker: t.speaker,
        text: t.text,
        timestamp: new Date().toISOString(),
        source_type: 'voice_transcript',
      })),
      language: state.detectedLanguage,
      conversation_turn: state.conversationTurn,
    };

    const res = await fetch(`/v1/incidents/${state.currentIncidentId}/intelligence/analyze`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(payload),
    });

    if (res.ok) {
      const intelligence = await res.json();
      state.intelligence = intelligence;

      // Update detected language and re-adapt speech recognition language if changed
      if (intelligence.language && intelligence.language !== state.detectedLanguage) {
        const prevLang = state.detectedLanguage;
        state.detectedLanguage = intelligence.language;
        // Restart SR with correct language if voice is active
        if (state.isVoiceConnected && !state.isMuted && prevLang !== intelligence.language) {
          console.info(`[SpeechRecognition] Language changed ${prevLang} → ${intelligence.language}. Restarting SR with correct lang.`);
          startSpeechRecognition();
        }
      } else if (intelligence.language) {
        state.detectedLanguage = intelligence.language;
      }

      renderIntelligence(intelligence);
      renderCommanderState(intelligence);

      // Auto-speak the AI co-commander response in detected language when voice room is active
      if (intelligence.summary) {
        elements.aiSpokenText.textContent = `"${intelligence.summary}"`;
        if (state.isVoiceConnected && !state.isMuted) {
          speakCurrentSummary(intelligence.summary, state.detectedLanguage);
        } else {
          setVoiceState(VoiceState.WAITING_FOR_USER);
        }
      } else {
        setVoiceState(VoiceState.WAITING_FOR_USER);
      }
    } else {
      setVoiceState(VoiceState.WAITING_FOR_USER);
    }
  } catch (err) {
    console.error('Error analyzing intelligence:', err);
    setVoiceState(VoiceState.WAITING_FOR_USER);
  } finally {
    state.isAnalyzing = false;
  }
}

async function runPaymentOutageDemo() {
  if (!state.currentIncidentId) return;

  elements.btnRunPaymentDemo.disabled = true;
  elements.btnRunPaymentDemo.textContent = 'Simulating Outage...';

  try {
    const res = await fetch(`/v1/incidents/${state.currentIncidentId}/intelligence/payment-demo`, {
      headers: getAuthHeaders(),
    });

    if (res.ok) {
      const data = await res.json();
      state.intelligence = data;

      const demoMessages = [
        { speaker: 'Monitoring Bot', text: 'Payment failures reached 42.8% with HTTP 503 responses.' },
        { speaker: 'Alice (Commander)', text: 'I am declaring SEV1. We need to stabilize immediately.' },
        { speaker: 'Bob (Database Lead)', text: 'I suspect database latency spiked to 4500ms and DB pool is saturated.' },
        { speaker: 'Charlie (Infra)', text: 'Wait, database is healthy and CPU is at 12%, but external stripe gateway is throwing timeouts.' },
        { speaker: 'Alice (Commander)', text: 'Does anyone know if canary deployment v2.14 was deployed at 21:45 today?' },
        { speaker: 'Dave (Release Lead)', text: 'Yes, canary deployment v2.14 was deployed at 21:45. I will inspect the diff.' },
        { speaker: 'Alice (Commander)', text: 'We decided to rollback canary deployment v2.14 immediately. Action item: @dave execute rollback.' },
      ];

      state.transcriptHistory = demoMessages.map((m) => ({
        ...m,
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      }));
      renderTranscript();
      renderIntelligence(data);

      if (data.summary) {
        elements.aiSpokenText.textContent = `"${data.summary}"`;
        if (state.isVoiceConnected && !state.isMuted) {
          speakCurrentSummary(data.summary);
        }
      }

      document.getElementById('tab-matrix').click();
      addAuditLog('Executed Payment Outage Scenario Simulation with AI Co-Commander', 'ai');
    }
  } catch (err) {
    console.error('Demo simulation error:', err);
  } finally {
    elements.btnRunPaymentDemo.disabled = false;
    elements.btnRunPaymentDemo.textContent = '⚡ Run Payment Outage Demo';
  }
}

function renderIntelligence(intel) {
  // 1. Facts
  if (intel.facts && intel.facts.length > 0) {
    elements.factsContainer.innerHTML = intel.facts
      .map(
        (f) => `
        <div class="fact-card">
          <div class="card-main-text">${escapeHTML(f.statement)}</div>
          <div class="card-evidence-quote">${escapeHTML(f.evidence)}</div>
          <div class="card-meta-footer">
            <span>Source: ${escapeHTML(f.source)}</span>
            <span>Confidence: ${(f.confidence * 100).toFixed(0)}%</span>
          </div>
        </div>
      `
      )
      .join('');
  } else {
    elements.factsContainer.innerHTML = '<div class="empty-state">No facts extracted yet.</div>';
  }

  // 2. Hypotheses
  if (intel.hypotheses && intel.hypotheses.length > 0) {
    elements.hypothesesContainer.innerHTML = intel.hypotheses
      .map(
        (h) => `
        <div class="hypothesis-card">
          <div class="card-main-text">${escapeHTML(h.statement)}</div>
          <div class="card-meta-footer">
            <span>Proposed by: ${escapeHTML(h.proposed_by)}</span>
            <span class="info-pill status-${escapeHTML(h.status)}">${escapeHTML(h.status).toUpperCase()}</span>
          </div>
        </div>
      `
      )
      .join('');
  } else {
    elements.hypothesesContainer.innerHTML = '<div class="empty-state">No hypotheses active.</div>';
  }

  // 3. Conflicts
  elements.conflictBadge.textContent = (intel.conflicts || []).length;
  if (intel.conflicts && intel.conflicts.length > 0) {
    elements.conflictsContainer.innerHTML = intel.conflicts
      .map(
        (c) => `
        <div class="conflict-card">
          <div class="conflict-title">⚠️ ${escapeHTML(c.description)}</div>
          <div class="claim-row"><strong>Claim A (${escapeHTML(c.source_a)}):</strong> "${escapeHTML(c.claim_a)}"</div>
          <div class="claim-row"><strong>Claim B (${escapeHTML(c.source_b)}):</strong> "${escapeHTML(c.claim_b)}"</div>
          ${c.suggested_verification ? `<div class="resolution-tip">💡 Verification: ${escapeHTML(c.suggested_verification)}</div>` : ''}
        </div>
      `
      )
      .join('');
  } else {
    elements.conflictsContainer.innerHTML = '<div class="empty-state">No contradictions detected.</div>';
  }

  // 4. Unknowns
  if (intel.unknowns && intel.unknowns.length > 0) {
    elements.unknownsContainer.innerHTML = intel.unknowns
      .map(
        (u) => `
        <div class="unknown-card">
          <div class="unknown-question">❓ ${escapeHTML(u.question)}</div>
          <div class="claim-row"><strong>Impact:</strong> ${escapeHTML(u.impact)}</div>
          <div class="resolution-tip">Suggested Inquiry: ${escapeHTML(u.suggested_inquiry)}</div>
        </div>
      `
      )
      .join('');
  } else {
    elements.unknownsContainer.innerHTML = '<div class="empty-state">No critical unknowns identified.</div>';
  }

  // 5. Actions / Remediation Proposals
  elements.approvalBadge.textContent = (intel.actions || []).length;
  if (intel.actions && intel.actions.length > 0) {
    elements.remediationsContainer.innerHTML = intel.actions
      .map(
        (a) => `
        <div class="remediation-card">
          <div class="remediation-meta">
            <h5>${escapeHTML(a.title)}</h5>
            <p>${escapeHTML(a.description || 'Remediation action proposal')} • Assignee: <strong>${escapeHTML(a.assigned_owner || 'Unassigned (Requires Dispatch)')}</strong></p>
          </div>
          <div class="remediation-actions">
            <span class="severity-pill ${escapeHTML(a.urgency.toLowerCase())}">${escapeHTML(a.urgency.toUpperCase())}</span>
            <button class="btn btn-primary btn-xs" onclick="authorizeAction('${escapeHTML(a.id)}', '${escapeHTML(a.title).replace(/'/g, "\\'")}')">
              Authorize Action
            </button>
          </div>
        </div>
      `
      )
      .join('');
  } else {
    elements.remediationsContainer.innerHTML = '<div class="empty-state">No remediation actions pending authorization.</div>';
  }

  // Summary Update
  if (intel.summary) {
    elements.aiSpokenText.textContent = `"${intel.summary}"`;
  }
}

// Global action handler
window.authorizeAction = async function (actionId, title) {
  if (state.currentRole !== 'incident_commander') {
    alert('Permission Denied: Only Incident Commanders can authorize consequential remediations.');
    return;
  }
  if (!state.currentIncidentId) return;

  try {
    const proposeRes = await fetch(`/v1/incidents/${state.currentIncidentId}/actions/propose`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        action_type: 'rollback_deployment',
        title: title || 'Rollback canary release to v2.13.9',
        description: 'Authorized canary rollback to stabilize checkout error rate',
        risk_level: 'high',
        parameters: {
          service_name: 'checkout-service',
          target_version: 'v2.13.9',
          cluster: 'production-primary',
        },
      }),
    });

    if (proposeRes.ok) {
      const proposal = await proposeRes.json();
      const approveRes = await fetch(
        `/v1/incidents/${state.currentIncidentId}/actions/proposals/${proposal.id}/approve`,
        {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({ rationale: 'Confirmed error spike in war room.' }),
        }
      );
      if (approveRes.ok) {
        const executed = await approveRes.json();
        addTimelineEvent(`Authorized & Executed: ${title} (Status: ${executed.status})`, 'action');
        addAuditLog(`Commander authorized execution of "${title}" (receipt_id: ${executed.id})`, 'user');
        alert(`Action "${title}" authorized and executed successfully!`);
        return;
      }
    }
    addTimelineEvent(`Authorized Remediation: ${title}`, 'action');
    addAuditLog(`Human Commander authorized action "${title}"`, 'user');
  } catch (err) {
    console.error('Authorization error:', err);
    addTimelineEvent(`Authorized Remediation: ${title}`, 'action');
    addAuditLog(`Human Commander authorized action "${title}"`, 'user');
  }
};

function renderTranscript() {
  elements.transcriptFeed.innerHTML = state.transcriptHistory
    .map(
      (t) => `
      <div class="transcript-item">
        <span class="speaker-tag">${escapeHTML(t.speaker)}:</span>
        <span class="transcript-text">${escapeHTML(t.text)}</span>
      </div>
    `
    )
    .join('');
  elements.transcriptFeed.scrollTop = elements.transcriptFeed.scrollHeight;
}

// ==========================================================================
// Incident Commander State Dashboard
// ==========================================================================

function renderCommanderState(intel) {
  const panel = document.getElementById('commander-state-panel');
  if (!panel) return;

  if (!intel) {
    panel.innerHTML = `
      <div class="cs-row">
        <span class="cs-label">STATUS</span>
        <span class="cs-value cs-neutral">Awaiting first report</span>
      </div>
      <div class="cs-row">
        <span class="cs-label">GOAL</span>
        <span class="cs-value">Join voice room or type a statement below</span>
      </div>
    `;
    return;
  }

  const rtColors = {
    CLARIFY: 'cs-blue', INVESTIGATE: 'cs-cyan', VERIFY: 'cs-amber',
    COORDINATE: 'cs-purple', WARN: 'cs-red', RECOMMEND: 'cs-green',
    APPROVAL: 'cs-orange', CONFIRM: 'cs-emerald',
  };
  const rtIcons = {
    CLARIFY: '❓', INVESTIGATE: '🔍', VERIFY: '✅', COORDINATE: '📋',
    WARN: '⚠️', RECOMMEND: '💡', APPROVAL: '🛡️', CONFIRM: '🎯',
  };

  const rt = intel.response_type || 'INVESTIGATE';
  const rtClass = rtColors[rt] || 'cs-cyan';
  const rtIcon = rtIcons[rt] || '🔍';

  const rsColors = {
    ACTIVE: 'cs-red', INVESTIGATING: 'cs-amber', MITIGATING: 'cs-orange',
    RECOVERING: 'cs-green', RESOLVED: 'cs-emerald',
  };
  const rs = intel.resolution_state || 'ACTIVE';
  const rsClass = rsColors[rs] || 'cs-amber';

  panel.innerHTML = `
    <div class="cs-row">
      <span class="cs-label">RESPONSE TYPE</span>
      <span class="cs-value cs-pill ${rtClass}">${rtIcon} ${rt}</span>
    </div>
    <div class="cs-row">
      <span class="cs-label">RESOLUTION</span>
      <span class="cs-value cs-pill ${rsClass}">${rs}</span>
    </div>
    <div class="cs-row">
      <span class="cs-label">TURN</span>
      <span class="cs-value cs-neutral">#${state.conversationTurn}</span>
    </div>
    <div class="cs-row cs-goal">
      <span class="cs-label">CURRENT GOAL</span>
      <span class="cs-value">${intel.current_goal || '—'}</span>
    </div>
    ${intel.next_question ? `
    <div class="cs-row cs-question">
      <span class="cs-label">NEXT QUESTION</span>
      <span class="cs-value cs-question-text">"${intel.next_question}"</span>
    </div>` : ''}
    ${intel.recommendation ? `
    <div class="cs-row cs-recommendation">
      <span class="cs-label">RECOMMENDATION</span>
      <span class="cs-value cs-rec-text">💡 ${intel.recommendation}</span>
    </div>` : ''}
  `;
}

// ==========================================================================
// Spoken AI Speech Synthesis
// ==========================================================================

function speakCurrentSummary(customText, lang) {
  const text = (customText || elements.aiSpokenText.textContent).replace(/"/g, '').trim();
  if (!text) return;
  if (!window.speechSynthesis) {
    console.warn('[SpeechSynthesis] Web Speech Synthesis not supported in this browser.');
    return;
  }

  // Cancel previous speech to prevent overlapping queues
  window.speechSynthesis.cancel();

  // Set explicit state — isSpeakingTTS blocks SR restart race
  state.isSpeakingTTS = true;
  setVoiceState(VoiceState.SPEAKING);
  state.lastSpokenText = text;

  // Stop SR while AI is speaking to prevent self-echo
  if (state.speechRecognition) {
    try { state.speechRecognition.stop(); } catch (_) {}
  }

  const currentLang = (lang || state.detectedLanguage || 'english').toLowerCase();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1.0;
  utterance.pitch = 1.0;

  const voices = window.speechSynthesis.getVoices();

  // Language-specific voice resolution
  if (currentLang === 'hindi' || /[\u0900-\u097F]/.test(text)) {
    utterance.lang = 'hi-IN';
    const hindiVoice = voices.find(
      (v) =>
        v.lang &&
        (v.lang.startsWith('hi') || v.name.includes('Hindi') || v.name.includes('हिन्दी') || v.name.includes('Kalpana') || v.name.includes('Swara'))
    );
    if (hindiVoice) utterance.voice = hindiVoice;
  } else if (currentLang === 'hinglish') {
    // Hinglish uses Roman-script Hindi mixed with English technical terms.
    // An Indian-English (en-IN) or Hindi voice provides natural cadence without mangling technical terms.
    utterance.lang = 'en-IN';
    const indianVoice = voices.find(
      (v) =>
        v.lang &&
        (v.lang === 'en-IN' || v.lang.startsWith('en_IN') || v.name.includes('India') || v.name.includes('Heera') || v.name.includes('Ravi') || v.name.includes('Prabhat') || v.lang.startsWith('hi'))
    );
    if (indianVoice) utterance.voice = indianVoice;
  } else {
    // English default
    utterance.lang = 'en-US';
    const englishVoice = voices.find(
      (v) =>
        v.lang &&
        v.lang.startsWith('en') &&
        (v.name.includes('Google') ||
          v.name.includes('Natural') ||
          v.name.includes('Microsoft') ||
          v.name.includes('David') ||
          v.name.includes('Zira') ||
          v.name.includes('Samantha'))
    );
    if (englishVoice) utterance.voice = englishVoice;
  }

  utterance.onstart = () => {
    console.info(`[SpeechSynthesis] Spoken AI response started in [${currentLang.toUpperCase()}]. Voice: ${utterance.voice ? utterance.voice.name : 'Default'}`);
    setVoiceState(VoiceState.SPEAKING);
  };

  utterance.onend = () => {
    console.info('[SpeechSynthesis] Spoken AI response completed.');
    state.isSpeakingTTS = false;
    // Safety delay before returning to listening to prevent speaker echo bleed
    setTimeout(() => {
      if (state.voiceState === VoiceState.SPEAKING) {
        setVoiceState(VoiceState.WAITING_FOR_USER);
      }
      // Re-start SR now that TTS is done
      if (state.isVoiceConnected && !state.isMuted) {
        startSpeechRecognition();
      }
    }, 500);
  };

  utterance.onerror = (e) => {
    console.warn('[SpeechSynthesis] Spoken synthesis error/interrupted:', e);
    state.isSpeakingTTS = false;
    setVoiceState(VoiceState.WAITING_FOR_USER);
    // Re-start SR after error
    if (state.isVoiceConnected && !state.isMuted) {
      setTimeout(() => startSpeechRecognition(), 300);
    }
  };

  window.speechSynthesis.speak(utterance);
}

// ==========================================================================
// Timeline & Audit Logging Feeds
// ==========================================================================

async function refreshTimeline() {
  if (!state.currentIncidentId) return;
  try {
    const res = await fetch(`/v1/incidents/${state.currentIncidentId}`, { headers: getAuthHeaders() });
    if (res.ok) {
      const incident = await res.json();
      if (incident.timeline_events && incident.timeline_events.length > 0) {
        elements.timelineStream.innerHTML = incident.timeline_events
          .map(
            (e) => `
          <div class="timeline-card">
            <div class="timeline-time">${new Date(e.occurred_at).toLocaleTimeString()}</div>
            <div><strong>${(e.event_type || 'EVENT').toUpperCase()}:</strong> ${e.title}${e.details ? ` — <em>${e.details}</em>` : ''}</div>
          </div>
        `
          )
          .join('');
        return;
      }
    }
  } catch (err) {
    console.warn('Error fetching incident timeline:', err);
  }
  elements.timelineStream.innerHTML = `
    <div class="timeline-card">
      <div class="timeline-time">${new Date().toLocaleTimeString()}</div>
      <div><strong>Incident Room Ready:</strong> Co-commander standby.</div>
    </div>
  `;
}

function addTimelineEvent(title, type = 'observation') {
  const time = new Date().toLocaleTimeString();
  const item = document.createElement('div');
  item.className = 'timeline-card';
  item.innerHTML = `
    <div class="timeline-time">${time}</div>
    <div><strong>${type.toUpperCase()}:</strong> ${title}</div>
  `;
  elements.timelineStream.prepend(item);
}

function addAuditLog(description, actorType = 'system') {
  const time = new Date().toLocaleTimeString();
  const item = document.createElement('div');
  item.className = 'audit-card';
  item.innerHTML = `
    <div class="audit-time">${time} • actor=${actorType}</div>
    <div>${description}</div>
  `;
  elements.auditStream.prepend(item);
}

function renderOfflineIncident() {
  const mock = {
    id: '00000000-0000-0000-0000-000000000001',
    title: 'Payment Gateway 503 Authorization Outage',
    severity: 'sev1',
    status: 'open',
  };
  state.incidents = [mock];
  renderIncidentSelect(state.incidents);
  selectIncident(mock.id);
}

// Launch application on DOM load
window.addEventListener('DOMContentLoaded', init);
