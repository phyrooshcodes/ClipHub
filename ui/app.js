// Toast system
const Toast = {
  container: null,
  init() {
    this.container = document.createElement('div');
    this.container.className = 'toast-container';
    document.body.appendChild(this.container);
  },
  show(message, type = 'info', duration = 4000) {
    if (!this.container) this.init();
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.textContent = message;
    this.container.appendChild(el);
    requestAnimationFrame(() => el.classList.add('toast-visible'));
    setTimeout(() => {
      el.classList.remove('toast-visible');
      setTimeout(() => el.remove(), 300);
    }, duration);
  }
};

// UI State Management & GSAP Animations
document.addEventListener("DOMContentLoaded", () => {
  
  // Initialize Toast
  Toast.init();

  async function refreshSystemBadges() {
    try {
      const data = await fetch('/api/publisher/health').then(r => r.json());
      const badgeNvenc = document.getElementById('badge-nvenc');
      if (badgeNvenc) {
        badgeNvenc.innerHTML = data.nvenc_available ? '<i class="ri-cpu-line"></i> ⚡ NVENC Active' : '<i class="ri-cpu-line"></i> 🖥 CPU Mode';
        if (data.nvenc_available) badgeNvenc.classList.add('glow');
      }
      const badgeModel = document.getElementById('badge-model');
      if (badgeModel) {
        badgeModel.innerHTML = '<i class="ri-brain-line"></i> ' + (data.active_model || 'Local Model');
      }
    } catch (e) {
      console.error("Failed to refresh badges", e);
    }
  }
  refreshSystemBadges();
  // Refresh badges every 30s
  setInterval(refreshSystemBadges, 30000);
  
  // Elements
  const sectionUpload = document.getElementById('section-upload');
  const sectionProcessing = document.getElementById('section-processing');
  const sectionClips = document.getElementById('section-clips');
  const sectionHistory = document.getElementById('section-history');
  
  const btnStartYt = document.getElementById('btn-start-yt');
  const btnCancel = document.getElementById('btn-cancel');
  const btnSettings = document.getElementById('btn-settings');
  const btnHistory = document.getElementById('btn-history');
  const btnBackHome = document.getElementById('btn-back-home');
  const modalSettings = document.getElementById('modal-settings');
  const btnCloseModal = document.querySelector('.close-modal');
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('file-input');
  
  const consoleOutput = document.getElementById('console-output');
  const procBar = document.getElementById('proc-bar');
  const procStageName = document.getElementById('proc-stage-name');
  const procPercent = document.getElementById('proc-percent');

  let currentJobId = null;
  let currentWs = null;
  const sectionUploadCenter = document.getElementById('section-upload-center');
  const uploadStatusBar = document.getElementById('upload-status-bar');
  const seenUploadStates = new Map();
  let uploadCenterTimer = null;
  let pipelineClip = { current: 0, total: 0 };

  const pipelineStageMap = {
    1: { id: 'step-demux',  name: 'Audio Demux',        percent: 20 },
    2: { id: 'step-asr',    name: 'ASR Transcription',  percent: 40 },
    3: { id: 'step-hook',   name: 'Hook Detection',     percent: 58 },
    4: { id: 'step-face',   name: 'Face Tracking',      percent: 68 },
    5: { id: 'step-subs',   name: 'Generating Subtitles', percent: 76 },
    6: { id: 'step-render', name: 'NVENC Rendering',    percent: 84 }
  };

  // GSAP Initial Setup - Ensure visibility gracefully
  gsap.fromTo(".hero-title", { y: 20, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5, ease: "power2.out" });
  gsap.fromTo(".hero-subtitle", { y: 15, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5, delay: 0.1, ease: "power2.out" });
  gsap.fromTo(".dropzone", { scale: 0.98, opacity: 0, y: 10 }, { scale: 1, opacity: 1, y: 0, duration: 0.5, delay: 0.2, ease: "power2.out" });
  gsap.fromTo(".divider", { opacity: 0 }, { opacity: 1, duration: 0.5, delay: 0.3, ease: "power2.out" });
  gsap.fromTo(".url-input-wrapper", { y: 15, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5, delay: 0.4, ease: "power2.out" });

  // Handle Upload Events
  dropzone.addEventListener('click', () => fileInput.click());
  dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('dragover'); });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files.length) startProcessing(e.dataTransfer.files[0], false);
  });
  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length) startProcessing(e.target.files[0], false);
  });
  btnStartYt.addEventListener('click', () => {
    const url = document.getElementById('youtube-url').value;
    if (url) startProcessing(url, true);
  });

  // --- Initialization & Resume Logic ---
  const savedJobId = (() => {
    const jid = localStorage.getItem('currentJobId');
    const ts = Number(localStorage.getItem('currentJobId_ts') || 0);
    if (jid && Date.now() - ts < 24 * 3600 * 1000) return jid;
    localStorage.removeItem('currentJobId');
    localStorage.removeItem('currentJobId_ts');
    return null;
  })();
  const savedYtUrl = localStorage.getItem('ytUrl');
  if (savedJobId) {
    currentJobId = savedJobId;
    sectionUpload.classList.add('hidden');
    sectionProcessing.classList.remove('hidden');
    gsap.to(sectionProcessing, { y: 0, opacity: 1, duration: 0.6, ease: "power3.out" });
    
    if (savedYtUrl) {
      connectYoutubeWS(savedJobId, savedYtUrl);
    } else {
      connectPipelineWS(savedJobId);
    }
  } else {
    // If no active job, load recent uploads for quick selection
    loadRecentUploads();
  }

  async function loadRecentUploads() {
    try {
      const res = await fetch('/uploads');
      const data = await res.json();
      if(data.uploads && data.uploads.length > 0) {
        document.getElementById('recent-uploads-section').style.display = 'block';
        const list = document.getElementById('recent-uploads-list');
        list.innerHTML = '';
        data.uploads.forEach(u => {
          const card = document.createElement('div');
          card.style.cssText = `
            min-width: 150px; background: rgba(255,255,255,0.05); padding: 12px;
            border-radius: var(--radius-sm); border: 1px solid var(--border-color);
            cursor: pointer; transition: all 0.2s ease;
          `;
          card.innerHTML = `
            <i class="ri-video-line" style="font-size: 2rem; color: var(--accent-cyan); margin-bottom: 8px; display: block;"></i>
            <p style="margin:0; font-size: 0.8rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(u.filename)}">${escapeHtml(u.filename)}</p>
            <span style="font-size: 0.7rem; color: var(--text-muted);">${u.size} MB</span>
          `;
          card.onmouseover = () => { card.style.background = 'rgba(255,255,255,0.1)'; card.style.borderColor = 'var(--accent-primary)'; };
          card.onmouseout = () => { card.style.background = 'rgba(255,255,255,0.05)'; card.style.borderColor = 'var(--border-color)'; };
          card.onclick = () => startProcessing(u.filename, false, true);
          list.appendChild(card);
        });
      }
    } catch(e) {}
  }

  // Settings Modal
  const configCaptionStyle = document.getElementById('config-caption-style');
  const homeCaptionStyle = document.getElementById('home-caption-style');
  
  const savedCaptionStyle = localStorage.getItem('captionStyle') || 'kinetic_slide';
  if (configCaptionStyle) configCaptionStyle.value = savedCaptionStyle;
  if (homeCaptionStyle) homeCaptionStyle.value = savedCaptionStyle;
  
  if (configCaptionStyle) {
    configCaptionStyle.addEventListener('change', (e) => {
      localStorage.setItem('captionStyle', e.target.value);
      if (homeCaptionStyle) homeCaptionStyle.value = e.target.value;
    });
  }
  
  if (homeCaptionStyle) {
    homeCaptionStyle.addEventListener('change', (e) => {
      localStorage.setItem('captionStyle', e.target.value);
      if (configCaptionStyle) configCaptionStyle.value = e.target.value;
    });
  }

  const publishingModeStatus = document.getElementById('publishing-mode-status');
  function currentPublishingMode() {
    return localStorage.getItem('publishingMode') || 'manual';
  }
  function renderPublishingMode() {
    const mode = currentPublishingMode();
    document.querySelectorAll('input[name="publishing-mode"]').forEach(input => {
      input.checked = input.value === mode;
    });
    if (publishingModeStatus) {
      publishingModeStatus.textContent = mode === 'auto' ? 'Auto Publish Enabled' : 'Manual Publish Enabled';
    }
  }
  document.querySelectorAll('input[name="publishing-mode"]').forEach(input => {
    input.addEventListener('change', event => {
      localStorage.setItem('publishingMode', event.target.value);
      renderPublishingMode();
    });
  });
  renderPublishingMode();

  const optYtShopping = document.getElementById('opt-yt-shopping');
  if (optYtShopping) {
    const savedYtShopping = localStorage.getItem('ytShoppingEnabled');
    optYtShopping.checked = savedYtShopping !== 'false'; // Default true
    optYtShopping.addEventListener('change', (e) => {
      localStorage.setItem('ytShoppingEnabled', e.target.checked);
    });
  }

  // NVIDIA API Key — check/save wiring (endpoints already existed server-side,
  // this field just wasn't connected to them)
  const nvidiaKeyInput = document.getElementById('nvidia-key');
  const nvidiaKeyStatus = document.getElementById('nvidia-key-status');
  const btnSaveNvidiaKey = document.getElementById('btn-save-nvidia-key');

  async function refreshNvidiaKeyStatus() {
    if (!nvidiaKeyStatus) return;
    try {
      const res = await fetch('/api/check-nvidia-key');
      const data = await res.json();
      if (data.is_set) {
        nvidiaKeyStatus.textContent = `Saved key: ${data.masked_key}`;
        nvidiaKeyStatus.style.color = 'var(--accent-cyan)';
        if (nvidiaKeyInput) nvidiaKeyInput.placeholder = 'Enter a new key to replace it...';
      } else {
        nvidiaKeyStatus.textContent = 'No key saved yet.';
        nvidiaKeyStatus.style.color = 'var(--text-muted)';
      }
    } catch (e) {
      nvidiaKeyStatus.textContent = '';
    }
  }

  if (btnSaveNvidiaKey) {
    btnSaveNvidiaKey.addEventListener('click', async () => {
      const key = (nvidiaKeyInput?.value || '').trim();
      if (!key) {
        nvidiaKeyStatus.textContent = 'Enter a key before saving.';
        nvidiaKeyStatus.style.color = 'var(--accent-secondary)';
        return;
      }
      btnSaveNvidiaKey.disabled = true;
      btnSaveNvidiaKey.textContent = 'Saving...';
      try {
        const res = await fetch('/api/save-nvidia-key', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key })
        });
        const data = await res.json();
        if (data.success) {
          nvidiaKeyInput.value = '';
          nvidiaKeyStatus.style.color = '#4ade80';
          nvidiaKeyStatus.textContent = 'Saved.';
          await refreshNvidiaKeyStatus();
        } else {
          nvidiaKeyStatus.style.color = 'var(--accent-secondary)';
          nvidiaKeyStatus.textContent = 'Failed to save key.';
        }
      } catch (e) {
        nvidiaKeyStatus.style.color = 'var(--accent-secondary)';
        nvidiaKeyStatus.textContent = 'Failed to save key.';
      } finally {
        btnSaveNvidiaKey.disabled = false;
        btnSaveNvidiaKey.textContent = 'Save';
      }
    });
  }

  btnSettings.addEventListener('click', () => {
    document.documentElement.classList.add('modal-open');
    document.body.classList.add('modal-open');
    modalSettings.classList.remove('hidden');
    gsap.fromTo(".modal", { scale: 0.98, opacity: 0, y: 10 }, { scale: 1, opacity: 1, y: 0, duration: 0.2, ease: "power2.out" });
    refreshNvidiaKeyStatus();
  });

  function getSelectedPlatforms() {
    const selected = [];
    if (document.getElementById('chk-platform-instagram')?.checked) selected.push('instagram');
    if (document.getElementById('chk-platform-youtube')?.checked) selected.push('youtube');
    return selected.length ? selected : ['instagram'];
  }

  async function refreshSocialStatus() {
    const igStatus = document.getElementById('ig-status-text');
    const igButton = document.getElementById('btn-connect-ig');
    const ytStatus = document.getElementById('yt-status-text');
    const ytButton = document.getElementById('btn-connect-yt');
    if (!igStatus && !ytStatus) return;
    try {
      const [response, historyResponse] = await Promise.all([
        fetch('/api/social/status'), fetch('/api/social/instagram/history')
      ]);
      const data = await response.json();
      const history = historyResponse.ok ? (await historyResponse.json()).uploads || [] : [];
      const waiting = history.filter(upload => ['queued', 'retrying'].includes(upload.status)).length;
      const uploading = history.filter(upload => upload.status === 'uploading').length;
      const completed = history.filter(upload => upload.status === 'completed').length;
      const lastCompleted = history.find(upload => upload.status === 'completed');

      if (igStatus) {
        if (data.instagram_connected) {
          const queueText = ` · Queue: ${waiting} waiting, ${uploading} uploading, ${completed} completed`;
          const lastText = lastCompleted ? ` · Last: ${lastCompleted.filename}` : '';
          igStatus.textContent = `${data.instagram_username || 'Saved browser session'}${queueText}${lastText}`;
          if (igButton) igButton.textContent = 'Reconnect';
        } else {
          igStatus.textContent = 'Not connected';
          if (igButton) igButton.textContent = 'Connect';
        }
      }

      if (ytStatus) {
        const ytTitle = document.getElementById('yt-channel-title');
        const ytSwitch = document.getElementById('btn-switch-yt');
        const ytDisconnect = document.getElementById('btn-disconnect-yt');
        if (data.youtube_connected) {
          const channel = data.youtube_channel || {};
          const channelName = channel.name || 'Saved Session';
          const handle = channel.handle ? ` (${channel.handle})` : '';
          if (ytTitle) ytTitle.textContent = `YouTube · ${channelName}`;
          ytStatus.textContent = `Active Channel: ${channelName}${handle}`;
          if (ytButton) ytButton.textContent = 'Reconnect';
          if (ytSwitch) ytSwitch.classList.remove('hidden');
          if (ytDisconnect) ytDisconnect.classList.remove('hidden');
        } else {
          if (ytTitle) ytTitle.textContent = 'YouTube Studio';
          ytStatus.textContent = 'Not connected';
          if (ytButton) ytButton.textContent = 'Connect Studio';
          if (ytSwitch) ytSwitch.classList.add('hidden');
          if (ytDisconnect) ytDisconnect.classList.add('hidden');
        }
      }
    } catch (_) {
      if (igStatus) igStatus.textContent = 'Status unavailable';
      if (ytStatus) ytStatus.textContent = 'Status unavailable';
    }
  }

  document.getElementById('btn-connect-ig')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    button.innerHTML = '<i class="ri-loader-4-line spin"></i> Login in browser...';
    try {
      const response = await fetch('/api/social/instagram/connect-playwright', { method: 'POST' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Instagram login failed');
      await refreshSocialStatus();
    } catch (error) {
      if (igStatus) igStatus.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });

  document.getElementById('btn-connect-yt')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    button.innerHTML = '<i class="ri-loader-4-line spin"></i> Login in browser...';
    try {
        const response = await fetch('/api/social/youtube/connect-playwright', { method: 'POST' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'YouTube login failed');
      await refreshSocialStatus();
    } catch (error) {
      const ytStatus = document.getElementById('yt-status-text');
      if (ytStatus) ytStatus.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });

  document.getElementById('btn-disconnect-yt')?.addEventListener('click', async (event) => {
    if (!confirm('Disconnect YouTube? You will need to log in again to publish videos.')) return;
    const button = event.currentTarget;
    button.disabled = true;
    button.innerHTML = '<i class="ri-loader-4-line spin"></i> Disconnecting...';
    try {
      await fetch('/api/social/youtube/disconnect', { method: 'POST' });
      await refreshSocialStatus();
    } catch (error) {
      console.error('Disconnect failed:', error);
    } finally {
      button.disabled = false;
      button.innerHTML = '<i class="ri-logout-box-r-line"></i> Disconnect';
    }
  });

  document.getElementById('btn-switch-yt')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    button.innerHTML = '<i class="ri-loader-4-line spin"></i> Opening Studio...';
    try {
      const response = await fetch('/api/social/youtube/connect-playwright', { method: 'POST' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'YouTube Studio launch failed');
      await refreshSocialStatus();
    } catch (error) {
      const ytStatus = document.getElementById('yt-status-text');
      if (ytStatus) ytStatus.textContent = error.message;
    } finally {
      button.disabled = false;
      button.innerHTML = '<i class="ri-user-switch-line"></i> Switch Channel';
    }
  });

  refreshSocialStatus();
  
  // Ask Title & Hashtags Modal
  const modalAskCaption = document.getElementById('modal-ask-caption');
  const btnAskCaption = document.getElementById('btn-ask-caption');
  const btnAskUpload = document.getElementById('btn-ask-upload');
  const askCaptionFile = document.getElementById('ask-caption-file');
  
  btnAskCaption.addEventListener('click', () => {
    modalAskCaption.classList.remove('hidden');
    gsap.fromTo(modalAskCaption.querySelector('.modal'), { scale: 0.98, opacity: 0, y: 10 }, { scale: 1, opacity: 1, y: 0, duration: 0.2, ease: "power2.out" });
  });
  
  btnAskUpload.addEventListener('click', () => askCaptionFile.click());
  
  askCaptionFile.addEventListener('change', async (e) => {
    if(!e.target.files.length) return;
    const file = e.target.files[0];
    
    document.getElementById('ask-caption-loading').classList.remove('hidden');
    document.getElementById('ask-caption-result').classList.add('hidden');
    btnAskUpload.style.display = 'none';
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const res = await fetch('/api/tools/generate-caption', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      
      document.getElementById('ask-caption-loading').classList.add('hidden');
      document.getElementById('ask-caption-result').classList.remove('hidden');
      btnAskUpload.style.display = 'block';
      
      const copyText = `Title: ${data.title}\n\nCaption:\n${data.caption}`;
      document.getElementById('ask-caption-text').textContent = copyText;
      
      // Save to localStorage history
      let capHist = JSON.parse(localStorage.getItem('captionHistory') || '[]');
      capHist.unshift({
        title: data.title,
        caption: data.caption,
        date: new Date().toLocaleDateString() + ' ' + new Date().toLocaleTimeString()
      });
      localStorage.setItem('captionHistory', JSON.stringify(capHist.slice(0, 50))); // Keep last 50
    } catch(err) {
      console.error(err);
      Toast.show("Failed to generate captions.", "error");
      document.getElementById('ask-caption-loading').classList.add('hidden');
      btnAskUpload.style.display = 'block';
    }
  });
  
  document.getElementById('btn-ask-copy').addEventListener('click', async (e) => {
    const text = document.getElementById('ask-caption-text').textContent;
    try {
      await navigator.clipboard.writeText(text);
      const btn = e.target.closest('button');
      const orig = btn.innerHTML;
      btn.innerHTML = '<i class="ri-check-line"></i> Copied!';
      setTimeout(() => btn.innerHTML = orig, 2000);
    } catch(err) {}
  });

  // Ask Product Suggestion Modal
  const modalAskProduct = document.getElementById('modal-ask-product');
  const btnAskProduct = document.getElementById('btn-ask-product');
  const btnAskProductUpload = document.getElementById('btn-ask-product-upload');
  const askProductFile = document.getElementById('ask-product-file');
  
  btnAskProduct.addEventListener('click', () => {
    modalAskProduct.classList.remove('hidden');
    gsap.fromTo(modalAskProduct.querySelector('.modal'), { scale: 0.98, opacity: 0, y: 10 }, { scale: 1, opacity: 1, y: 0, duration: 0.2, ease: "power2.out" });
  });
  
  btnAskProductUpload.addEventListener('click', () => askProductFile.click());
  
  askProductFile.addEventListener('change', async (e) => {
    if(!e.target.files.length) return;
    const file = e.target.files[0];
    
    document.getElementById('ask-product-loading').classList.remove('hidden');
    document.getElementById('ask-product-result').classList.add('hidden');
    btnAskProductUpload.style.display = 'none';
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const res = await fetch('/api/tools/generate-products', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      
      document.getElementById('ask-product-loading').classList.add('hidden');
      document.getElementById('ask-product-result').classList.remove('hidden');
      btnAskProductUpload.style.display = 'block';
      
      const listContainer = document.getElementById('ask-product-list');
      listContainer.innerHTML = '';
      
      if (data.products && data.products.length > 0) {
        data.products.forEach(prod => {
          const amzSearch = `https://www.amazon.com/s?k=${encodeURIComponent(prod.search_query)}`;
          listContainer.innerHTML += `
            <div style="background: rgba(255,255,255,0.03); padding: 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.08);">
              <div style="font-weight: bold; color: var(--text-main); margin-bottom: 4px;">${prod.product_name}</div>
              <div style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 10px;">${prod.reason}</div>
              <a href="${amzSearch}" target="_blank" class="btn-outline btn-sm" style="display: inline-block; color: #ff9900; border-color: rgba(255,153,0,0.3); text-decoration: none;">
                <i class="ri-amazon-fill"></i> Search on Amazon
              </a>
            </div>
          `;
        });
      } else {
        listContainer.innerHTML = `<div class="text-muted">No specific products found for this clip.</div>`;
      }
      
    } catch(err) {
      console.error(err);
      Toast.show("Failed to generate product suggestions.", "error");
      document.getElementById('ask-product-loading').classList.add('hidden');
      btnAskProductUpload.style.display = 'block';
    }
  });

  document.querySelectorAll('.close-modal').forEach(btn => {
    btn.addEventListener('click', () => {
      document.documentElement.classList.remove('modal-open');
      document.body.classList.remove('modal-open');
      gsap.to(".modal", { 
        scale: 0.9, opacity: 0, duration: 0.2, 
        onComplete: () => {
          modalSettings.classList.add('hidden');
          modalAskCaption.classList.add('hidden');
          modalAskProduct.classList.add('hidden');
        }
      });
    });
  });
  btnCloseModal?.addEventListener('click', () => {
    document.documentElement.classList.remove('modal-open');
    document.body.classList.remove('modal-open');
    gsap.to(".modal-backdrop", { opacity: 0, duration: 0.4 });
    gsap.to(".modal", { scale: 0.98, opacity: 0, y: 10, duration: 0.2, ease: "power2.inOut", onComplete: () => modalSettings.classList.add('hidden') });
  });

  document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) {
        document.documentElement.classList.remove('modal-open');
        document.body.classList.remove('modal-open');
        backdrop.classList.add('hidden');
      }
    });
    backdrop.addEventListener('wheel', (e) => {
      const modalBody = backdrop.querySelector('.modal-body');
      if (modalBody) {
        modalBody.scrollTop += e.deltaY;
      }
    }, { passive: true });
  });

  // History Interactions
  btnHistory.addEventListener('click', () => {
    // Show clip history by default
    document.getElementById('tab-clip-history').classList.replace('btn-outline', 'btn-primary');
    document.getElementById('tab-caption-history').classList.replace('btn-primary', 'btn-outline');
    document.getElementById('history-container').classList.remove('hidden');
    document.getElementById('caption-history-container').classList.add('hidden');
    
    gsap.to([sectionUpload, sectionProcessing, sectionClips], { 
      opacity: 0, y: -30, duration: 0.4, 
      onComplete: () => {
        sectionUpload.classList.add('hidden');
        sectionProcessing.classList.add('hidden');
        sectionClips.classList.add('hidden');
        
        sectionHistory.classList.remove('hidden');
        gsap.fromTo(sectionHistory, { y: 30, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6 });
        renderHistory();
      }
    });
  });

  const tabClip = document.getElementById('tab-clip-history');
  const tabCaption = document.getElementById('tab-caption-history');
  const histContainer = document.getElementById('history-container');
  const capHistContainer = document.getElementById('caption-history-container');

  tabClip.addEventListener('click', () => {
    tabClip.classList.replace('btn-outline', 'btn-primary');
    tabCaption.classList.replace('btn-primary', 'btn-outline');
    histContainer.classList.remove('hidden');
    capHistContainer.classList.add('hidden');
  });

  tabCaption.addEventListener('click', () => {
    tabCaption.classList.replace('btn-outline', 'btn-primary');
    tabClip.classList.replace('btn-primary', 'btn-outline');
    histContainer.classList.add('hidden');
    capHistContainer.classList.remove('hidden');
    renderCaptionHistory();
  });

  function renderCaptionHistory() {
    capHistContainer.innerHTML = '';
    const capHist = JSON.parse(localStorage.getItem('captionHistory') || '[]');
    if(capHist.length === 0) {
      capHistContainer.innerHTML = '<p class="text-muted">No generated captions yet.</p>';
      return;
    }
    
    capHist.forEach(item => {
      const el = document.createElement('div');
      el.className = 'clip-card';
      el.style.flexDirection = 'column';
      el.style.background = 'rgba(0,0,0,0.3)';
      el.style.padding = '20px';
      el.style.border = '1px solid var(--border-color)';
      el.style.borderRadius = 'var(--radius-md)';
      
      const copyText = `Title: ${item.title}\n\nCaption:\n${item.caption}`;
      
      el.innerHTML = `
        <div style="display:flex; justify-content:space-between; margin-bottom:10px;">
          <span class="text-xs text-muted"><i class="ri-time-line"></i> ${item.date}</span>
          <button class="btn-primary btn-sm btn-cap-copy"><i class="ri-clipboard-line"></i> Copy</button>
        </div>
        <h4 style="color:#fff; margin-bottom:10px;">${item.title}</h4>
        <pre style="white-space:pre-wrap; font-family:inherit; font-size:0.9rem; color:#b0b0c0; margin:0;">${item.caption}</pre>
      `;
      
      el.querySelector('.btn-cap-copy').addEventListener('click', async (e) => {
        try {
          await navigator.clipboard.writeText(copyText);
          const btn = e.target.closest('button');
          const orig = btn.innerHTML;
          btn.innerHTML = '<i class="ri-check-line"></i> Copied!';
          setTimeout(() => btn.innerHTML = orig, 2000);
        } catch(err) {}
      });
      
      capHistContainer.appendChild(el);
    });
  }

  btnBackHome.addEventListener('click', () => {
    gsap.to(sectionHistory, { y: 30, opacity: 0, duration: 0.4, ease: "power2.inOut", onComplete: () => {
        sectionHistory.classList.add('hidden');
        sectionUpload.classList.remove('hidden');
        gsap.fromTo(sectionUpload, { y: -30, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6, ease: "power3.out" });
      }
    });
  });

  // ----------------------------------------------------
  // Core API Logic & WebSockets
  // ----------------------------------------------------
  
  function updateProgress(stepId, name, percent) {
    const stepMsgMap = {
      'step-download': 'Fetching from YouTube...',
      'step-demux': 'Extracting streams...',
      'step-asr': 'Transcribing audio locally (Whisper)...',
      'step-hook': 'AI is finding the golden hooks...',
      'step-face': 'Tracking faces (CPU is sweating)...',
      'step-subs': 'Baking in those viral captions...',
      'step-render': 'Finalizing pixels... Grab a coffee ☕'
    };
    
    if (stepId && stepMsgMap[stepId]) {
      const funText = document.getElementById('fun-status-text');
      if(funText) funText.textContent = stepMsgMap[stepId];
    } else if (!stepId) {
      const funText = document.getElementById('fun-status-text');
      if(funText) funText.textContent = 'Initializing pipeline...';
    }

    if (stepId) {
      document.querySelectorAll('.step-card').forEach(c => c.classList.remove('active'));
      const card = document.getElementById(stepId);
      if (card) {
        card.classList.remove('hidden');
        card.classList.add('active');
        // mark previous ones as done based on typical order
        const steps = Array.from(document.querySelectorAll('.step-card:not(.hidden)'));
        const idx = steps.indexOf(card);
        if (idx > 0) {
          for(let i=0; i<idx; i++) {
             const prev = steps[i];
             if (!prev.classList.contains('done')) {
               prev.classList.remove('active');
               prev.classList.add('done');
               prev.querySelector('.step-status').innerHTML = '<i class="ri-check-line"></i>';
             }
          }
        }
      }
    }
    
    procBar.style.width = percent + "%";
    procStageName.textContent = name + "...";
    gsap.to(procPercent, {
      innerHTML: percent + "%", duration: 0.3, snap: { innerHTML: 1 },
      onUpdate: function() { procPercent.innerHTML = Math.round(this.targets()[0].innerHTML.replace('%','')) + "%"; }
    });
  }

  function appendLog(html) {
    const p = document.createElement('p');
    p.innerHTML = html;
    consoleOutput.appendChild(p);
    consoleOutput.scrollTop = consoleOutput.scrollHeight;
  }

  function resetSteps() {
    pipelineClip = { current: 0, total: 0 };
    document.querySelectorAll('.step-card').forEach(c => {
      c.classList.remove('active', 'done');
      c.querySelector('.step-status').innerHTML = '<i class="ri-loader-4-line spin"></i>';
    });
    document.getElementById('step-download').classList.add('hidden');
    consoleOutput.innerHTML = '';
  }

  async function startProcessing(fileOrUrl, isYoutube=false, isExistingUpload=false) {
    document.getElementById('proc-filename').textContent = typeof fileOrUrl === 'string' ? fileOrUrl : fileOrUrl.name;
    if (isYoutube) document.getElementById('proc-filename').textContent = "YouTube Video";
    
    resetSteps();
    
    const tl = gsap.timeline();
    tl.to(sectionUpload, { 
      y: -50, opacity: 0, duration: 0.6, ease: "power3.inOut",
      onComplete: async () => {
        sectionUpload.classList.add('hidden');
        sectionProcessing.classList.remove('hidden');
        gsap.fromTo(sectionProcessing, { y: 50, opacity: 0 }, { y: 0, opacity: 1, duration: 0.8, ease: "power3.out" });
        
        try {
          // Send config (model, caption_style, etc) FIRST before initiating connections
          async function sendConfig(jobId) {
            const model = document.getElementById('config-model')?.value || 'small';
            const captionStyle = document.getElementById('config-caption-style')?.value || 'kinetic_slide';
            try {
              await fetch(`/config/${jobId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                   model: model,
                   caption_style: captionStyle,
                   auto_publish: currentPublishingMode() === 'auto'
                })
              });
            } catch(e) {}
          }
          
          if (isYoutube) {
             document.getElementById('step-download').classList.remove('hidden');
             updateProgress('step-download', "Initializing YouTube Download", 0);
             const res = await fetch('/prepare-download', { method: 'POST' });
             const data = await res.json();
             if (data.job_id) {
               currentJobId = data.job_id;
               localStorage.setItem('currentJobId', data.job_id);
               localStorage.setItem('ytUrl', fileOrUrl);
               await sendConfig(data.job_id);
               connectYoutubeWS(data.job_id, fileOrUrl);
             }
          } else if (isExistingUpload) {
             updateProgress(null, "Initializing existing file", 10);
             const res = await fetch(`/api/start-from-upload/${encodeURIComponent(fileOrUrl)}`, { method: 'POST' });
             const data = await res.json();
             if (data.job_id) {
               currentJobId = data.job_id;
               localStorage.setItem('currentJobId', data.job_id);
               localStorage.setItem('currentJobId_ts', Date.now());
               await sendConfig(data.job_id);
               connectPipelineWS(data.job_id);
             } else {
               updateProgress(null, "Error: " + (data.error || "File not found"), 0);
               appendLog(`<span class="log-error">[Error]</span> Failed to initialize existing file. It may have been cleaned up or does not exist.`);
               setTimeout(() => btnCancel.click(), 2500);
             }
          } else {
             updateProgress(null, "Uploading file", 5);
             const fd = new FormData();
             fd.append('file', fileOrUrl);
             const res = await fetch('/upload', { method: 'POST', body: fd });
             const data = await res.json();
             if (data.job_id) {
               currentJobId = data.job_id;
               localStorage.setItem('currentJobId', data.job_id);
               localStorage.setItem('currentJobId_ts', Date.now());
               await sendConfig(data.job_id);
               connectPipelineWS(data.job_id);
             }
          }
        } catch(e) {
          console.error(e);
          updateProgress(null, "Failed to upload!", 0);
        }
      }
    });
  }

  function connectYoutubeWS(jobId, url) {
    if (currentWs) currentWs.close();
    
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${location.host}/ws-ytdl/${jobId}?url=${encodeURIComponent(url)}`;
    
    currentWs = new WebSocket(wsUrl);
    currentWs.onmessage = (event) => {
      let data;
      try { data = JSON.parse(event.data); }
      catch (e) { console.warn('Malformed WS message:', event.data); return; }
      if (data.type === 'ytdl_start') {
         appendLog(`<span class="log-info">[YT-DLP]</span> Downloading ${data.url}`);
      } else if (data.type === 'ytdl_log') {
         appendLog(data.raw);
      } else if (data.type === 'ytdl_progress') {
         // scale YT progress up to 20%
         updateProgress('step-download', "Downloading Video", data.percent * 0.2);
      } else if (data.type === 'ytdl_done') {
         document.getElementById('proc-filename').textContent = data.filename;
         appendLog(`<span class="log-highlight">[YT-DLP]</span> Completed! Connecting to Pipeline...`);
         localStorage.removeItem('ytUrl');
         currentWs.close();
         connectPipelineWS(jobId);
      } else if (data.type === 'error') {
         appendLog(`<span class="log-error">[Error]</span> ${data.message}`);
         updateProgress(null, "Error Occurred", 0);
         localStorage.removeItem('currentJobId');
         localStorage.removeItem('currentJobId_ts');
         localStorage.removeItem('ytUrl');
         setTimeout(() => btnCancel.click(), 2000);
      }
    };
  }

  function connectPipelineWS(jobId) {
    if (currentWs && currentWs.readyState !== WebSocket.CLOSED) currentWs.close();
    
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${location.host}/ws/${jobId}`;
    
    currentWs = new WebSocket(wsUrl);
    currentWs.onmessage = (event) => {
      let data;
      try { data = JSON.parse(event.data); }
      catch (e) { console.warn('Malformed WS message:', event.data); return; }
      
      if (data.type === 'start') {
        updateProgress(null, "Warming up pipeline", 15);
        appendLog(`<span class="log-highlight">[System]</span> Connected to pipeline. Warming up...`);
      } else if (data.type === 'stage' || data.type === 'substage') {
        // The backend parses the pipeline's real log markers into these
        // events.  This is the canonical progress source for uploaded files.
        const stageNumber = data.type === 'stage' ? data.stage : data.substage;
        const stage = pipelineStageMap[stageNumber];
        if (stage) {
          updateProgress(stage.id, stage.name, stage.percent);
        }
        if (data.raw) {
          appendLog(`<span class="log-info" style="color:var(--text-muted)">[Log]</span> ${data.raw}`);
        }
      } else if (data.type === 'clip_start') {
        pipelineClip = { current: data.clip_num, total: data.total };
        if (data.raw) {
          appendLog(`<span class="log-info" style="color:var(--text-muted)">[Log]</span> ${data.raw}`);
        }
      } else if (data.type === 'clip_ready') {
        // Rendering repeats once per generated clip. Advance the last stage
        // so the UI reflects work after the first render begins.
        if (pipelineClip.total > 0) {
          const completed = Math.min(pipelineClip.current, pipelineClip.total);
          const percent = 84 + Math.round((completed / pipelineClip.total) * 15);
          updateProgress('step-render', `Rendered clip ${completed}/${pipelineClip.total}`, percent);
        }
        if (data.raw) {
          appendLog(`<span class="log-info" style="color:var(--text-muted)">[Log]</span> ${data.raw}`);
        }
      } else if (data.type === 'progress') {
        const stageMap = {
          'demux': 'step-demux',
          'transcribe': 'step-asr',
          'hook': 'step-hook',
          'face': 'step-face',
          'subtitle': 'step-subs',
          'render': 'step-render'
        };
        const domId = stageMap[data.step];
        updateProgress(domId, data.step.toUpperCase(), data.percent);
        appendLog(`<span class="log-info">[System]</span> ${data.log}`);
      } else if (data.type === 'error') {
        appendLog(`<span class="log-error">[Error]</span> ${data.message}`);
        if (data.message === 'Job not found.') {
          localStorage.removeItem('currentJobId');
          setTimeout(() => btnCancel.click(), 1500);
        }
      } else if (data.type === 'log') {
        appendLog(`<span class="log-info" style="color:var(--text-muted)">[Log]</span> ${data.raw}`);
      } else if (data.type === 'warning') {
        // Previously silently dropped — this is where GPU-fallback / retry
        // notices show up, which is exactly the info that was missing
        // during long "stuck" stages.
        appendLog(`<span class="log-warning">[Warning]</span> ${data.raw}`);
      } else if (data.type === 'done') {
        updateProgress('step-render', "Finished Processing", 100);
        appendLog(`<span class="log-highlight">[Success]</span> Pipeline completed.`);
        setTimeout(() => fetchClips(jobId), 1000);
      }
    };
  }

  async function fetchClips(jobId) {
    try {
      const res = await fetch(`/clips/${jobId}`);
      const data = await res.json();
      
      localStorage.removeItem('currentJobId');
      
      const tl = gsap.timeline();
      tl.to(sectionProcessing, { 
        y: -10, opacity: 0, duration: 0.3, ease: "power2.inOut",
        onComplete: () => {
          sectionProcessing.classList.add('hidden');
          sectionClips.classList.remove('hidden');
          gsap.fromTo(sectionClips, { y: 10, opacity: 0 }, { y: 0, opacity: 1, duration: 0.4, ease: "power2.out" });
          renderClips(data.clips || []);
          if (currentPublishingMode() === 'auto') {
            setTimeout(() => triggerMassPublish('#clips-container'), 1000);
          }
        }
      });
    } catch(e) { console.error(e); }
  }

  function escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str ?? '';
    return d.innerHTML;
  }

  function renderClips(clips) {
    const container = document.getElementById('clips-container');
    if(!clips || clips.length === 0) {
      container.innerHTML = '<p class="text-muted">No clips generated.</p>';
      return;
    }
    
    let html = '';
    clips.forEach((clip, i) => {
      const score = typeof clip.hook_score !== 'undefined' ? clip.hook_score : '?';
      const rawTitle = clip.title || ('Viral Clip ' + (i+1));
      const cleanTitle = rawTitle.replace(/^(?:clip[_\s\-]*\d+[_\s\-]*)+/i, '').trim() || rawTitle;
      const cleanCaption = (clip.social_caption || '').replace(/^(?:clip[_\s\-]*\d+[_\s\-]*)+/i, '').trim();
      
      const numBadgeHtml = clip.clip_number 
        ? `<span class="clip-num-badge" style="background:rgba(99, 102, 241, 0.15); color:#818cf8; border:1px solid rgba(99, 102, 241, 0.3); padding:2px 8px; border-radius:12px; font-weight:700; font-size:0.75rem; letter-spacing:0.5px;">Clip #${clip.clip_number}</span>`
        : `<span class="clip-num-badge" style="background:rgba(99, 102, 241, 0.15); color:#818cf8; border:1px solid rgba(99, 102, 241, 0.3); padding:2px 8px; border-radius:12px; font-weight:700; font-size:0.75rem; letter-spacing:0.5px;">Clip #${i + 1}</span>`;

      let productsHtml = '';
      if (clip.product_recommendations && clip.product_recommendations.length > 0) {
        productsHtml = `<div class="product-suggestions" style="margin-bottom: 15px; background: rgba(255, 153, 0, 0.1); border-left: 3px solid #ff9900; padding: 10px; border-radius: 6px;">
          <div style="font-size: 0.75rem; font-weight: 700; color: #ff9900; text-transform: uppercase; margin-bottom: 6px; letter-spacing: 0.5px;"><i class="ri-amazon-fill"></i> Amazon Suggestion</div>
        `;
        clip.product_recommendations.forEach(prod => {
          const amzSearch = `https://www.amazon.com/s?k=${encodeURIComponent(prod.search_query)}`;
          productsHtml += `
            <div style="margin-bottom: 8px; font-size: 0.85rem; color: #d1d5db;">
              <strong style="color: #f3f4f6;">${escapeHtml(prod.product_name)}</strong> <span style="font-size: 0.75rem; color: #9ca3af;">(${escapeHtml(prod.category)})</span>
              <p style="margin: 4px 0; font-size: 0.8rem; line-height: 1.3; color: #9ca3af;">${escapeHtml(prod.reasoning)}</p>
              <a href="${amzSearch}" target="_blank" style="color: #ff9900; text-decoration: none; font-size: 0.75rem; font-weight: 600;">Search on Amazon &rarr;</a>
            </div>
          `;
        });
        productsHtml += `</div>`;
      }

      html += `
        <div class="clip-card" style="opacity:0; transform:translateY(30px);">
          <div style="position:relative;">
            <video src="${clip.url}" class="clip-video" controls></video>
          </div>
          <div class="clip-body">
            <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;">
              ${numBadgeHtml}
              <div class="clip-score" style="margin-top:0;"><i class="ri-fire-fill" style="color:#f59e0b;"></i> Score: ${score}/100</div>
            </div>
            <h3 class="clip-title" style="margin-bottom:8px; font-size:1.05rem; font-weight:700;">${i+1}. ${escapeHtml(cleanTitle)}</h3>
            <div style="position:relative;">
               <p class="clip-caption" style="font-size:0.85rem; color:#8b8b99; margin-bottom:15px; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden;">${escapeHtml(cleanCaption)}</p>
               <button class="btn-outline btn-sm btn-copy" data-text="${encodeURIComponent(cleanTitle + '\n\n' + cleanCaption)}" style="position:absolute; right:0; top:-10px; padding:2px 6px; font-size:0.7rem;"><i class="ri-clipboard-line"></i> Copy</button>
            </div>
            ${productsHtml}
            <div class="clip-footer">
              <span class="text-xs text-muted" style="font-weight:600; letter-spacing:1px; text-transform:uppercase;">Auto-selected</span>
                <a href="${clip.url}" download class="btn-primary btn-sm" style="padding:6px 12px; margin-right:8px; border-radius:8px; font-size:0.85rem; text-decoration:none;"><i class="ri-download-cloud-2-line"></i></a>
                <button class="btn-primary btn-sm btn-publish" data-clip="${clip.url}" data-products='${JSON.stringify(clip.product_recommendations || []).replace(/'/g, "&#39;")}' style="padding:6px 16px; font-size:0.8rem;">Publish</button>
              </div>
            </div>
          </div>
        </div>
      `;
    });
    container.innerHTML = html;
    gsap.to("#clips-container .clip-card", { y: 0, opacity: 1, duration: 0.4, stagger: 0.05, ease: "power2.out", delay: 0.1 });
  }

  function escapeUploadText(value) {
    return String(value || '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  }

  function formatUploadTime(epoch) {
    return epoch ? new Date(epoch * 1000).toLocaleString() : '—';
  }

  function formatUploadSize(size) {
    if (!size) return '—';
    return `${(size / (1024 * 1024)).toFixed(size > 1024 * 1024 * 1024 ? 1 : 0)} MB`;
  }
  function formatUploadDuration(seconds) {
    if (!seconds) return '—';
    return `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, '0')}`;
  }

  function uploadCard(upload, queuePosition = null) {
    const status = upload.status.replaceAll('_', ' ');
    const thumb = upload.video_url ? `<video class="upload-thumb" muted preload="metadata" src="${upload.video_url}"></video>` : '<div class="upload-thumb"></div>';
    const progress = Math.max(0, Math.min(100, upload.progress || 0));
    const elapsed = upload.status === 'uploading' ? ` · Elapsed ${Math.max(0, Math.floor((Date.now() / 1000 - upload.updated_at) / 60))}m · ETA —` : '';
    const action = (name, label, icon) => `<button class="btn-outline btn-sm" data-upload-id="${upload.id}" data-upload-action="${name}"><i class="${icon}"></i> ${label}</button>`;
    let actions = '';
    if (upload.status === 'needs_manual_verification') {
      actions += action('mark_completed', 'Mark Completed', 'ri-check-line') + action('retry', 'Retry', 'ri-refresh-line');
      actions += '<button class="btn-outline btn-sm" data-upload-open-instagram="1"><i class="ri-instagram-line"></i> Open Instagram</button>';
    } else if (['failed','login_required','challenge_required','rate_limited','rejected'].includes(upload.status)) {
      actions += action('retry', 'Retry', 'ri-refresh-line') + action('remove', 'Delete', 'ri-delete-bin-line');
    } else if (upload.status === 'completed') {
      if (upload.reel_url) actions += `<button class="btn-outline btn-sm" data-upload-link="${upload.reel_url}"><i class="ri-external-link-line"></i> Open Reel</button><button class="btn-outline btn-sm" data-copy-link="${upload.reel_url}"><i class="ri-file-copy-line"></i> Copy Link</button>`;
      else actions += '<button class="btn-outline btn-sm" data-upload-open-instagram="1"><i class="ri-instagram-line"></i> Open Instagram</button>';
    } else if (upload.status !== 'uploading') {
      actions += action('move_up', 'Up', 'ri-arrow-up-line') + action('move_down', 'Down', 'ri-arrow-down-line') + action('cancel', 'Cancel', 'ri-stop-circle-line');
    }
    actions += action('logs', 'Logs', 'ri-file-list-3-line') + action('export_logs', 'Export', 'ri-download-line');
    const position = queuePosition ? ` · Queue #${queuePosition}` : '';
    return `<article class="upload-card">
      ${thumb}<div><div class="upload-name">${escapeUploadText(upload.filename)}</div>
      <div class="upload-meta">Instagram${position} · ${formatUploadSize(upload.file_size)} · ${formatUploadDuration(upload.duration)} · ${formatUploadTime(upload.created_at)}${elapsed}</div>
      <div class="upload-step">${escapeUploadText(upload.message || status)}</div>
      <div class="upload-progress"><span style="width:${progress}%"></span></div></div>
      <div class="upload-actions">${actions}</div></article>`;
  }

  function setUploadList(id, uploads, queueStart = 0) {
    const target = document.getElementById(id);
    if (!target) return;
    target.innerHTML = uploads.length ? uploads.map((upload, index) => uploadCard(upload, queueStart ? queueStart + index : null)).join('') : '<p class="upload-empty">Nothing here.</p>';
  }

  function notifyUploadChange(upload) {
    const prior = seenUploadStates.get(upload.id);
    seenUploadStates.set(upload.id, upload.status);
    if (!prior || prior === upload.status || !['completed','failed','login_required','challenge_required','needs_manual_verification'].includes(upload.status)) return;
    if ('Notification' in window && Notification.permission === 'granted') {
      const notification = new Notification(`Instagram: ${upload.status.replaceAll('_', ' ')}`, { body: `${upload.filename}: ${upload.message || ''}` });
      notification.onclick = () => openUploadCenter();
    }
  }

  async function refreshUploadCenter() {
    try {
      const response = await fetch('/api/social/instagram/center');
      if (!response.ok) return;
      const data = await response.json();
      const uploads = data.uploads || [];
      uploads.forEach(notifyUploadChange);
      const counts = data.summary?.counts || {};
      const waiting = (counts.queued || 0) + (counts.retrying || 0);
      const uploading = counts.uploading || 0;
      const completed = counts.completed || 0;
      const mode = currentPublishingMode() === 'auto' ? 'Auto Publish Enabled' : currentPublishingMode() === 'disabled' ? 'Publishing Disabled' : 'Manual Publish';
      document.getElementById('upload-status-text').textContent = `${mode} · Uploading ${uploading} · Waiting ${waiting} · Completed ${completed}`;
      document.getElementById('upload-center-subtitle').textContent = data.summary?.paused ? 'Queue paused' : `${mode} · one Instagram upload at a time`;
      document.getElementById('btn-queue-pause').innerHTML = data.summary?.paused ? '<i class="ri-play-circle-line"></i> Resume Queue' : '<i class="ri-pause-circle-line"></i> Pause Queue';
      document.getElementById('upload-overview').innerHTML = [
        ['Waiting', waiting], ['Uploading', uploading], ['Completed', completed], ['Failed', (counts.failed || 0) + (counts.login_required || 0) + (counts.challenge_required || 0) + (counts.rate_limited || 0)]
      ].map(([label, value]) => `<div class="upload-metric"><span class="text-muted">${label}</span><strong>${value}</strong></div>`).join('');
      setUploadList('uploading-list', uploads.filter(item => item.status === 'uploading'));
      setUploadList('queue-list', uploads.filter(item => ['queued','retrying'].includes(item.status)).sort((a,b) => a.created_at - b.created_at), 1);
      setUploadList('manual-list', uploads.filter(item => item.status === 'needs_manual_verification'));
      setUploadList('failed-list', uploads.filter(item => ['failed','login_required','challenge_required','rate_limited','rejected'].includes(item.status)));
      setUploadList('completed-list', uploads.filter(item => item.status === 'completed'));
    } catch (error) { console.error('Upload Center refresh failed', error); }
  }

  function openUploadCenter() {
    [sectionUpload, sectionProcessing, sectionClips, sectionHistory].forEach(section => section.classList.add('hidden'));
    sectionUploadCenter.classList.remove('hidden');
    refreshUploadCenter();
    if (!uploadCenterTimer) uploadCenterTimer = setInterval(refreshUploadCenter, 2500);
    if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission();
  }

  function closeUploadCenter() {
    sectionUploadCenter.classList.add('hidden');
    sectionUpload.classList.remove('hidden');
    if (uploadCenterTimer) clearInterval(uploadCenterTimer);
    uploadCenterTimer = null;
  }

  document.getElementById('btn-upload-center')?.addEventListener('click', openUploadCenter);
  uploadStatusBar?.addEventListener('click', openUploadCenter);
  document.getElementById('btn-upload-center-back')?.addEventListener('click', closeUploadCenter);
  document.getElementById('btn-queue-pause')?.addEventListener('click', async () => {
    const paused = document.getElementById('btn-queue-pause').textContent.includes('Resume');
    await fetch('/api/social/instagram/queue', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action: paused ? 'resume' : 'pause'}) });
    refreshUploadCenter();
  });
  document.getElementById('btn-clear-failed')?.addEventListener('click', async () => {
    await fetch('/api/social/instagram/queue', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action:'clear_failed'}) });
    refreshUploadCenter();
  });
  document.getElementById('btn-remove-completed')?.addEventListener('click', async () => {
    await fetch('/api/social/instagram/queue', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action:'remove_completed'}) });
    refreshUploadCenter();
  });
  document.addEventListener('click', async event => {
    const target = event.target.closest('[data-upload-action]');
    if (target) {
      const uploadId = target.dataset.uploadId;
      const action = target.dataset.uploadAction;
      if (action === 'logs' || action === 'export_logs') {
        const response = await fetch(`/api/social/instagram/uploads/${uploadId}/events`);
        const data = await response.json();
        const timeline = (data.events || []).map(entry => `${formatUploadTime(entry.created_at)} · ${entry.event}\n${entry.detail}`).join('\n\n') || 'No logs yet.';
        if (action === 'logs') Toast.show(timeline, "info", 6000);
        else {
          const link = document.createElement('a');
          link.href = URL.createObjectURL(new Blob([timeline], {type:'text/plain'}));
          link.download = `obscura-upload-${uploadId}.log`;
          link.click();
          URL.revokeObjectURL(link.href);
        }
      } else {
        await fetch(`/api/social/instagram/queue/${uploadId}`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action}) });
        refreshUploadCenter();
      }
    }
    const link = event.target.closest('[data-upload-link]');
    if (link) window.open(link.dataset.uploadLink, '_blank', 'noopener');
    const copy = event.target.closest('[data-copy-link]');
    if (copy) navigator.clipboard.writeText(copy.dataset.copyLink);
    if (event.target.closest('[data-upload-open-instagram]')) window.open('https://www.instagram.com/', '_blank', 'noopener');
  });

  refreshUploadCenter();

  async function renderHistory() {
    const container = document.getElementById('history-container');
    container.innerHTML = '<p>Loading history...</p>';
    
    try {
      const res = await fetch('/clips');
      const data = await res.json();
      const pastClips = data.clips || [];
      
      if(pastClips.length === 0) {
        container.innerHTML = '<p class="text-muted">No history found.</p>';
        return;
      }
      
      let html = '';
      
      pastClips.forEach((clip, i) => {
        const score = typeof clip.hook_score !== 'undefined' ? clip.hook_score : '?';
        const rawTitle = clip.title || 'Past Clip';
        const cleanTitle = rawTitle.replace(/^(?:clip[_\s\-]*\d+[_\s\-]*)+/i, '').trim() || rawTitle;
        const cleanCaption = (clip.social_caption || '').replace(/^(?:clip[_\s\-]*\d+[_\s\-]*)+/i, '').trim();

        const numBadgeHtml = clip.clip_number 
          ? `<span class="clip-num-badge" style="background:rgba(99, 102, 241, 0.15); color:#818cf8; border:1px solid rgba(99, 102, 241, 0.3); padding:2px 8px; border-radius:12px; font-weight:700; font-size:0.75rem; letter-spacing:0.5px;">Clip #${clip.clip_number}</span>`
          : `<span class="clip-num-badge" style="background:rgba(99, 102, 241, 0.15); color:#818cf8; border:1px solid rgba(99, 102, 241, 0.3); padding:2px 8px; border-radius:12px; font-weight:700; font-size:0.75rem; letter-spacing:0.5px;">Clip #${i + 1}</span>`;

        let productsHtml = '';
        if (clip.product_recommendations && clip.product_recommendations.length > 0) {
          productsHtml = `<div class="product-suggestions" style="margin-bottom: 15px; background: rgba(255, 153, 0, 0.1); border-left: 3px solid #ff9900; padding: 10px; border-radius: 6px;">
            <div style="font-size: 0.75rem; font-weight: 700; color: #ff9900; text-transform: uppercase; margin-bottom: 6px; letter-spacing: 0.5px;"><i class="ri-amazon-fill"></i> Amazon Suggestion</div>
          `;
          clip.product_recommendations.forEach(prod => {
            const amzSearch = `https://www.amazon.com/s?k=${encodeURIComponent(prod.search_query)}`;
            productsHtml += `
              <div style="margin-bottom: 8px; font-size: 0.85rem; color: #d1d5db;">
                <strong style="color: #f3f4f6;">${escapeHtml(prod.product_name)}</strong> <span style="font-size: 0.75rem; color: #9ca3af;">(${escapeHtml(prod.category)})</span>
                <p style="margin: 4px 0; font-size: 0.8rem; line-height: 1.3; color: #9ca3af;">${escapeHtml(prod.reasoning)}</p>
                <a href="${amzSearch}" target="_blank" style="color: #ff9900; text-decoration: none; font-size: 0.75rem; font-weight: 600;">Search on Amazon &rarr;</a>
              </div>
            `;
          });
          productsHtml += `</div>`;
        }

        html += `
          <div class="clip-card" style="opacity:0; transform:translateY(30px);">
            <div style="position:relative;">
              <video src="${clip.url}" class="clip-video" controls></video>
            </div>
            <div class="clip-body">
              <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;">
                ${numBadgeHtml}
                <div class="clip-score" style="margin-top:0;"><i class="ri-fire-fill" style="color:#f59e0b;"></i> Score: ${score}/100</div>
              </div>
              <h3 class="clip-title" style="margin-bottom:8px; font-size:1.05rem; font-weight:700;">${i+1}. ${escapeHtml(cleanTitle)}</h3>
              <div style="position:relative;">
                 <p class="clip-caption" style="font-size:0.85rem; color:#8b8b99; margin-bottom:15px; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden;">${escapeHtml(cleanCaption)}</p>
                 <button class="btn-outline btn-sm btn-copy" data-text="${encodeURIComponent(cleanTitle + '\n\n' + cleanCaption)}" style="position:absolute; right:0; top:-10px; padding:2px 6px; font-size:0.7rem;"><i class="ri-clipboard-line"></i> Copy</button>
              </div>
              ${productsHtml}
              <div class="clip-footer">
                <span class="text-xs text-muted" style="font-weight:600; letter-spacing:1px; text-transform:uppercase;">History</span>
                <div class="platform-toggles">
                  <a href="${clip.url}" download class="btn-outline btn-sm" style="padding:4px 12px; margin-right:8px; font-size:0.8rem; text-decoration:none;"><i class="ri-download-cloud-2-line"></i></a>
                  <button class="btn-primary btn-sm btn-publish" data-clip="${clip.url}" style="padding:4px 12px; font-size:0.8rem;">Publish</button>
                </div>
              </div>
            </div>
          </div>
        `;
      });
      container.innerHTML = html;
      gsap.to("#history-container .clip-card", { y: 0, opacity: 1, duration: 0.4, stagger: 0.05, ease: "power2.out", delay: 0.1 });
      
    } catch(e) {
      console.error(e);
      container.innerHTML = '<p class="text-muted">Failed to load history.</p>';
    }
  }

  btnCancel.addEventListener('click', async () => {
    if (currentJobId) {
      try {
        await fetch(`/api/cancel/${currentJobId}`, { method: 'POST' });
      } catch(e) { console.error(e); }
    }
    if (currentWs) currentWs.close();
    
    localStorage.removeItem('currentJobId');
    
    // Reset to upload screen
    gsap.to(sectionProcessing, { 
      opacity: 0, y: 30, duration: 0.5, ease: "power2.inOut", 
      onComplete: () => {
        sectionProcessing.classList.add('hidden');
        sectionUpload.classList.remove('hidden');
        gsap.fromTo(sectionUpload, { y: -30, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6, ease: "power3.out" });
        loadRecentUploads(); // refresh uploads
      }
    });
  });

  const btnBackFromClips = document.getElementById('btn-back-from-clips');
  if (btnBackFromClips) {
    btnBackFromClips.addEventListener('click', () => {
      gsap.to(sectionClips, { 
        opacity: 0, y: 30, duration: 0.4, ease: "power2.inOut", 
        onComplete: () => {
          sectionClips.classList.add('hidden');
          sectionUpload.classList.remove('hidden');
          gsap.fromTo(sectionUpload, { y: -30, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6, ease: "power3.out" });
          loadRecentUploads();
        }
      });
    });
  }

  // Handle Mass Publishing & Copying
  function triggerMassPublish(containerId) {
    const modal = document.getElementById('modal-publish');
    document.getElementById('publish-selection-view').classList.add('hidden');
    document.getElementById('publish-progress-view').classList.remove('hidden');
    document.getElementById('publish-progress-status').textContent = 'Mass publishing...';
    document.getElementById('publish-progress-percent').textContent = '0%';
    document.getElementById('publish-progress-fill').style.width = '0%';
    document.getElementById('publish-console-output').innerHTML = '';
    document.getElementById('btn-publish-done').classList.add('hidden');
    modal.classList.remove('hidden');

    const platforms = [];
    if(document.getElementById('opt-instagram')?.checked ?? true) platforms.push('instagram');
    if(document.getElementById('opt-youtube')?.checked ?? true) platforms.push('youtube');

    document.querySelectorAll(`${containerId} .btn-publish`).forEach(btn => {
      const clipPath = btn.getAttribute('data-clip');
      if(!clipPath) return;
      const card = btn.closest('.clip-card');
      const title = card ? card.querySelector('.clip-title').textContent : 'Viral Clip';
      const caption = card ? card.querySelector('.clip-caption').textContent : 'Check out this awesome clip! #viral #fyp';
      const parts = clipPath.split('/');
      if (parts.length >= 3) {
        const jobId = parts[parts.length - 2];
        const filename = parts[parts.length - 1];
        executePublish(jobId, filename, title, caption, platforms, btn, true);
      }
    });
  }

  document.getElementById('btn-publish-all')?.addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    btn.innerHTML = '<i class="ri-check-line"></i> Mass Post Initiated';
    btn.classList.add('btn-success');
    triggerMassPublish('#clips-container');
  });
  
  document.getElementById('btn-mass-post-history')?.addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    btn.innerHTML = '<i class="ri-check-line"></i> Mass Post Initiated';
    btn.classList.add('btn-success');
    triggerMassPublish('#history-container');
  });

  document.addEventListener('click', async (e) => {
    // Copy Title & Caption
    if (e.target.closest('.btn-copy')) {
      const btn = e.target.closest('.btn-copy');
      const textToCopy = decodeURIComponent(btn.getAttribute('data-text'));
      try {
        await navigator.clipboard.writeText(textToCopy);
        const originalHtml = btn.innerHTML;
        btn.innerHTML = '<i class="ri-check-line"></i> Copied';
        setTimeout(() => btn.innerHTML = originalHtml, 2000);
      } catch(err) {
        console.error('Failed to copy', err);
      }
      return;
    }
    
        // Publish Single Clip
    if (e.target.closest('.btn-publish')) {
      const btn = e.target.closest('.btn-publish');
      const clipPath = btn.getAttribute('data-clip');
      let products = [];
      const ytShoppingEnabled = document.getElementById('opt-yt-shopping')?.checked ?? (localStorage.getItem('ytShoppingEnabled') !== 'false');
      if (ytShoppingEnabled) {
        try { products = JSON.parse(btn.getAttribute('data-products') || '[]'); } catch(e) {}
      }
      
      const card = btn.closest('.clip-card');
      const title = card ? card.querySelector('.clip-title').textContent : 'Viral Clip';
      const caption = card ? card.querySelector('.clip-caption').textContent : 'Check out this awesome clip! #viral #fyp';
      
      const parts = clipPath.split('/');
      if (parts.length < 3) return;
      const jobId = parts[parts.length - 2];
      const filename = parts[parts.length - 1];
      
      if (!e.isTrusted) {
        // Mass publish programmatically clicked this
        executePublish(jobId, filename, title, caption, products, getSelectedPlatforms(), btn, false);
        return;
      }
      
      // Show modal for single manual publish
      const modal = document.getElementById('modal-publish');
      const selectionView = document.getElementById('publish-selection-view');
      const progressView = document.getElementById('publish-progress-view');
      
      // Sync checkboxes with global settings
      document.getElementById('chk-pub-instagram').checked = document.getElementById('opt-instagram')?.checked ?? true;
      document.getElementById('chk-pub-youtube').checked = document.getElementById('opt-youtube')?.checked ?? true;
      
      selectionView.classList.remove('hidden');
      progressView.classList.add('hidden');
      modal.classList.remove('hidden');
      
      const btnConfirm = document.getElementById('btn-confirm-publish');
      const newBtnConfirm = btnConfirm.cloneNode(true);
      btnConfirm.parentNode.replaceChild(newBtnConfirm, btnConfirm);
      
      newBtnConfirm.addEventListener('click', () => {
        const doIg = document.getElementById('chk-pub-instagram').checked;
        const doYt = document.getElementById('chk-pub-youtube').checked;
        const platforms = [];
        if(doIg) platforms.push('instagram');
        if(doYt) platforms.push('youtube');
        
        if(platforms.length === 0) {
          alert('Please select at least one platform.');
          return;
        }
        
        selectionView.classList.add('hidden');
        progressView.classList.remove('hidden');
        document.getElementById('publish-progress-status').textContent = 'Starting upload...';
        document.getElementById('publish-progress-percent').textContent = '0%';
        document.getElementById('publish-progress-fill').style.width = '0%';
        document.getElementById('publish-console-output').innerHTML = '';
        document.getElementById('btn-publish-done').classList.add('hidden');
        
        executePublish(jobId, filename, title, caption, products, platforms, btn, true);
      });
    }
  });

  async function executePublish(jobId, filename, title, caption, products, platforms, btn, updateModal = false) {
    if(!updateModal) {
      btn.innerHTML = '<i class="ri-loader-4-line spin"></i> Publishing...';
      btn.disabled = true;
    }
    
    let lastLogMsg = null;
    function logToModal(msg) {
      if(!updateModal || !msg) return;
      if(msg === lastLogMsg) return;
      lastLogMsg = msg;
      const consoleEl = document.getElementById('publish-console-output');
      const div = document.createElement('div');
      div.textContent = msg;
      consoleEl.appendChild(div);
      consoleEl.scrollTop = consoleEl.scrollHeight;
    }
    
    function setProgress(pct, statusMsg) {
      if(updateModal) {
        document.getElementById('publish-progress-percent').textContent = `${pct}%`;
        document.getElementById('publish-progress-fill').style.width = `${pct}%`;
        if(statusMsg) document.getElementById('publish-progress-status').textContent = statusMsg;
      } else {
        btn.textContent = statusMsg || `Uploading ${pct}%...`;
      }
    }
    
    try {
      const response = await fetch('/api/social/post', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          job_id: jobId, clip_filename: filename, title: title, caption: caption,
          platforms: platforms, allow_duplicate: false, product_recommendations: products
        })
      });
      let data = await response.json();
      
      if (!data.upload_id && data.error?.includes('already submitted')) {
        if(updateModal || window.confirm(`${data.error}\n\nUpload this exact clip again anyway?`)) {
          const retryRes = await fetch('/api/social/post', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              job_id: jobId, clip_filename: filename, title: title, caption: caption,
              platforms: platforms, allow_duplicate: true, product_recommendations: products
            })
          });
          data = await retryRes.json();
        } else {
          btn.disabled = false;
          btn.innerHTML = 'Publish';
          return;
        }
      }
      
      if(data.upload_id) {
        logToModal(`Upload initialized: ${data.upload_id}`);
        // Poll for status
        const poll = setInterval(async () => {
          const stRes = await fetch(`/api/social/post-status/${data.upload_id}`);
          if (!stRes.ok) {
            clearInterval(poll);
            logToModal(`Error: Unable to read upload status`);
            if(!updateModal) {
              btn.innerHTML = 'Failed';
              btn.disabled = false;
            }
            return;
          }
          const stData = await stRes.json();
          
          if (stData.status === 'uploading' || stData.status === 'retrying') {
             const pct = stData.progress || 10;
             const msg = stData.message || 'Uploading...';
             setProgress(pct, msg);
             logToModal(msg);
          }
          
          if(['completed', 'scheduled', 'failed', 'needs_manual_verification', 'login_required', 'rate_limited', 'challenge_required', 'rejected', 'partial'].includes(stData.status)) {
            clearInterval(poll);
            setProgress(100, `Done: ${stData.status}`);
            logToModal(`Process finished with status: ${stData.status}`);
            if(stData.error) logToModal(`Error: ${stData.error}`);
            if(stData.results) {
              for (const [plat, res] of Object.entries(stData.results)) {
                if (!res.success && res.error) {
                  logToModal(`[${plat.toUpperCase()}] Error: ${res.error}`);
                }
              }
            }
            
            if(updateModal) {
              const doneBtn = document.getElementById('btn-publish-done');
              doneBtn.classList.remove('hidden');
              const newDoneBtn = doneBtn.cloneNode(true);
              doneBtn.parentNode.replaceChild(newDoneBtn, doneBtn);
              newDoneBtn.addEventListener('click', () => {
                document.getElementById('modal-publish').classList.add('hidden');
              });
            }
            
            if(stData.status === 'completed' || stData.status === 'scheduled') {
              btn.innerHTML = stData.status === 'scheduled' ? '<i class="ri-time-line"></i> Scheduled (12:00 AM)' : '<i class="ri-check-line"></i> Published!';
              btn.classList.add('btn-success');
            } else if (stData.status === 'needs_manual_verification') {
              btn.innerHTML = '<i class="ri-eye-line"></i> Check Instagram';
              btn.title = stData.error || stData.message || 'Share was clicked but Instagram confirmation was not observed.';
              btn.classList.add('btn-outline');
            } else {
              const failure = stData.error || stData.message || 'Upload failed';
              btn.textContent = `Failed: ${failure.slice(0, 42)}`;
              btn.title = failure;
              btn.classList.add('btn-danger');
            }
            btn.disabled = false;
          }
        }, 1500);
      } else {
         logToModal(`Failed to initialize: ${data.error}`);
         if(!updateModal) {
           btn.innerHTML = data.error || 'Failed';
           btn.title = data.error || '';
           btn.disabled = false;
         }
      }
    } catch(err) {
      console.error(err);
      logToModal(`Exception: ${err.message}`);
      if(!updateModal) {
        btn.innerHTML = 'Failed';
        btn.disabled = false;
      }
    }
  }

  // Handle modal close
  document.getElementById('btn-close-publish-modal')?.addEventListener('click', () => {
    document.getElementById('modal-publish').classList.add('hidden');
  });

});
