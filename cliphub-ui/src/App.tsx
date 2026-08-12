import { getCurrentWindow } from '@tauri-apps/api/window';
import { useState, useEffect, useRef, useCallback } from 'react';
import './index.css';

const API = 'http://127.0.0.1:7842';

// ── Types ─────────────────────────────────────────────────────────────────
interface Clip {
  filename: string; url: string; title: string;
  size_mb: number; hook_score: string | number;
  viral_rating: number | null; social_caption: string;
  reason: string; clip_number: number | null;
}
interface HistoryEntry {
  job_id: string; filename: string; created: number; clip_count?: number;
}
type Page = 'upload' | 'clips' | 'history' | 'settings';

const STAGES = ['Transcribe', 'Detect', 'Slice', 'Captions', 'Music', 'Final'];

// ── Helpers ───────────────────────────────────────────────────────────────
function timeAgo(ts: number) {
  const s = (Date.now() / 1000) - ts;
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

// ── Sub-components ────────────────────────────────────────────────────────

function Titlebar({ status, onMinimize, onClose }: { status: string; onMinimize: () => void; onClose: () => void }) {
  return (
    <div className="titlebar" data-tauri-drag-region>
      <div className="titlebar-brand" data-tauri-drag-region>
        <div className="titlebar-dot pulse-dot" />
        OBSCURA
      </div>
      <div className="titlebar-status">{status}</div>
      <div className="titlebar-controls">
        <button className="titlebar-btn" onClick={onMinimize} title="Minimise">&#x2212;</button>
        <button className="titlebar-btn close" onClick={onClose} title="Close">&#x2715;</button>
      </div>
    </div>
  );
}

function Sidebar({ page, setPage, clipCount }: { page: Page; setPage: (p: Page) => void; clipCount: number }) {
  const items: { id: Page; icon: string; title: string }[] = [
    { id: 'upload',  icon: '⬆',  title: 'Upload' },
    { id: 'clips',   icon: '✂',  title: `Clips${clipCount > 0 ? ` (${clipCount})` : ''}` },
    { id: 'history', icon: '◷',  title: 'History' },
  ];
  return (
    <div className="sidebar">
      <div className="sidebar-nav">
        {items.map(i => (
          <button key={i.id} className={`nav-btn ${page === i.id ? 'active' : ''}`} onClick={() => setPage(i.id)} title={i.title}>
            {i.icon}
          </button>
        ))}
      </div>
      <div className="sidebar-bottom">
        <button className={`nav-btn ${page === 'settings' ? 'active' : ''}`} onClick={() => setPage('settings')} title="Settings">⚙</button>
      </div>
    </div>
  );
}

// ── Config Defaults ───────────────────────────────────────────────────────
const DEFAULT_CONFIG = {
  model: 'small', max_clips: 8, music: 'none',
  caption_style: 'kinetic_slide', font_preset: 'default',
  font_size: 48, primary_color: '#FFFFFF', outline_color: '#000000',
  broll: false, no_title: false, language: '',
};

// ── Upload Page ───────────────────────────────────────────────────────────
function UploadPage({ onJobStart }: { onJobStart: (jobId: string, filename: string) => void }) {
  const [url, setUrl] = useState('');
  const [fetching, setFetching] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [config, setConfig] = useState({ ...DEFAULT_CONFIG });
  const [pendingJob, setPendingJob] = useState<{ jobId: string; filename: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const cfg = (k: string, v: unknown) => setConfig(p => ({ ...p, [k]: v }));

  const uploadFile = async (file: File) => {
    const fd = new FormData(); fd.append('file', file);
    const r = await fetch(`${API}/upload`, { method: 'POST', body: fd });
    const d = await r.json();
    setPendingJob({ jobId: d.job_id, filename: file.name });
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) uploadFile(f);
  };

  const fetchUrl = async () => {
    if (!url.trim()) return;
    setFetching(true);
    try {
      const r = await fetch(`${API}/prepare-download`, { method: 'POST' });
      const d = await r.json();
      const jobId = d.job_id;
      // Start download via WebSocket
      const ws = new WebSocket(`ws://127.0.0.1:7842/download/${jobId}`);
      ws.onopen = () => ws.send(JSON.stringify({ url: url.trim() }));
      ws.onmessage = (e) => {
        const ev = JSON.parse(e.data);
        if (ev.type === 'done' && ev.filename) {
          setPendingJob({ jobId, filename: ev.filename });
          ws.close();
        }
      };
    } catch {
      // fallback: treat url as already-downloaded file
    } finally {
      setFetching(false);
    }
  };

  const handleStart = async () => {
    if (!pendingJob) return;
    await fetch(`${API}/config/${pendingJob.jobId}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...config, force_restart: false }),
    });
    onJobStart(pendingJob.jobId, pendingJob.filename);
    setPendingJob(null); setUrl('');
  };

  return (
    <div className="page active" id="page-upload">
      <div className="upload-header">
        <h1>Upload Center</h1>
        <p>Drop a video or paste a YouTube link — Obscura does the rest.</p>
      </div>

      {/* Drop zone */}
      <div
        className={`dropzone ${dragOver ? 'drag-over' : ''} ${pendingJob ? 'drag-over' : ''}`}
        onClick={() => !pendingJob && fileRef.current?.click()}
        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        <input ref={fileRef} type="file" accept="video/*" onChange={e => { if (e.target.files?.[0]) uploadFile(e.target.files[0]); }} />
        <span className="dropzone-icon">
          {pendingJob ? '✓' : '↑'}
        </span>
        {pendingJob
          ? <><h2 style={{ color: '#4caf50' }}>Ready: {pendingJob.filename}</h2><p>Configure below and press Start</p></>
          : <><h2>Drop video file here</h2><p>or click to browse — MP4, MOV, MKV, WebM supported</p></>
        }
      </div>

      {/* URL row */}
      <div className="url-row">
        <input
          className="input-dark"
          placeholder="Paste YouTube, TikTok, or any video URL…"
          value={url} onChange={e => setUrl(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && fetchUrl()}
          style={{ userSelect: 'text' }}
        />
        <button className="btn btn-ghost" onClick={fetchUrl} disabled={fetching || !url.trim()}>
          {fetching ? <span className="spinner" /> : 'Fetch'}
        </button>
      </div>

      {/* Config */}
      <div className="config-section">
        <div className="config-section-title">Processing Options</div>
        <div className="config-grid">
          <div className="config-field">
            <label className="config-label">Whisper Model</label>
            <select className="select-dark" value={config.model} onChange={e => cfg('model', e.target.value)}>
              <option value="tiny">Tiny (fastest)</option>
              <option value="base">Base</option>
              <option value="small">Small (recommended)</option>
              <option value="medium">Medium</option>
              <option value="large">Large (best quality)</option>
            </select>
          </div>
          <div className="config-field">
            <label className="config-label">Max Clips</label>
            <select className="select-dark" value={config.max_clips} onChange={e => cfg('max_clips', Number(e.target.value))}>
              {[3,5,8,10,15,20].map(n => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <div className="config-field">
            <label className="config-label">Background Music</label>
            <select className="select-dark" value={config.music} onChange={e => cfg('music', e.target.value)}>
              <option value="none">None</option>
              <option value="chill">Chill</option>
              <option value="hype">Hype</option>
              <option value="ambient">Ambient</option>
            </select>
          </div>
          <div className="config-field">
            <label className="config-label">Caption Style</label>
            <select className="select-dark" value={config.caption_style} onChange={e => cfg('caption_style', e.target.value)}>
              <option value="kinetic_slide">Kinetic Slide</option>
              <option value="word_pop">Word Pop</option>
              <option value="karaoke">Karaoke</option>
              <option value="subtitle">Subtitle</option>
              <option value="none">None</option>
            </select>
          </div>
        </div>
        <div style={{ marginTop: 16 }}>
          <div className="toggle-row">
            <span className="toggle-label">Remove title card</span>
            <button className={`toggle ${config.no_title ? 'on' : ''}`} onClick={() => cfg('no_title', !config.no_title)} />
          </div>
          <div className="toggle-row">
            <span className="toggle-label">B-roll overlay</span>
            <button className={`toggle ${config.broll ? 'on' : ''}`} onClick={() => cfg('broll', !config.broll)} />
          </div>
        </div>
      </div>

      <div className="start-btn-row">
        {pendingJob && (
          <button className="btn btn-ghost btn-icon" onClick={() => setPendingJob(null)} title="Clear">✕</button>
        )}
        <button className="btn btn-white" onClick={handleStart} disabled={!pendingJob}>
          {pendingJob ? '▶ Start Processing' : 'No file selected'}
        </button>
      </div>
    </div>
  );
}

// ── Job Progress Page ─────────────────────────────────────────────────────
function JobPage({ jobId, filename, onDone, onBack }: {
  jobId: string; filename: string;
  onDone: (clips: Clip[]) => void; onBack: () => void;
}) {
  const [logs, setLogs] = useState<{ text: string; kind: string }[]>([]);
  const [stage, setStage] = useState(0);
  const [status, setStatus] = useState<'running' | 'done' | 'error'>('running');
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ws = new WebSocket(`ws://127.0.0.1:7842/ws/${jobId}`);
    ws.onmessage = (e) => {
      const ev = JSON.parse(e.data);
      if (ev.type === 'stage') setStage(ev.stage);
      if (ev.type === 'done') { setStatus('done'); if (ev.clips?.length) onDone(ev.clips); }
      if (ev.type === 'error') setStatus('error');
      if (ev.raw) setLogs(p => [...p, { text: ev.raw, kind: ev.type }]);
    };
    ws.onclose = () => { if (status === 'running') setStatus('done'); };
    return () => ws.close();
  }, [jobId]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs]);

  const cancel = () => fetch(`${API}/api/cancel/${jobId}`, { method: 'POST' });

  return (
    <div className="page active" id="page-job">
      <div className="clips-header">
        <button className="btn btn-ghost" onClick={onBack}>← Back</button>
        {status === 'running' && (
          <button className="btn btn-danger" onClick={cancel}>Cancel</button>
        )}
      </div>
      <div className="job-view" style={{ marginBottom: 24 }}>
        <div className="job-header">
          <span className="job-title">{filename}</span>
          <span className={`job-status-badge badge-${status}`}>
            {status === 'running' && <span className="spinner" />}
            {status === 'running' ? 'Processing' : status === 'done' ? '✓ Done' : '✕ Error'}
          </span>
        </div>
        <div className="stage-tracker">
          {STAGES.map((s, i) => (
            <div key={s} className={`stage-step ${i < stage ? 'done' : i === stage ? 'active' : ''}`}>
              <div className="stage-dot">{i < stage ? '✓' : i + 1}</div>
              <div className="stage-label">{s}</div>
            </div>
          ))}
        </div>
        <div className="log-console" ref={logRef}>
          {logs.map((l, i) => (
            <div key={i} className={`log-line ${l.kind === 'warning' ? 'warn' : l.kind === 'error' ? 'error-line' : ''}`}>
              {l.text}
            </div>
          ))}
          {status === 'running' && <div className="log-line" style={{ color: 'var(--text-tertiary)' }}>▋</div>}
        </div>
      </div>
      {status === 'done' && (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>✓</div>
          <p style={{ color: 'var(--text-secondary)' }}>Processing complete. Switch to Clips to review your results.</p>
        </div>
      )}
    </div>
  );
}

// ── Publish Modal ─────────────────────────────────────────────────────────
function PublishModal({ clip, jobId, onClose }: { clip: Clip; jobId: string; onClose: () => void }) {
  const [platforms, setPlatforms] = useState<string[]>(['instagram']);
  const [caption, setCaption] = useState(clip.social_caption || '');
  const [publishing, setPublishing] = useState(false);
  const [result, setResult] = useState('');

  const toggleP = (p: string) => setPlatforms(prev => prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p]);

  const publish = async () => {
    setPublishing(true);
    try {
      const r = await fetch(`${API}/social/post`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: jobId, clip_filename: clip.filename, title: clip.title, caption, platforms }),
      });
      const d = await r.json();
      setResult(d.upload_id ? 'Queued for publish!' : d.error || 'Error');
    } finally {
      setPublishing(false);
    }
  };

  return (
    <div className="modal-overlay open" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modal-header">
          <h2>Publish Clip</h2>
          <button className="btn btn-ghost btn-icon" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">
          <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 12 }}>{clip.title}</p>
          <div className="config-label" style={{ marginBottom: 6 }}>Caption</div>
          <textarea className="textarea-dark" value={caption} onChange={e => setCaption(e.target.value)} rows={4} style={{ userSelect: 'text' }} />
          <div className="config-label" style={{ marginTop: 14, marginBottom: 6 }}>Platforms</div>
          <div className="platform-row">
            {['instagram', 'youtube', 'tiktok'].map(p => (
              <button key={p} className={`platform-chip ${platforms.includes(p) ? 'selected' : ''}`} onClick={() => toggleP(p)}>
                {p.charAt(0).toUpperCase() + p.slice(1)}
              </button>
            ))}
          </div>
          {result && <p style={{ marginTop: 12, fontSize: 12, color: result.includes('Error') ? 'var(--red)' : '#4caf50' }}>{result}</p>}
        </div>
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-white" onClick={publish} disabled={publishing || platforms.length === 0}>
            {publishing ? <span className="spinner" /> : 'Publish'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Clips Page ────────────────────────────────────────────────────────────
function ClipsPage({ clips, jobId }: { clips: Clip[]; jobId: string }) {
  const [publishClip, setPublishClip] = useState<Clip | null>(null);

  if (clips.length === 0) return (
    <div className="page active" id="page-clips">
      <div className="empty-state">
        <div className="empty-state-icon">✂</div>
        <h3>No clips yet</h3>
        <p>Upload a video to generate clips</p>
      </div>
    </div>
  );

  return (
    <div className="page active" id="page-clips">
      <div className="clips-header">
        <h2>{clips.length} clips generated</h2>
        <button className="btn btn-ghost" onClick={() => { const a = document.createElement('a'); a.href = `${API}/clips`; a.target = '_blank'; a.click(); }}>
          View all
        </button>
      </div>
      <div className="clips-grid">
        {clips.map((clip) => (
          <div className="clip-card" key={clip.filename}>
            <div className="clip-thumb">
              <video
                src={`${API}${clip.url}`}
                muted
                onMouseEnter={e => (e.currentTarget as HTMLVideoElement).play()}
                onMouseLeave={e => { (e.currentTarget as HTMLVideoElement).pause(); (e.currentTarget as HTMLVideoElement).currentTime = 0; }}
              />
              <div className="clip-overlay">
                <div className="clip-play-btn">▶</div>
              </div>
            </div>
            <div className="clip-info">
              <div className="clip-title">{clip.title}</div>
              <div className="clip-meta">
                <span className="clip-meta-tag">{clip.size_mb}MB</span>
                {clip.clip_number && <span className="clip-meta-tag">#{clip.clip_number}</span>}
                {clip.hook_score && <span className="clip-score">⚡ {clip.hook_score}</span>}
              </div>
            </div>
            <div className="clip-actions">
              <a
                className="btn btn-ghost"
                href={`${API}${clip.url}`}
                download={clip.filename}
                style={{ flex: 1, textDecoration: 'none', justifyContent: 'center', fontSize: 12 }}
              >
                ↓ Download
              </a>
              <button className="btn btn-ghost" onClick={() => setPublishClip(clip)} style={{ flex: 1, fontSize: 12 }}>
                ↑ Publish
              </button>
            </div>
          </div>
        ))}
      </div>
      {publishClip && <PublishModal clip={publishClip} jobId={jobId} onClose={() => setPublishClip(null)} />}
    </div>
  );
}

// ── History Page ──────────────────────────────────────────────────────────
function HistoryPage({ onLoad }: { onLoad: (jobId: string, filename: string, clips: Clip[]) => void }) {
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/history`);
      const d = await r.json();
      setHistory(d.history || []);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const loadJob = async (entry: HistoryEntry) => {
    const r = await fetch(`${API}/clips/${entry.job_id}`);
    const d = await r.json();
    onLoad(entry.job_id, entry.filename, d.clips || []);
  };

  if (loading) return (
    <div className="page active" id="page-history">
      <div className="empty-state"><div className="spinner" style={{ width: 24, height: 24 }} /></div>
    </div>
  );

  if (history.length === 0) return (
    <div className="page active" id="page-history">
      <div className="empty-state">
        <div className="empty-state-icon">◷</div>
        <h3>No history yet</h3>
        <p>Processed jobs will appear here</p>
      </div>
    </div>
  );

  return (
    <div className="page active" id="page-history">
      <div className="clips-header">
        <h2>History</h2>
        <button className="btn btn-ghost" onClick={refresh}>↻ Refresh</button>
      </div>
      <div className="history-list">
        {history.map(h => (
          <div className="history-card" key={h.job_id} onClick={() => loadJob(h)}>
            <div className="history-icon">🎬</div>
            <div className="history-info">
              <div className="history-name">{h.filename}</div>
              <div className="history-sub">{timeAgo(h.created)}</div>
            </div>
            {h.clip_count && <span className="history-badge">{h.clip_count} clips</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Settings Page ─────────────────────────────────────────────────────────
function SettingsPage() {
  const [backendUrl, setBackendUrl] = useState('http://127.0.0.1:7842');
  const [ping, setPing] = useState<'idle' | 'ok' | 'fail'>('idle');

  const testConn = async () => {
    try {
      await fetch(`${backendUrl}/clips`);
      setPing('ok');
    } catch { setPing('fail'); }
  };

  return (
    <div className="page active" id="page-settings">
      <div className="upload-header">
        <h1>Settings</h1>
        <p>Configure Obscura Clips</p>
      </div>
      <div className="config-section">
        <div className="config-section-title">Backend</div>
        <div style={{ display: 'flex', gap: 10 }}>
          <input
            className="input-dark"
            value={backendUrl}
            onChange={e => setBackendUrl(e.target.value)}
            style={{ userSelect: 'text' }}
          />
          <button className="btn btn-ghost" onClick={testConn}>Test</button>
        </div>
        {ping === 'ok' && <p style={{ color: '#4caf50', fontSize: 12, marginTop: 8 }}>✓ Connected</p>}
        {ping === 'fail' && <p style={{ color: 'var(--red)', fontSize: 12, marginTop: 8 }}>✕ Could not reach backend</p>}
      </div>
      <div className="config-section">
        <div className="config-section-title">About</div>
        <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          Obscura Clips — AI-powered viral clip generator.<br />
          Tauri + React frontend · FastAPI + Python backend<br />
          Powered by Whisper, FFmpeg, and local LLM inference.
        </p>
      </div>
    </div>
  );
}

// ── Root App ──────────────────────────────────────────────────────────────
export default function App() {
  const [page, setPage] = useState<Page>('upload');
  const [activeJob, setActiveJob] = useState<{ jobId: string; filename: string } | null>(null);
  const [clips, setClips] = useState<Clip[]>([]);
  const [currentJobId, setCurrentJobId] = useState('');
  const [statusText, setStatusText] = useState('Ready');

  const handleMinimize = async () => {
    try { await getCurrentWindow().minimize(); } catch { /* browser fallback */ }
  };
  const handleClose = async () => {
    try { await getCurrentWindow().close(); } catch { window.close(); }
  };

  const handleJobStart = (jobId: string, filename: string) => {
    setActiveJob({ jobId, filename });
    setCurrentJobId(jobId);
    setStatusText('Processing…');
    setPage('clips');
  };

  const handleJobDone = (newClips: Clip[]) => {
    setClips(newClips);
    setActiveJob(null);
    setStatusText(`${newClips.length} clips ready`);
  };

  const handleHistoryLoad = (jobId: string, _filename: string, loadedClips: Clip[]) => {
    setCurrentJobId(jobId);
    setClips(loadedClips);
    setPage('clips');
  };

  return (
    <div className="app">
      <Titlebar status={statusText} onMinimize={handleMinimize} onClose={handleClose} />
      <Sidebar page={page} setPage={setPage} clipCount={clips.length} />
      <div className="content">
        {page === 'upload' && !activeJob && (
          <UploadPage onJobStart={handleJobStart} />
        )}
        {page === 'clips' && activeJob && (
          <JobPage
            jobId={activeJob.jobId}
            filename={activeJob.filename}
            onDone={handleJobDone}
            onBack={() => { setActiveJob(null); setPage('upload'); }}
          />
        )}
        {page === 'clips' && !activeJob && (
          <ClipsPage clips={clips} jobId={currentJobId} />
        )}
        {page === 'history' && (
          <HistoryPage onLoad={handleHistoryLoad} />
        )}
        {page === 'settings' && (
          <SettingsPage />
        )}
      </div>
    </div>
  );
}
