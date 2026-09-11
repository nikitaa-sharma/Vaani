import { useEffect, useRef, useState, useCallback } from 'react';
import '@livekit/components-styles';
import {
  LiveKitRoom,
  RoomAudioRenderer,
  BarVisualizer,
  useVoiceAssistant,
  useLocalParticipant,
  useRoomContext,
} from '@livekit/components-react';
import { RoomEvent, type TranscriptionSegment, type Participant } from 'livekit-client';
import './App.css';
import femaleVoiceImg from './assets/female-voice.png';
import maleVoiceImg from './assets/male-voice.png';

interface TranscriptItem {
  id: string;
  sender: 'vaani' | 'user';
  text: string;
  timestamp: string;
  isFinal?: boolean;
}

const DEFAULT_WELCOME_MESSAGE: TranscriptItem = {
  id: 'welcome-0',
  sender: 'vaani',
  text: "Namaste! I'm Vaani, your AI voice assistant. How can I help you today?",
  timestamp: 'Just now',
  isFinal: true,
};

function formatCurrentTime(): string {
  const now = new Date();
  return now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function SoundwaveIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className="voice-modal-soundwave" aria-hidden="true">
      <rect x="3" y="9" width="3" height="6" rx="1.5" fill="url(#wave-grad)" />
      <rect x="8" y="5" width="3" height="14" rx="1.5" fill="url(#wave-grad)" />
      <rect x="13" y="3" width="3" height="18" rx="1.5" fill="url(#wave-grad)" />
      <rect x="18" y="8" width="3" height="8" rx="1.5" fill="url(#wave-grad)" />
      <defs>
        <linearGradient id="wave-grad" x1="3" y1="3" x2="21" y2="21" gradientUnits="userSpaceOnUse">
          <stop stopColor="#818cf8" />
          <stop offset="1" stopColor="#c084fc" />
        </linearGradient>
      </defs>
    </svg>
  );
}

/* Avatar images are imported from src/assets/ */

interface EmailRecipient {
  name: string;
  email: string;
}

interface MultipleMatchResult {
  queryName: string;
  recipients: EmailRecipient[];
}

function parseMultipleMatchRecipients(text: string): MultipleMatchResult | null {
  const queryMatch = text.match(/Multiple recent recipients match\s+['"]?([^'":]+)['"]?:/i);
  if (!queryMatch) return null;

  const queryName = queryMatch[1].trim();
  const afterColon = text.slice((queryMatch.index ?? 0) + queryMatch[0].length);

  const pleaseIdx = afterColon.search(/\bPlease specify\b/i);
  const optionsText = pleaseIdx >= 0 ? afterColon.slice(0, pleaseIdx) : afterColon;

  const regex = /(?:([^<,]+?)\s*)?<([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})>/g;
  const recipients: EmailRecipient[] = [];
  let m: RegExpExecArray | null;
  while ((m = regex.exec(optionsText)) !== null) {
    recipients.push({
      name: m[1]?.trim() || '',
      email: m[2].trim(),
    });
  }

  return recipients.length > 0 ? { queryName, recipients } : null;
}

function getInitials(name: string, email: string): string {
  if (name && name.trim()) {
    const parts = name.trim().split(/\s+/);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return name.trim().slice(0, 2).toUpperCase();
  }
  return email.trim().slice(0, 2).toUpperCase();
}

interface RecipientPickerProps {
  recipients: EmailRecipient[];
  queryName?: string;
  onSelect: (recipient: EmailRecipient) => void;
  onClose: () => void;
}

function RecentRecipientPicker({
  recipients,
  queryName,
  onSelect,
  onClose,
}: RecipientPickerProps) {
  return (
    <div className="recent-recipients-overlay" role="dialog" aria-label="Choose Email Recipient">
      <div className="recent-recipients-card">
        <div className="recipients-card-header">
          <div className="recipients-header-title">
            <div className="recipients-icon-badge" aria-hidden="true">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
                <circle cx="11" cy="7" r="4" />
                <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
                <path d="M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
            </div>
            <div>
              <h3 className="recipients-title">Choose Recipient</h3>
              <p className="recipients-subtitle">
                {queryName
                  ? `Multiple contacts match "${queryName}". Tap one to select:`
                  : 'Multiple matching contacts found. Tap one to select:'}
              </p>
            </div>
          </div>
          <button
            type="button"
            className="recipients-close-btn"
            onClick={onClose}
            aria-label="Close recipient picker"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <div className="recipients-list" role="list">
          {recipients.map((r, idx) => (
            <button
              key={`${r.email}-${idx}`}
              type="button"
              className="recipient-item-btn"
              role="listitem"
              onClick={() => onSelect(r)}
            >
              <div className="recipient-avatar" aria-hidden="true">
                {getInitials(r.name, r.email)}
              </div>
              <div className="recipient-info">
                <span className="recipient-name">{r.name || 'Unnamed Contact'}</span>
                <span className="recipient-email">{r.email}</span>
              </div>
              <div className="recipient-select-arrow" aria-hidden="true">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              </div>
            </button>
          ))}
        </div>

        <div className="recipients-footer">
          <button
            type="button"
            className="recipients-new-btn"
            onClick={onClose}
          >
            <span>+ Enter new address / Speak address</span>
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * VaaniScreen renders the active voice assistant UI inside the LiveKitRoom context.
 */
function VaaniScreen({
  onEndCall,
  selectedVoice,
}: {
  onEndCall: () => void;
  selectedVoice: 'female' | 'male';
}) {
  const room = useRoomContext();
  const { state: agentState, audioTrack } = useVoiceAssistant();
  const { isMicrophoneEnabled, localParticipant } = useLocalParticipant();

  const [transcripts, setTranscripts] = useState<TranscriptItem[]>([DEFAULT_WELCOME_MESSAGE]);
  const [multipleMatchingRecipients, setMultipleMatchingRecipients] = useState<EmailRecipient[]>([]);
  const [multipleMatchingQuery, setMultipleMatchingQuery] = useState<string>('');
  const [showRecipientPicker, setShowRecipientPicker] = useState(false);
  const resolvedMatchKeysRef = useRef<Set<string>>(new Set());
  const activeMatchKeyRef = useRef<string | null>(null);
  const transcriptContainerRef = useRef<HTMLDivElement | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);

  // Sync chosen voice to room participant attributes and data channel
  useEffect(() => {
    if (!room || !localParticipant) return;
    try {
      localParticipant.setAttributes({ voice: selectedVoice });
      const payload = new TextEncoder().encode(
        JSON.stringify({ type: 'set_voice', voice: selectedVoice })
      );
      localParticipant.publishData(payload, { reliable: true });
    } catch (e) {
      console.debug('Voice attribute sync:', e);
    }
  }, [room, localParticipant, selectedVoice]);

  // Auto-scroll transcript container only when new messages arrive, without shifting the page or header
  useEffect(() => {
    if (transcripts.length > 1 && transcriptContainerRef.current) {
      transcriptContainerRef.current.scrollTo({
        top: transcriptContainerRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, [transcripts]);

  // Listen for LiveKit transcription events for both user and agent
  useEffect(() => {
    if (!room) return;

    const handleTranscription = (
      segments: TranscriptionSegment[],
      participant?: Participant
    ) => {
      const isUser = participant?.isLocal ?? false;
      const sender = isUser ? 'user' : 'vaani';

      setTranscripts((prev) => {
        let updated = [...prev];
        for (const seg of segments) {
          const text = seg.text.trim();
          if (!text) continue;

          // Only show recipient picker if Vaani explicitly states multiple recent recipients match
          if (!isUser && /multiple recent recipients match/i.test(text)) {
            const matchKey = seg.id || text.slice(0, 40);
            if (
              !resolvedMatchKeysRef.current.has(matchKey) &&
              activeMatchKeyRef.current !== matchKey
            ) {
              const parsed = parseMultipleMatchRecipients(text);
              if (parsed && parsed.recipients.length > 1) {
                setMultipleMatchingRecipients(parsed.recipients);
                setMultipleMatchingQuery(parsed.queryName);
                activeMatchKeyRef.current = matchKey;
                setShowRecipientPicker(true);
              }
            }
          }

          const existingIndex = updated.findIndex((item) => item.id === seg.id);
          if (existingIndex >= 0) {
            updated[existingIndex] = {
              ...updated[existingIndex],
              text,
              isFinal: seg.final,
            };
          } else {
            updated.push({
              id: seg.id,
              sender,
              text,
              timestamp: formatCurrentTime(),
              isFinal: seg.final,
            });
          }
        }
        return updated;
      });
    };

    room.on(RoomEvent.TranscriptionReceived, handleTranscription);

    return () => {
      room.off(RoomEvent.TranscriptionReceived, handleTranscription);
    };
  }, [room]);

  // One-click recipient selection: notify agent via data channel and add transcript notice
  const handleSelectRecipient = useCallback(
    (recipient: EmailRecipient) => {
      // Mark as resolved so picker never reopens for this interaction
      if (activeMatchKeyRef.current) {
        resolvedMatchKeysRef.current.add(activeMatchKeyRef.current);
        activeMatchKeyRef.current = null;
      }
      setShowRecipientPicker(false);

      if (localParticipant) {
        try {
          const payload = new TextEncoder().encode(
            JSON.stringify({
              type: 'select_recipient',
              email: recipient.email,
              name: recipient.name || '',
            })
          );
          localParticipant.publishData(payload, { reliable: true });
        } catch (e) {
          console.debug('Recipient selection publish error:', e);
        }
      }

      const label = recipient.name ? `${recipient.name} <${recipient.email}>` : recipient.email;
      setTranscripts((prev) => [
        ...prev,
        {
          id: `recipient-pick-${Date.now()}`,
          sender: 'user',
          text: `Use ${label}`,
          timestamp: formatCurrentTime(),
          isFinal: true,
        },
      ]);
    },
    [localParticipant]
  );

  const handleClosePicker = useCallback(() => {
    if (activeMatchKeyRef.current) {
      resolvedMatchKeysRef.current.add(activeMatchKeyRef.current);
      activeMatchKeyRef.current = null;
    }
    setShowRecipientPicker(false);
  }, []);

  // Toggle microphone mute state
  const handleToggleMute = useCallback(async () => {
    if (localParticipant) {
      await localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled);
    }
  }, [localParticipant, isMicrophoneEnabled]);

  // Determine user-friendly status badge and label
  const isAgentSpeaking = agentState === 'speaking';
  const isAgentThinking = agentState === 'thinking';
  const isAgentListening = agentState === 'listening';

  let statusLabel = 'Vaani can listen';
  let statusClass = 'listening';

  if (!isMicrophoneEnabled) {
    statusLabel = 'Microphone Muted';
    statusClass = 'muted';
  } else if (agentState === 'connecting' || agentState === 'initializing' || !agentState) {
    statusLabel = 'Vaani is connecting...';
    statusClass = 'connecting';
  } else if (isAgentSpeaking) {
    statusLabel = 'Vaani is speaking...';
    statusClass = 'speaking';
  } else if (isAgentThinking) {
    statusLabel = 'Vaani is thinking...';
    statusClass = 'thinking';
  } else if (isAgentListening) {
    statusLabel = 'Vaani can listen';
    statusClass = 'listening';
  } else {
    statusLabel = 'Vaani can listen';
    statusClass = 'listening';
  }

  return (
    <div className="vaani-active-screen">
      {/* Header with Vaani Logo and Live Status */}
      <header className="vaani-header">
        <div className="vaani-brand">
          <div className="vaani-logo-badge" aria-hidden="true">
            <span className="vaani-logo-letter">V</span>
          </div>
          <div className="vaani-brand-meta">
            <h1 className="vaani-title">Vaani</h1>
            <span className="vaani-subtitle">Voice Assistant</span>
          </div>
        </div>

        <div
          className={`status-pill ${statusClass}`}
          role="status"
          aria-live="polite"
        >
          <span className="status-indicator-dot" />
          <span className="status-label-text">{statusLabel}</span>
        </div>
      </header>

      {/* Main Conversation Transcript */}
      <main
        ref={transcriptContainerRef}
        className="vaani-transcript-container"
        aria-label="Conversation Transcript"
      >
        <div className="transcript-messages">
          {transcripts.map((item) => (
            <div
              key={item.id}
              className={`transcript-row ${item.sender === 'user' ? 'row-user' : 'row-vaani'}`}
            >
              <div className="transcript-bubble">
                <div className="bubble-sender-header">
                  <span className="sender-name">
                    {item.sender === 'user' ? 'You' : 'Vaani'}
                  </span>
                  <span className="message-time">{item.timestamp}</span>
                </div>
                <p className="bubble-text">{item.text}</p>
              </div>
            </div>
          ))}
          <div ref={transcriptEndRef} />
        </div>
      </main>

      {/* Recipient Picker Overlay: shown ONLY when multiple matching recipients exist */}
      {showRecipientPicker && (
        <RecentRecipientPicker
          recipients={multipleMatchingRecipients}
          queryName={multipleMatchingQuery}
          onSelect={handleSelectRecipient}
          onClose={handleClosePicker}
        />
      )}

      {/* Voice Visualizer */}
      <section className="vaani-interaction-zone" aria-label="Voice Interaction">
        <div className="visualizer-container" aria-hidden="true">
          <BarVisualizer
            state={agentState}
            barCount={15}
            trackRef={audioTrack}
            className="agent-sound-bars"
          />
        </div>
      </section>

      {/* Control Bar: Mute Toggle and End Call */}
      <footer className="vaani-control-bar" aria-label="Call Controls">
        <button
          type="button"
          className={`control-btn mute-btn ${!isMicrophoneEnabled ? 'active-muted' : ''}`}
          onClick={handleToggleMute}
          aria-label={isMicrophoneEnabled ? 'Mute microphone' : 'Unmute microphone'}
        >
          <span className="btn-icon" aria-hidden="true">
            {isMicrophoneEnabled ? (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" y1="19" x2="12" y2="22" />
                <line x1="8" y1="22" x2="16" y2="22" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="2" y1="2" x2="22" y2="22" />
                <path d="M18.89 13.23A7.12 7.12 0 0 0 19 12v-2" />
                <path d="M5 10v2a7 7 0 0 0 12 5" />
                <line x1="12" y1="19" x2="12" y2="22" />
              </svg>
            )}
          </span>
          <span className="btn-label">{isMicrophoneEnabled ? 'Mute' : 'Unmute'}</span>
        </button>

        <button
          type="button"
          className="control-btn end-call-btn"
          onClick={onEndCall}
          aria-label="End call with Vaani"
        >
          <span className="btn-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <path d="M10.68 13.31a16 16 0 0 0 3.41 2.6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7 2 2 0 0 1 1.72 2v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.42 19.42 0 0 1-3.33-2.67m-2.67-3.34a19.79 19.79 0 0 1-3.07-8.63A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91" />
              <line x1="22" y1="2" x2="2" y2="22" />
            </svg>
          </span>
          <span className="btn-label">End Call</span>
        </button>
      </footer>
    </div>
  );
}

/**
 * Main App Component
 * Handles the behind-the-scenes LiveKit token acquisition and displays the Vaani UI.
 * Completely hides LiveKit URLs, room names, and credentials from the user.
 */
export default function App() {
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [serverUrl, setServerUrl] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isVoiceModalOpen, setIsVoiceModalOpen] = useState(false);
  const [selectedVoice, setSelectedVoice] = useState<'female' | 'male'>('female');

  // Hidden background connection to LiveKit with chosen voice
  const startConversation = async (voice: 'female' | 'male' = selectedVoice) => {
    setLoading(true);
    setErrorMessage(null);

    try {
      // Auto-request token from local middleware with selected voice
      const res = await fetch(`/api/token?room=my-agent-room&voice=${voice}`);
      const data = await res.json();

      if (!res.ok || !data.token) {
        throw new Error(data.error || 'Failed to start voice assistant');
      }

      setToken(data.token);
      setServerUrl(data.url || 'wss://vaani-pvpbffol.livekit.cloud');
      setIsVoiceModalOpen(false);
      setConnected(true);
    } catch (err: any) {
      setErrorMessage(
        err?.message || 'Unable to connect to Vaani. Please ensure the voice service is running.'
      );
      setConnected(false);
    } finally {
      setLoading(false);
    }
  };

  const handleEndCall = () => {
    setConnected(false);
    setToken(null);
  };

  return (
    <div className="vaani-app-root">
      {!connected ? (
        // Welcome / Start Screen (Clean, accessible, high-contrast)
        <div className="vaani-welcome-screen">
          <div className="welcome-card">
            <div className="brand-emblem" aria-hidden="true">
              <span className="emblem-text">V</span>
            </div>

            <h1 className="welcome-heading">Vaani</h1>
            <p className="welcome-subheading">Your Multilingual AI Voice Assistant</p>

            <div className="welcome-message-box">
              <p>
                Speak. Ask. Get Things Done.
              </p>
            </div>

            {errorMessage && (
              <div className="connection-error-box" role="alert">
                <span className="error-icon" aria-hidden="true">⚠️</span>
                <span>{errorMessage}</span>
              </div>
            )}

            <button
              type="button"
              className="start-talking-btn"
              onClick={() => setIsVoiceModalOpen(true)}
              disabled={loading}
              aria-label="Start conversation with Vaani"
            >
              {loading ? (
                <>
                  <span className="btn-spinner" aria-hidden="true" />
                  <span>Connecting to Vaani...</span>
                </>
              ) : (
                <>
                  <span className="btn-mic-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                      <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                      <line x1="12" y1="19" x2="12" y2="22" />
                      <line x1="8" y1="22" x2="16" y2="22" />
                    </svg>
                  </span>
                  <span>Start Conversation</span>
                </>
              )}
            </button>

            <p className="privacy-note">
              Microphone access is used solely for live voice conversation.
            </p>
          </div>

          {/* Voice Selection Modal (Matching reference design) */}
          {isVoiceModalOpen && (
            <div
              className="voice-modal-backdrop"
              onClick={() => setIsVoiceModalOpen(false)}
            >
              <div
                className="voice-modal-card"
                role="dialog"
                aria-modal="true"
                aria-labelledby="voice-modal-title"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="voice-modal-header">
                  <div className="voice-modal-title-row">
                    <SoundwaveIcon />
                    <h2 id="voice-modal-title" className="voice-modal-title">
                      Choose Vaani's Voice
                    </h2>
                  </div>
                  <button
                    type="button"
                    className="voice-modal-close-btn"
                    onClick={() => setIsVoiceModalOpen(false)}
                    aria-label="Close voice selection modal"
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                      <line x1="18" y1="6" x2="6" y2="18" />
                      <line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                </div>

                <p className="voice-modal-subtitle">Select a voice for your conversation</p>

                <div className="voice-options-grid" role="radiogroup" aria-label="Vaani voice selection">
                  {/* Female Voice Option */}
                  <div
                    className={`voice-option-card ${selectedVoice === 'female' ? 'selected' : ''}`}
                    role="radio"
                    aria-checked={selectedVoice === 'female'}
                    tabIndex={0}
                    onClick={() => setSelectedVoice('female')}
                    onKeyDown={(e) => {
                      if (e.key === ' ' || e.key === 'Enter') setSelectedVoice('female');
                    }}
                  >
                    <div className="voice-radio" aria-hidden="true">
                      {selectedVoice === 'female' && <span className="voice-radio-dot" />}
                    </div>
                    <div className="voice-avatar-wrapper">
                      <img src={femaleVoiceImg} alt="Female voice avatar" className="voice-avatar-img" />
                    </div>
                    <span className="voice-name">Female Voice</span>
                    <span className="voice-desc">Warm, friendly and natural</span>
                  </div>

                  {/* Male Voice Option */}
                  <div
                    className={`voice-option-card ${selectedVoice === 'male' ? 'selected' : ''}`}
                    role="radio"
                    aria-checked={selectedVoice === 'male'}
                    tabIndex={0}
                    onClick={() => setSelectedVoice('male')}
                    onKeyDown={(e) => {
                      if (e.key === ' ' || e.key === 'Enter') setSelectedVoice('male');
                    }}
                  >
                    <div className="voice-radio" aria-hidden="true">
                      {selectedVoice === 'male' && <span className="voice-radio-dot" />}
                    </div>
                    <div className="voice-avatar-wrapper">
                      <img src={maleVoiceImg} alt="Male voice avatar" className="voice-avatar-img" />
                    </div>
                    <span className="voice-name">Male Voice</span>
                    <span className="voice-desc">Clear, calm and natural</span>
                  </div>
                </div>

                <button
                  type="button"
                  className="voice-continue-btn"
                  onClick={() => startConversation(selectedVoice)}
                  disabled={loading}
                >
                  {loading ? (
                    <>
                      <span className="btn-spinner" aria-hidden="true" />
                      <span>Connecting...</span>
                    </>
                  ) : (
                    <>
                      <span>Continue</span>
                      <span aria-hidden="true">→</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          )}
        </div>
      ) : (
        // Active Voice Assistant Session
        token &&
        serverUrl && (
          <LiveKitRoom
            serverUrl={serverUrl}
            token={token}
            connect={connected}
            audio={true}
            video={false}
            onDisconnected={handleEndCall}
            onError={(err) => setErrorMessage(err.message)}
            className="vaani-room-shell"
          >
            {/* Handles incoming voice agent audio playback */}
            <RoomAudioRenderer />

            {/* Vaani voice assistant interface */}
            <VaaniScreen onEndCall={handleEndCall} selectedVoice={selectedVoice} />
          </LiveKitRoom>
        )
      )}
    </div>
  );
}

