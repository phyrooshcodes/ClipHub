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

// Theme Manager (Light, Dark, System Sync)
const ThemeManager = {
  storageKey: 'cliphub_theme',

  init() {
    const saved = localStorage.getItem(this.storageKey) || 'system';
    this.apply(saved, false);

    if (window.matchMedia) {
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
        if (this.getTheme() === 'system') {
          this.apply('system', false);
        }
      });
    }

    document.querySelectorAll('input[name="app-theme"]').forEach((radio) => {
      radio.addEventListener('change', (e) => {
        this.apply(e.target.value, true);
        Toast.show(`Theme updated to ${e.target.value}`, 'info', 2000);
      });
    });

    document.getElementById('btn-theme-toggle')?.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const currentDark = document.documentElement.classList.contains('dark-theme');
      const nextTheme = currentDark ? 'light' : 'dark';
      this.apply(nextTheme, true);
      Toast.show(`Switched to ${nextTheme} theme`, 'info', 2000);
    });
  },

  getTheme() {
    return localStorage.getItem(this.storageKey) || 'system';
  },

  apply(theme, persist = true) {
    if (persist) {
      localStorage.setItem(this.storageKey, theme);
    }
    
    const isDark = theme === 'dark' || (theme === 'system' && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);

    if (isDark) {
      document.documentElement.classList.remove('light-theme');
      document.documentElement.classList.add('dark-theme');
      document.body.classList.remove('light-theme');
      document.body.classList.add('dark-theme');
    } else {
      document.documentElement.classList.remove('dark-theme');
      document.documentElement.classList.add('light-theme');
      document.body.classList.remove('dark-theme');
      document.body.classList.add('light-theme');
    }

    // Update settings radio buttons and active cards
    const radio = document.querySelector(`input[name="app-theme"][value="${theme}"]`);
    if (radio) radio.checked = true;
    
    document.querySelectorAll('.theme-card').forEach((card) => card.classList.remove('active'));
    document.getElementById(`theme-card-${theme}`)?.classList.add('active');

    // Update quick toggle icon
    const toggleIcon = document.querySelector('#btn-theme-toggle i');
    if (toggleIcon) {
      toggleIcon.className = isDark ? 'ri-sun-line' : 'ri-moon-line';
    }

    // Update settings status pill
    const statusPill = document.getElementById('theme-status-pill');
    if (statusPill) {
      if (theme === 'system') statusPill.textContent = `System (${isDark ? 'Dark' : 'Light'})`;
      else statusPill.textContent = theme === 'dark' ? 'Dark Mode' : 'Light Mode';
    }
  }
};

// Sidebar Manager (Draggable Resizer & Collapsible Toggle)
const SidebarManager = {
  sidebarEl: null,
  resizerEl: null,
  toggleBtn: null,
  isResizing: false,
  minWidth: 210,
  maxWidth: 450,
  defaultWidth: 250,

  init() {
    this.sidebarEl = document.getElementById('app-sidebar');
    this.resizerEl = document.getElementById('sidebar-resizer');
    this.toggleBtn = document.getElementById('btn-sidebar-toggle');
    if (!this.sidebarEl || !this.resizerEl) return;

    // Restore saved width
    const savedWidth = parseInt(localStorage.getItem('cliphub_sidebar_width'), 10);
    if (savedWidth && savedWidth >= this.minWidth && savedWidth <= this.maxWidth) {
      document.documentElement.style.setProperty('--sidebar-w', `${savedWidth}px`);
    } else {
      document.documentElement.style.setProperty('--sidebar-w', `${this.defaultWidth}px`);
      localStorage.setItem('cliphub_sidebar_width', this.defaultWidth);
    }

    // Restore collapsed state
    const isCollapsed = localStorage.getItem('cliphub_sidebar_collapsed') === 'true';
    if (isCollapsed) {
      this.sidebarEl.classList.add('collapsed');
      if (this.toggleBtn) {
        this.toggleBtn.innerHTML = '<i class="ri-layout-right-line"></i>';
      }
    }

    // Toggle button click
    this.toggleBtn?.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.toggle();
    });

    // Keyboard shortcut Ctrl+B or Cmd+B
    window.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
        const activeTag = document.activeElement?.tagName;
        if (activeTag !== 'INPUT' && activeTag !== 'TEXTAREA') {
          e.preventDefault();
          this.toggle();
        }
      }
    });

    // Double-click resizer to reset to default 250px
    this.resizerEl.addEventListener('dblclick', () => {
      this.sidebarEl.classList.remove('collapsed');
      document.documentElement.style.setProperty('--sidebar-w', `${this.defaultWidth}px`);
      localStorage.setItem('cliphub_sidebar_width', this.defaultWidth);
      localStorage.setItem('cliphub_sidebar_collapsed', 'false');
      if (this.toggleBtn) {
        this.toggleBtn.innerHTML = '<i class="ri-layout-left-line"></i>';
      }
    });

    // Drag Resizing
    this.resizerEl.addEventListener('mousedown', (e) => this.startResize(e));
    this.resizerEl.addEventListener('touchstart', (e) => this.startResize(e.touches[0]), { passive: true });
  },

  toggle() {
    if (!this.sidebarEl) return;
    const isCollapsed = this.sidebarEl.classList.toggle('collapsed');
    localStorage.setItem('cliphub_sidebar_collapsed', isCollapsed ? 'true' : 'false');
    if (this.toggleBtn) {
      this.toggleBtn.innerHTML = isCollapsed ? '<i class="ri-layout-right-line"></i>' : '<i class="ri-layout-left-line"></i>';
      this.toggleBtn.title = isCollapsed ? 'Expand Sidebar (Ctrl+B)' : 'Collapse Sidebar (Ctrl+B)';
    }
  },

  startResize(e) {
    if (!this.sidebarEl) return;
    this.isResizing = true;
    this.sidebarEl.classList.add('is-resizing');
    this.resizerEl.classList.add('active');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    const onMove = (moveEvent) => {
      if (!this.isResizing) return;
      const clientX = moveEvent.clientX || (moveEvent.touches && moveEvent.touches[0]?.clientX);
      if (clientX === undefined) return;

      if (clientX < 135) {
        // Auto-collapse if dragged very small
        this.sidebarEl.classList.add('collapsed');
        localStorage.setItem('cliphub_sidebar_collapsed', 'true');
        if (this.toggleBtn) this.toggleBtn.innerHTML = '<i class="ri-layout-right-line"></i>';
      } else {
        this.sidebarEl.classList.remove('collapsed');
        localStorage.setItem('cliphub_sidebar_collapsed', 'false');
        if (this.toggleBtn) this.toggleBtn.innerHTML = '<i class="ri-layout-left-line"></i>';

        const newWidth = Math.max(this.minWidth, Math.min(this.maxWidth, clientX));
        document.documentElement.style.setProperty('--sidebar-w', `${newWidth}px`);
        localStorage.setItem('cliphub_sidebar_width', newWidth);
      }
    };

    const onEnd = () => {
      this.isResizing = false;
      this.sidebarEl.classList.remove('is-resizing');
      this.resizerEl.classList.remove('active');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onEnd);
      window.removeEventListener('touchmove', onMove);
      window.removeEventListener('touchend', onEnd);
    };

    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onEnd);
    window.addEventListener('touchmove', onMove, { passive: true });
    window.addEventListener('touchend', onEnd);
  }
};

// UI State Management & GSAP Animations
document.addEventListener("DOMContentLoaded", () => {
  
  // Initialize Toast, Theme Manager, and Sidebar Manager
  Toast.init();
  ThemeManager.init();
  SidebarManager.init();

  async function refreshSystemBadges() {
    try {
      const data = await fetch('/api/system-status').then(r => r.json());
      const bGpu = document.getElementById('ui-gpu-status');
      const bNvenc = document.getElementById('ui-nvenc-status');
      const bKokoro = document.getElementById('ui-kokoro-status');
      const bWhisper = document.getElementById('ui-whisper-status');
      
      const formatGpu = (gpu) => {
        if (!gpu) return 'GPU';
        if (gpu.includes('RTX') || gpu.includes('GTX')) {
          const m = gpu.match(/(RTX\s*\d+(?:\s*Ti)?|GTX\s*\d+)/i);
          return m ? m[1] : 'NVIDIA';
        }
        return gpu.length > 10 ? gpu.slice(0, 8) + '…' : gpu;
      };

      const renderBadge = (txt, isGood, tooltip = '') => `<span title="${tooltip || txt}" style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:72px;">${txt}</span> <div class="dot-green" style="${isGood ? '' : 'background:#cbd5e1;box-shadow:none;'}"></div>`;
      
      if (bGpu) bGpu.innerHTML = renderBadge(formatGpu(data.gpu), data.gpu !== 'CPU Only' && data.gpu !== 'CPU / Unknown', data.gpu);
      if (bNvenc) bNvenc.innerHTML = renderBadge('NVENC', data.nvenc === 'Ready', `NVENC: ${data.nvenc}`);
      if (bKokoro) bKokoro.innerHTML = renderBadge('TTS', data.kokoro === 'Ready', `Kokoro TTS: ${data.kokoro}`);
      if (bWhisper) bWhisper.innerHTML = renderBadge('Whisper', data.whisper === 'Ready', `Whisper ASR: ${data.whisper}`);
      
    } catch (e) {
      console.error("Failed to refresh badges", e);
    }
  }
  refreshSystemBadges();

  // Mobile Menu Toggle
  const btnMobileMenu = document.getElementById('btn-mobile-menu');
  const navActionsMenu = document.getElementById('nav-actions-menu');
  if (btnMobileMenu && navActionsMenu) {
    btnMobileMenu.addEventListener('click', (e) => {
      e.stopPropagation();
      navActionsMenu.classList.toggle('show');
    });
    // Close menu when clicking outside
    document.addEventListener('click', (e) => {
      if (!navActionsMenu.contains(e.target) && !btnMobileMenu.contains(e.target)) {
        navActionsMenu.classList.remove('show');
      }
    });
  }
  // Refresh badges every 30s
  setInterval(refreshSystemBadges, 30000);
  
  // Pro Creator Keyboard Shortcuts
  document.addEventListener('keydown', (e) => {
    const isEditing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName);
    
    // Escape closes any open modal
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal-backdrop:not(.hidden)').forEach(m => m.classList.add('hidden'));
    }
    
    // Space toggles main video player if not editing text
    if (e.code === 'Space' && !isEditing) {
      const v = document.getElementById('main-video');
      if (v && v.src && v.style.display !== 'none') {
        e.preventDefault();
        v.paused ? v.play() : v.pause();
      }
    }
  });
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
    1:   { id: 'step-demux',  name: 'Audio Extraction',     percent: 15 },
    2:   { id: 'step-asr',    name: 'Speech Transcription',  percent: 32 },
    3:   { id: 'step-hook',   name: 'Viral Hook Detection', percent: 48 },
    3.5: { id: 'step-hook',   name: 'AI Commentary Writing',percent: 62 },
    4:   { id: 'step-face',   name: 'Face Tracking Framing',percent: 74 },
    4.5: { id: 'step-subs',   name: 'AI Voice Synthesis',   percent: 82 },
    5:   { id: 'step-subs',   name: 'Kinetic Subtitles',    percent: 88 },
    6:   { id: 'step-render', name: 'GPU NVENC Rendering',  percent: 94 }
  };

  // GSAP Initial Setup - Ensure visibility gracefully
  if (typeof gsap !== 'undefined') {
    try {
      gsap.fromTo(".hero-title", { y: 20, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5, ease: "power2.out" });
      gsap.fromTo(".hero-subtitle", { y: 15, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5, delay: 0.1, ease: "power2.out" });
      gsap.fromTo(".dropzone", { scale: 0.98, opacity: 0, y: 10 }, { scale: 1, opacity: 1, y: 0, duration: 0.5, delay: 0.2, ease: "power2.out" });
      gsap.fromTo(".divider", { opacity: 0 }, { opacity: 1, duration: 0.5, delay: 0.3, ease: "power2.out" });
      gsap.fromTo(".url-input-wrapper", { y: 15, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5, delay: 0.4, ease: "power2.out" });
    } catch(e) {
      console.warn("GSAP animation skipped", e);
    }
  }

  // Handle Upload Events
  let stagedFile = null;

  function updateDropzoneUI() {
    const title = document.getElementById('dz-title');
    const sub = document.getElementById('dz-sub');
    const btnRemove = document.getElementById('btn-remove-file');
    const btnBrowse = document.querySelector('.btn-browse');
    
    if (stagedFile) {
      title.textContent = "File Ready for Processing";
      sub.textContent = stagedFile.name;
      btnRemove.classList.remove('hidden');
      btnBrowse.classList.add('hidden');
    } else {
      title.textContent = "Drop your video here";
      sub.textContent = "MP4, MOV, MKV — any format works";
      btnRemove.classList.add('hidden');
      btnBrowse.classList.remove('hidden');
    }
  }

  dropzone.addEventListener('click', (e) => {
    if (!stagedFile && !e.target.closest('.yt-input-wrapper') && !e.target.closest('#btn-proceed') && !e.target.closest('.yt-divider')) {
      fileInput.click();
    }
  });

  document.querySelector('.btn-browse')?.addEventListener('click', (e) => {
    e.stopPropagation();
    fileInput.click();
  });
  dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('dragover'); });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files.length) {
      stagedFile = e.dataTransfer.files[0];
      updateDropzoneUI();
    }
  });
  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length) {
      stagedFile = e.target.files[0];
      updateDropzoneUI();
    }
  });
  
  document.getElementById('btn-remove-file')?.addEventListener('click', (e) => {
    e.stopPropagation();
    stagedFile = null;
    fileInput.value = '';
    updateDropzoneUI();
  });
  
  document.getElementById('btn-proceed')?.addEventListener('click', (e) => {
    e.stopPropagation();
    const ytUrl = document.getElementById('yt-link-input').value.trim();
    
    if (stagedFile && ytUrl) {
      Toast.show("Please choose either a file OR a YouTube link to process, not both!", "error");
      return;
    }
    
    if (stagedFile) {
      openCaptionStudio(stagedFile, false, false, false);
    } else if (ytUrl) {
      openCaptionStudio(ytUrl, true, false, false);
    } else {
      Toast.show("Please select a file or enter a YouTube link first.", "info");
    }
  });
  
  // YouTube link import button
  document.getElementById('btn-yt-import')?.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    const ytUrl = document.getElementById('yt-link-input')?.value.trim();
    if (!ytUrl) {
      Toast.show("Please paste a valid YouTube URL first.", "info");
      return;
    }
    openCaptionStudio(ytUrl, true, false, false);
  });
  
  document.getElementById('yt-link-input')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      document.getElementById('btn-yt-import')?.click();
    }
  });

  // Wire up sidebar navigation and modals
  document.getElementById('btn-nav-studio')?.addEventListener('click', (e) => {
    e.preventDefault();
    document.querySelectorAll('.sidebar-nav .nav-item').forEach(el => el.classList.remove('active'));
    document.getElementById('btn-nav-studio')?.classList.add('active');
    document.getElementById('modal-gallery')?.classList.add('hidden');
    document.getElementById('modal-history')?.classList.add('hidden');
    document.getElementById('modal-recent-uploads')?.classList.add('hidden');
  });

  document.getElementById('btn-nav-recent')?.addEventListener('click', (e) => {
    e.preventDefault();
    document.getElementById('modal-recent-uploads')?.classList.remove('hidden');
    fetchRecentUploads();
  });

  document.getElementById('btn-open-recent-uploads')?.addEventListener('click', (e) => {
    e.preventDefault();
    document.getElementById('modal-recent-uploads')?.classList.remove('hidden');
    fetchRecentUploads();
  });

  document.getElementById('btn-close-recent-uploads')?.addEventListener('click', () => {
    document.getElementById('modal-recent-uploads')?.classList.add('hidden');
  });

  document.getElementById('btn-nav-gallery')?.addEventListener('click', (e) => {
    e.preventDefault();
    document.querySelectorAll('.sidebar-nav .nav-item').forEach(el => el.classList.remove('active'));
    document.getElementById('btn-nav-gallery')?.classList.add('active');
    const modal = document.getElementById('modal-gallery');
    if (modal) {
      modal.classList.remove('hidden');
      fetchGalleryClips(currentJobId);
    }
  });

  document.getElementById('btn-back-from-clips')?.addEventListener('click', () => {
    document.getElementById('modal-gallery')?.classList.add('hidden');
    document.getElementById('btn-nav-studio')?.classList.add('active');
    document.getElementById('btn-nav-gallery')?.classList.remove('active');
  });

  document.getElementById('btn-history')?.addEventListener('click', (e) => {
    e.preventDefault();
    document.querySelectorAll('.sidebar-nav .nav-item').forEach(el => el.classList.remove('active'));
    document.getElementById('btn-history')?.classList.add('active');
    const modal = document.getElementById('modal-history');
    if (modal) {
      modal.classList.remove('hidden');
      renderHistory();
    }
  });

  document.getElementById('btn-close-history')?.addEventListener('click', () => {
    document.getElementById('modal-history')?.classList.add('hidden');
    document.getElementById('btn-nav-studio')?.classList.add('active');
    document.getElementById('btn-history')?.classList.remove('active');
  });

  document.getElementById('btn-settings')?.addEventListener('click', (e) => {
    e.preventDefault();
    document.getElementById('modal-settings')?.classList.remove('hidden');
    refreshNvidiaKeyStatus();
    refreshSocialStatus();
    loadCharacters();
    loadCovers();
  });

  document.getElementById('btn-close-settings')?.addEventListener('click', () => {
    document.getElementById('modal-settings')?.classList.add('hidden');
  });

  async function fetchRecentUploads() {
    const grid = document.getElementById('recent-uploads-grid');
    const empty = document.getElementById('recent-uploads-empty');
    if (!grid) return;
    grid.innerHTML = '<div style="grid-column: 1/-1; text-align:center; padding:30px; color:var(--text-muted);"><i class="ri-loader-4-line spin" style="font-size:24px;"></i><p style="margin-top:8px;">Scanning media library...</p></div>';
    
    try {
      const res = await fetch('/api/uploads');
      const data = await res.json();
      grid.innerHTML = '';
      if (!data.uploads || data.uploads.length === 0) {
        if (empty) empty.classList.remove('hidden');
        return;
      }
      if (empty) empty.classList.add('hidden');

      data.uploads.forEach(u => {
        const card = document.createElement('div');
        card.className = 'review-card';
        card.style.cssText = 'display:flex; flex-direction:column; justify-content:space-between; gap:12px; padding:16px;';
        
        card.innerHTML = `
          <div>
            <div style="display:flex; align-items:flex-start; gap:10px; margin-bottom:8px;">
              <div style="width:36px; height:36px; border-radius:var(--radius-sm); background:var(--brand-primary-light); color:var(--brand-primary); display:flex; align-items:center; justify-content:center; font-size:18px; flex-shrink:0;">
                <i class="ri-video-fill"></i>
              </div>
              <div style="overflow:hidden; flex:1;">
                <h4 style="font-size:13px; font-weight:700; color:var(--text-main); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${escapeHtml(u.original_name)}">${escapeHtml(u.original_name)}</h4>
                <div style="font-size:11px; color:var(--text-muted); font-family:var(--font-mono); margin-top:2px;">${u.size_mb} MB · ${u.formatted_date || ''}</div>
              </div>
            </div>
          </div>
          <div style="display:flex; align-items:center; justify-content:space-between; gap:8px; border-top:1px solid var(--border-light); padding-top:10px;">
            <button class="btn-channel-danger btn-delete-upload" style="padding:6px 10px; font-size:11px;" title="Delete file from disk"><i class="ri-delete-bin-line"></i></button>
            <button class="btn-primary-gradient btn-select-upload" style="padding:6px 16px; font-size:12px; font-weight:600; flex:1;"><i class="ri-sparkling-fill"></i> Select & Clip →</button>
          </div>
        `;

        card.querySelector('.btn-select-upload')?.addEventListener('click', () => {
          document.getElementById('modal-recent-uploads')?.classList.add('hidden');
          openCaptionStudio(u.filename, false, true, false);
        });

        card.querySelector('.btn-delete-upload')?.addEventListener('click', async (e) => {
          e.stopPropagation();
          if (!confirm(`Delete "${u.original_name}" from disk?`)) return;
          try {
            await fetch(`/api/uploads/${encodeURIComponent(u.filename)}`, { method: 'DELETE' });
            Toast.show(`Deleted ${u.original_name}`, 'info');
            fetchRecentUploads();
          } catch(err) {
            Toast.show('Failed to delete file', 'error');
          }
        });

        grid.appendChild(card);
      });
    } catch(err) {
      console.error('Failed to load recent uploads:', err);
      grid.innerHTML = '<div style="grid-column: 1/-1; text-align:center; padding:30px; color:var(--rose-text);">Failed to load media library.</div>';
    }
  }

  // Settings Modal & Caption Studio Architecture
  const configCaptionStyle = document.getElementById('config-caption-style');
  const savedCaptionStyle = localStorage.getItem('captionStyle') || 'aftereffect_preset';
  if (configCaptionStyle) {
    configCaptionStyle.value = savedCaptionStyle;
    configCaptionStyle.addEventListener('change', (e) => {
      localStorage.setItem('captionStyle', e.target.value);
      renderCaptionStudioGrid();
    });
  }

  const configModel = document.getElementById('config-model');
  const savedModel = localStorage.getItem('cliphub_model') || 'small';
  if (configModel) {
    configModel.value = savedModel;
    configModel.addEventListener('change', (e) => {
      localStorage.setItem('cliphub_model', e.target.value);
    });
  }

  const configCommentaryMode = document.getElementById('config-commentary-mode');
  const savedCommentaryMode = localStorage.getItem('cliphub_commentary_mode') || 'hook_commentary';
  if (configCommentaryMode) {
    configCommentaryMode.value = savedCommentaryMode;
    configCommentaryMode.addEventListener('change', (e) => {
      localStorage.setItem('cliphub_commentary_mode', e.target.value);
    });
  }

  const configCommentaryVoice = document.getElementById('config-commentary-voice');
  const savedCommentaryVoice = localStorage.getItem('cliphub_commentary_voice') || 'af_sarah';
  if (configCommentaryVoice) {
    configCommentaryVoice.value = savedCommentaryVoice;
    configCommentaryVoice.addEventListener('change', (e) => {
      localStorage.setItem('cliphub_commentary_voice', e.target.value);
    });
  }

  // ─── Character Management Architecture ────────────────────────
  let availableCharacters = [];
  let stagedCharUploadFile = null;

  const configCharacterSelect = document.getElementById('config-character-select');
  if (configCharacterSelect) {
    configCharacterSelect.addEventListener('change', (e) => {
      localStorage.setItem('selectedCharacter', e.target.value);
      renderSettingsCharactersGrid();
      renderStudioCharactersGrid();
    });
  }

  async function loadCharacters() {
    try {
      const res = await fetch('/api/characters');
      const data = await res.json();
      if (data && Array.isArray(data.characters)) {
        availableCharacters = data.characters;
        renderCharacterSelectDropdown();
        renderSettingsCharactersGrid();
        renderStudioCharactersGrid();
      }
    } catch (e) {
      console.error("[Characters] Failed to load characters:", e);
    }
  }

  function renderCharacterSelectDropdown() {
    if (!configCharacterSelect) return;
    const current = localStorage.getItem('selectedCharacter') || 'anime_presenter.png';
    configCharacterSelect.innerHTML = '';
    availableCharacters.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = c.name + (c.is_builtin ? ' (Built-in)' : '');
      if (c.id === current) opt.selected = true;
      configCharacterSelect.appendChild(opt);
    });
  }

  function createCharacterCard(c, isSelected, inStudio = false) {
    const card = document.createElement('div');
    card.className = `character-card ${isSelected ? 'selected' : ''}`;
    card.setAttribute('data-char-id', c.id);

    const badgeText = c.is_builtin ? 'Built-in' : 'Custom';
    const isCustom = !c.is_builtin;

    card.innerHTML = `
      ${isCustom && !inStudio ? `<button type="button" class="character-delete-btn" title="Delete Character" data-delete-id="${c.id}"><i class="ri-delete-bin-line"></i></button>` : ''}
      <div class="character-card-img-wrap">
        <img src="${c.url}" class="character-card-img" alt="${c.name}">
      </div>
      <div class="character-card-name" title="${c.name}">${c.name}</div>
      <div style="display:flex; align-items:center; justify-content:space-between; width:100%; margin-top:4px;">
        <span class="character-card-badge">${badgeText}</span>
        <span class="char-check" style="font-size:12px; font-weight:800; color:${isSelected ? '#818cf8' : 'transparent'};">✓</span>
      </div>
    `;

    if (isCustom && !inStudio) {
      const delBtn = card.querySelector('.character-delete-btn');
      if (delBtn) {
        delBtn.addEventListener('click', async (e) => {
          e.stopPropagation();
          if (confirm(`Are you sure you want to delete character "${c.name}"?`)) {
            try {
              const res = await fetch(`/api/characters/${encodeURIComponent(c.id)}`, { method: 'DELETE' });
              const resData = await res.json();
              if (resData.success) {
                Toast.show(`Character "${c.name}" deleted.`, "info");
                if (localStorage.getItem('selectedCharacter') === c.id) {
                  localStorage.setItem('selectedCharacter', 'anime_presenter.png');
                }
                await loadCharacters();
              } else {
                Toast.show(resData.error || "Failed to delete", "error");
              }
            } catch (err) {
              Toast.show("Delete error: " + err.message, "error");
            }
          }
        });
      }
    }

    card.addEventListener('click', () => {
      localStorage.setItem('selectedCharacter', c.id);
      if (configCharacterSelect) configCharacterSelect.value = c.id;
      renderSettingsCharactersGrid();
      renderStudioCharactersGrid();
      Toast.show(`Presenter: ${c.name}`, "info");
    });

    return card;
  }

  function renderSettingsCharactersGrid() {
    const grid = document.getElementById('settings-characters-grid');
    if (!grid) return;
    grid.innerHTML = '';
    const selected = localStorage.getItem('selectedCharacter') || 'anime_presenter.png';

    availableCharacters.forEach(c => {
      grid.appendChild(createCharacterCard(c, c.id === selected, false));
    });

    const addCard = document.createElement('div');
    addCard.className = 'character-add-card';
    addCard.innerHTML = `
      <i class="ri-user-add-line" style="font-size:24px; color:var(--brand-purple);"></i>
      <span style="font-size:12px; font-weight:600; color:var(--text-main);">Upload Character</span>
      <small style="font-size:10px; color:var(--text-muted);">PNG, JPG, WEBP</small>
    `;
    addCard.addEventListener('click', () => openCharacterUploadModal());
    grid.appendChild(addCard);
  }

  function renderStudioCharactersGrid() {
    const grid = document.getElementById('studio-characters-grid');
    if (!grid) return;
    grid.innerHTML = '';
    const selected = localStorage.getItem('selectedCharacter') || 'anime_presenter.png';

    availableCharacters.forEach(c => {
      grid.appendChild(createCharacterCard(c, c.id === selected, true));
    });

    const addCard = document.createElement('div');
    addCard.className = 'character-add-card';
    addCard.innerHTML = `
      <i class="ri-user-add-line" style="font-size:22px; color:var(--brand-purple);"></i>
      <span style="font-size:11.5px; font-weight:600; color:var(--text-main);">+ Add Character</span>
      <small style="font-size:10px; color:var(--text-muted);">Upload cutout</small>
    `;
    addCard.addEventListener('click', () => openCharacterUploadModal());
    grid.appendChild(addCard);
  }

  // Upload Character Modal Controls
  const modalUploadChar = document.getElementById('modal-upload-character');
  const modalCharFileInput = document.getElementById('modal-char-file-input');
  const modalCharNameInput = document.getElementById('modal-char-name-input');
  const charUploadPreviewBox = document.getElementById('char-upload-preview-box');
  const charUploadPreviewImg = document.getElementById('char-upload-preview-img');
  const charUploadPlaceholder = document.getElementById('char-upload-placeholder');
  const btnConfirmCharUpload = document.getElementById('btn-confirm-char-upload');
  const btnCancelCharUpload = document.getElementById('btn-cancel-char-upload');
  const btnCloseUploadCharModal = document.getElementById('btn-close-upload-char-modal');

  function openCharacterUploadModal() {
    stagedCharUploadFile = null;
    if (modalCharFileInput) modalCharFileInput.value = '';
    if (modalCharNameInput) modalCharNameInput.value = '';
    if (charUploadPreviewImg) {
      charUploadPreviewImg.src = '';
      charUploadPreviewImg.classList.add('hidden');
    }
    if (charUploadPlaceholder) charUploadPlaceholder.classList.remove('hidden');
    if (btnConfirmCharUpload) {
      btnConfirmCharUpload.disabled = true;
      btnConfirmCharUpload.innerHTML = `<i class="ri-check-line"></i> Save Character`;
    }
    if (modalUploadChar) modalUploadChar.classList.remove('hidden');
  }

  function closeCharacterUploadModal() {
    if (modalUploadChar) modalUploadChar.classList.add('hidden');
  }

  btnCancelCharUpload?.addEventListener('click', closeCharacterUploadModal);
  btnCloseUploadCharModal?.addEventListener('click', closeCharacterUploadModal);
  document.getElementById('btn-upload-character-settings')?.addEventListener('click', openCharacterUploadModal);
  document.getElementById('btn-upload-character-studio')?.addEventListener('click', openCharacterUploadModal);

  charUploadPreviewBox?.addEventListener('click', () => {
    modalCharFileInput?.click();
  });

  modalCharFileInput?.addEventListener('change', (e) => {
    if (e.target.files.length) {
      stagedCharUploadFile = e.target.files[0];
      const reader = new FileReader();
      reader.onload = (re) => {
        if (charUploadPreviewImg) {
          charUploadPreviewImg.src = re.target.result;
          charUploadPreviewImg.classList.remove('hidden');
        }
        if (charUploadPlaceholder) charUploadPlaceholder.classList.add('hidden');
      };
      reader.readAsDataURL(stagedCharUploadFile);

      if (modalCharNameInput && !modalCharNameInput.value.trim()) {
        const rawName = stagedCharUploadFile.name.replace(/\.[^/.]+$/, "").replace(/[-_]/g, " ");
        modalCharNameInput.value = rawName.split(" ").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
      }
      if (btnConfirmCharUpload) btnConfirmCharUpload.disabled = false;
    }
  });

  btnConfirmCharUpload?.addEventListener('click', async () => {
    if (!stagedCharUploadFile) {
      Toast.show("Please select a character image first.", "error");
      return;
    }
    const charName = modalCharNameInput?.value?.trim() || "";
    btnConfirmCharUpload.disabled = true;
    btnConfirmCharUpload.innerHTML = `<i class="ri-loader-4-line spin"></i> Saving...`;

    try {
      const fd = new FormData();
      fd.append('file', stagedCharUploadFile);
      if (charName) fd.append('name', charName);

      const res = await fetch('/api/characters/upload', {
        method: 'POST',
        body: fd
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.detail || data.error || "Failed to upload character");
      }

      Toast.show(`Character "${data.character.name}" saved!`, "success");
      localStorage.setItem('selectedCharacter', data.character.id);
      closeCharacterUploadModal();
      await loadCharacters();
    } catch (err) {
      Toast.show("Upload failed: " + err.message, "error");
      btnConfirmCharUpload.disabled = false;
      btnConfirmCharUpload.innerHTML = `<i class="ri-check-line"></i> Save Character`;
    }
  });

  // ─── Cover Thumbnail Management Architecture ──────────────────
  let availableCovers = [];
  let stagedCoverUploadFile = null;

  const configCoverSelect = document.getElementById('config-cover-select');
  if (configCoverSelect) {
    configCoverSelect.addEventListener('change', (e) => {
      localStorage.setItem('selectedCover', e.target.value);
      renderSettingsCoversGrid();
      renderStudioCoversGrid();
    });
  }

  async function loadCovers() {
    try {
      const res = await fetch('/api/covers');
      const data = await res.json();
      if (data && Array.isArray(data.covers)) {
        availableCovers = data.covers;
        renderCoverSelectDropdown();
        renderSettingsCoversGrid();
        renderStudioCoversGrid();
      }
    } catch (e) {
      console.error("[Covers] Failed to load covers:", e);
    }
  }

  function renderCoverSelectDropdown() {
    if (!configCoverSelect) return;
    const current = localStorage.getItem('selectedCover') || 'default_cover.jpg';
    configCoverSelect.innerHTML = '';
    availableCovers.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = c.name + (c.is_none ? ' (No Universal)' : (c.is_builtin ? ' (Built-in)' : ''));
      if (c.id === current) opt.selected = true;
      configCoverSelect.appendChild(opt);
    });
  }

  function createCoverCard(c, isSelected, inStudio = false) {
    const card = document.createElement('div');
    card.className = `cover-card ${isSelected ? 'selected' : ''}`;
    card.setAttribute('data-cover-id', c.id);

    const isNone = c.id === 'none' || c.is_none;
    const badgeText = isNone ? 'Video Frame' : (c.is_builtin ? 'Built-in' : 'Custom');
    const isCustom = !c.is_builtin && !isNone;

    const imgBlock = isNone ? `
      <div class="cover-card-img-wrap">
        <div class="cover-none-icon-box">
          <i class="ri-movie-line" style="font-size:26px; color:#f59e0b;"></i>
          <span style="font-size:10px; color:var(--text-muted); font-weight:600;">Frame 0.0s</span>
        </div>
      </div>
    ` : `
      <div class="cover-card-img-wrap">
        <img src="${c.url}" class="cover-card-img" alt="${c.name}">
      </div>
    `;

    card.innerHTML = `
      ${isCustom && !inStudio ? `<button type="button" class="cover-delete-btn" title="Delete Cover" data-delete-id="${c.id}"><i class="ri-delete-bin-line"></i></button>` : ''}
      ${imgBlock}
      <div class="cover-card-name" title="${c.name}">${c.name}</div>
      <div style="display:flex; align-items:center; justify-content:space-between; width:100%; margin-top:4px;">
        <span class="cover-card-badge">${badgeText}</span>
        <span class="cover-check" style="font-size:12px; font-weight:800; color:${isSelected ? '#f59e0b' : 'transparent'};">✓</span>
      </div>
    `;

    if (isCustom && !inStudio) {
      const delBtn = card.querySelector('.cover-delete-btn');
      if (delBtn) {
        delBtn.addEventListener('click', async (e) => {
          e.stopPropagation();
          if (confirm(`Are you sure you want to delete cover "${c.name}"?`)) {
            try {
              const res = await fetch(`/api/covers/${encodeURIComponent(c.id)}`, { method: 'DELETE' });
              const resData = await res.json();
              if (resData.success) {
                Toast.show(`Cover "${c.name}" deleted.`, "info");
                if (localStorage.getItem('selectedCover') === c.id) {
                  localStorage.setItem('selectedCover', 'default_cover.jpg');
                }
                await loadCovers();
              } else {
                Toast.show(resData.error || "Failed to delete", "error");
              }
            } catch (err) {
              Toast.show("Delete error: " + err.message, "error");
            }
          }
        });
      }
    }

    card.addEventListener('click', () => {
      localStorage.setItem('selectedCover', c.id);
      if (configCoverSelect) configCoverSelect.value = c.id;
      renderSettingsCoversGrid();
      renderStudioCoversGrid();
      Toast.show(isNone ? "Cover set to Video Frame (No Universal)" : `Cover: ${c.name}`, "info");
    });

    return card;
  }

  function renderSettingsCoversGrid() {
    const grid = document.getElementById('settings-covers-grid');
    if (!grid) return;
    grid.innerHTML = '';
    const selected = localStorage.getItem('selectedCover') || 'default_cover.jpg';

    availableCovers.forEach(c => {
      grid.appendChild(createCoverCard(c, c.id === selected, false));
    });

    const addCard = document.createElement('div');
    addCard.className = 'cover-add-card';
    addCard.innerHTML = `
      <i class="ri-image-add-line" style="font-size:24px; color:#f59e0b;"></i>
      <span style="font-size:12px; font-weight:600; color:var(--text-main);">Upload Cover</span>
      <small style="font-size:10px; color:var(--text-muted);">JPG, PNG, WEBP</small>
    `;
    addCard.addEventListener('click', () => openCoverUploadModal());
    grid.appendChild(addCard);
  }

  function renderStudioCoversGrid() {
    const grid = document.getElementById('studio-covers-grid');
    if (!grid) return;
    grid.innerHTML = '';
    const selected = localStorage.getItem('selectedCover') || 'default_cover.jpg';

    availableCovers.forEach(c => {
      grid.appendChild(createCoverCard(c, c.id === selected, true));
    });

    const addCard = document.createElement('div');
    addCard.className = 'cover-add-card';
    addCard.innerHTML = `
      <i class="ri-image-add-line" style="font-size:22px; color:#f59e0b;"></i>
      <span style="font-size:11.5px; font-weight:600; color:var(--text-main);">+ Add Cover</span>
      <small style="font-size:10px; color:var(--text-muted);">Upload Image</small>
    `;
    addCard.addEventListener('click', () => openCoverUploadModal());
    grid.appendChild(addCard);
  }

  // Upload Cover Modal Controls
  const modalUploadCover = document.getElementById('modal-upload-cover');
  const modalCoverFileInput = document.getElementById('modal-cover-file-input');
  const modalCoverNameInput = document.getElementById('modal-cover-name-input');
  const coverUploadPreviewBox = document.getElementById('cover-upload-preview-box');
  const coverUploadPreviewImg = document.getElementById('cover-upload-preview-img');
  const coverUploadPlaceholder = document.getElementById('cover-upload-placeholder');
  const btnConfirmCoverUpload = document.getElementById('btn-confirm-cover-upload');
  const btnCancelCoverUpload = document.getElementById('btn-cancel-cover-upload');
  const btnCloseUploadCoverModal = document.getElementById('btn-close-upload-cover-modal');

  function openCoverUploadModal() {
    stagedCoverUploadFile = null;
    if (modalCoverFileInput) modalCoverFileInput.value = '';
    if (modalCoverNameInput) modalCoverNameInput.value = '';
    if (coverUploadPreviewImg) {
      coverUploadPreviewImg.src = '';
      coverUploadPreviewImg.classList.add('hidden');
    }
    if (coverUploadPlaceholder) coverUploadPlaceholder.classList.remove('hidden');
    if (btnConfirmCoverUpload) {
      btnConfirmCoverUpload.disabled = true;
      btnConfirmCoverUpload.innerHTML = `<i class="ri-check-line"></i> Save Cover`;
    }
    if (modalUploadCover) modalUploadCover.classList.remove('hidden');
  }

  function closeCoverUploadModal() {
    if (modalUploadCover) modalUploadCover.classList.add('hidden');
  }

  btnCancelCoverUpload?.addEventListener('click', closeCoverUploadModal);
  btnCloseUploadCoverModal?.addEventListener('click', closeCoverUploadModal);
  document.getElementById('btn-upload-cover-settings')?.addEventListener('click', openCoverUploadModal);
  document.getElementById('btn-upload-cover-studio')?.addEventListener('click', openCoverUploadModal);

  coverUploadPreviewBox?.addEventListener('click', () => {
    modalCoverFileInput?.click();
  });

  modalCoverFileInput?.addEventListener('change', (e) => {
    if (e.target.files.length) {
      stagedCoverUploadFile = e.target.files[0];
      const reader = new FileReader();
      reader.onload = (re) => {
        if (coverUploadPreviewImg) {
          coverUploadPreviewImg.src = re.target.result;
          coverUploadPreviewImg.classList.remove('hidden');
        }
        if (coverUploadPlaceholder) coverUploadPlaceholder.classList.add('hidden');
      };
      reader.readAsDataURL(stagedCoverUploadFile);

      if (modalCoverNameInput && !modalCoverNameInput.value.trim()) {
        const rawName = stagedCoverUploadFile.name.replace(/\.[^/.]+$/, "").replace(/[-_]/g, " ");
        modalCoverNameInput.value = rawName.split(" ").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
      }
      if (btnConfirmCoverUpload) btnConfirmCoverUpload.disabled = false;
    }
  });

  btnConfirmCoverUpload?.addEventListener('click', async () => {
    if (!stagedCoverUploadFile) {
      Toast.show("Please select a cover image first.", "error");
      return;
    }
    const coverName = modalCoverNameInput?.value?.trim() || "";
    btnConfirmCoverUpload.disabled = true;
    btnConfirmCoverUpload.innerHTML = `<i class="ri-loader-4-line spin"></i> Saving...`;

    try {
      const fd = new FormData();
      fd.append('file', stagedCoverUploadFile);
      if (coverName) fd.append('name', coverName);

      const res = await fetch('/api/covers/upload', {
        method: 'POST',
        body: fd
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.detail || data.error || "Failed to upload cover");
      }

      Toast.show(`Cover "${data.cover.name}" saved!`, "success");
      localStorage.setItem('selectedCover', data.cover.id);
      closeCoverUploadModal();
      await loadCovers();
    } catch (err) {
      Toast.show("Upload failed: " + err.message, "error");
      btnConfirmCoverUpload.disabled = false;
      btnConfirmCoverUpload.innerHTML = `<i class="ri-check-line"></i> Save Cover`;
    }
  });

  let currentPendingJob = null;

  const VIP_CAPTION_STYLES_DATA = [
    {
      id: 'aftereffect_preset',
      name: 'Aftereffect preset',
      desc: 'Word-by-Word Rise & Fade In (Bricks AE Preset). Position Y: +80px → 0px with simultaneous alpha dissolve (0% → 100%) and Ease High 20% / Ease Low 100% curve. Zero bounce, pure silky motion.',
      badge: '⭐ VIP MASTER • AFTER EFFECTS',
      previewCss: '',
      isVip: true,
      html: `
        <div class="ae-preview-stage">
          <span class="ae-word-mask"><span class="ae-word ae-word-1">WORD</span></span>
          <span class="ae-word-mask"><span class="ae-word ae-word-2">BY</span></span>
          <span class="ae-word-mask"><span class="ae-word ae-word-3">WORD</span></span>
          <span class="ae-word-mask"><span class="ae-word ae-word-4 ae-highlight">REVEAL</span></span>
        </div>
      `
    }
  ];

  const STANDARD_CAPTION_STYLES_DATA = [
    { id: 'kinetic_slide', name: 'Kinetic Slide (Default)', desc: 'Smooth vertical slide with a punchy entry scale pop.', previewCss: 'color: #00FFFF; text-shadow: 0 2px 4px rgba(0,0,0,0.8); font-weight: 800;', badge: '★ Most Popular', html: '<span style="color: #fff; opacity: 0.5;">VIRAL</span> <span style="color: #00ffff; text-shadow: 2px 2px 0px #000; display: inline-block; transform: scale(1.1);">GROWTH</span>' },
    { id: 'hormozi_gold', name: 'Alex Hormozi Gold', desc: 'Signature warm gold text, heavy drop shadow, and explosive bounce.', previewCss: 'color: #FFD700; text-shadow: 0 3px 6px #000; font-weight: 900;', badge: '👑 Hormozi Style', html: '<span style="color: #fff; opacity: 0.4;">HOW TO</span> <span style="color: #FFD700; text-shadow: 3px 3px 0 #000; display: inline-block; transform: scale(1.25); font-weight: 900;">WIN</span> <span style="color: #fff; opacity: 0.4;">TODAY</span>' },
    { id: 'mrbeast_lightning', name: 'MrBeast Lightning', desc: 'Hyper-bright electric cyan with energetic tilt and thick outline.', previewCss: 'color: #00FFFF; font-weight: 900;', badge: '⚡ MrBeast Vibe', html: '<span style="color: #00FFFF; -webkit-text-stroke: 1px black; text-shadow: 3px 3px 0 #000; display: inline-block; transform: rotate(-5deg) scale(1.15); font-weight: 900;">INSANE!</span>' },
    { id: 'fire_ember', name: 'Fire Ember', desc: 'Hot fiery orange jumping words with a subtle ember glow.', previewCss: 'color: #FF5500; font-weight: 800;', badge: '🔥 Hot', html: '<span style="color: #ccc;">UNSTOPPABLE</span> <span style="color: #FF5500; text-shadow: 0 0 12px #FF5500; display: inline-block; transform: translateY(-3px) scale(1.1);">POWER</span>' },
    { id: 'emerald_money', name: 'Emerald Money Pop', desc: 'Vibrant emerald green designed for finance, business, and cash hooks.', previewCss: 'color: #00FF70; font-weight: 800;', badge: '💰 Business', html: '<span style="color: #ddd; opacity: 0.5;">EARN</span> <span style="color: #00FF70; text-shadow: 0 0 8px rgba(0,255,112,0.6); display: inline-block; transform: scale(1.2); font-weight: 800;">$10,000</span> <span style="color: #ddd; opacity: 0.5;">NOW</span>' },
    { id: 'glitch_matrix', name: 'Glitch Matrix Green', desc: 'Cyber hacker neon green with quick horizontal jitter & neon glow.', previewCss: 'color: #00FF00; font-family: monospace;', badge: '💻 Cyberpunk', html: '<span style="color: #00FF00; font-family: monospace; text-shadow: 0 0 10px #00FF00; letter-spacing: 2px;">HACK_SYSTEM</span>' },
    { id: 'neon_purple_rain', name: 'Neon Purple Rain', desc: 'Deep electric violet and magenta with smooth breathing zoom.', previewCss: 'color: #FF00AA; font-weight: 800;', badge: '🟣 Aesthetic', html: '<span style="color: #e0d0e0; opacity: 0.5;">DEEP</span> <span style="color: #FF00AA; text-shadow: 0 0 12px #FF00AA; display: inline-block; transform: scale(1.15);">VIBES</span>' },
    { id: 'bold_impact_red', name: 'Bold Impact Red', desc: 'Aggressive high-impact crime and drama style with zero background dimming.', previewCss: 'color: #FF0000; font-weight: 900;', badge: '🚨 High Impact', html: '<span style="color: #fff;">CRITICAL</span> <span style="color: #FF0000; text-shadow: 2px 2px 0 #000; display: inline-block; transform: scale(1.3); font-weight: 900;">ALERT</span>' },
    { id: 'sunset_vibes', name: 'Sunset Vibes Glow', desc: 'Warm sunset pink-orange tones with gentle floating animation.', previewCss: 'color: #FF9966; font-weight: 700;', badge: '🌅 Dreamy', html: '<span style="color: #FF9966; text-shadow: 0 2px 8px rgba(255,153,102,0.5); display: inline-block; transform: translateY(-4px);">GOLDEN HOUR</span>' },
    { id: 'pastel_dream', name: 'Pastel Dream', desc: 'Soft pastel lavender and mint elegance for lifestyle content.', previewCss: 'color: #E0B0FF; font-weight: 600;', badge: '🌸 Lifestyle', html: '<span style="color: #fff; opacity: 0.6;">soft &</span> <span style="color: #F0D0FF; text-shadow: 0 0 6px rgba(240,208,255,0.7); display: inline-block; transform: scale(1.08);">beautiful</span>' },
    { id: 'stomp_kinetic', name: 'Action Stomp Kinetic', desc: 'Hard-hitting slam from 200% down to 100% scale instantaneously.', previewCss: 'color: #00FFFF; font-weight: 900;', badge: '💥 Action Slam', html: '<span style="color: #b0b0b0; opacity: 0.5;">READY</span> <span style="color: #00FFFF; text-shadow: 4px 4px 0 #000; font-weight: 900; display: inline-block; transform: scale(1.4);">STOMP!</span>' },
    { id: 'tiktok_pop', name: 'TikTok Pop', desc: 'Classic fast word zoom pop with high contrast outline.', previewCss: 'color: #FFFF00; font-weight: 800;', badge: '📱 TikTok', html: '<span style="color: #fff;">CHECK</span> <span style="color: #ffff00; -webkit-text-stroke: 1px red; text-shadow: 2px 2px 0 #ff0000; display: inline-block; transform: scale(1.2);">THIS</span> <span style="color: #fff;">OUT</span>' },
    { id: 'cyberpunk_neon', name: 'Cyberpunk Neon', desc: 'Neon pink active word with semi-transparent cyan inactive words.', previewCss: 'color: #FF00FF; font-weight: 800;', badge: '🌃 Neon', html: '<span style="color: #00ffff; opacity: 0.5;">CYBER</span> <span style="color: #ff00ff; text-shadow: 0 0 10px #ff00ff; display: inline-block; transform: rotate(3deg) scale(1.15);">PUNK</span>' },
    { id: 'smooth_wave', name: 'Smooth Wave', desc: 'Smooth continuous karaoke highlight wiping across words.', previewCss: 'color: #00FFFF; font-weight: 700;', badge: '🌊 Karaoke', html: '<span style="color: #00ffff; text-shadow: 0 0 5px #00ffff;">SMOOTH</span> <span style="color: #ffffff; opacity: 0.3;">WIPE EFFECT</span>' },
    { id: 'vibrant_gradient', name: 'Vibrant Gradient', desc: 'Orange-to-yellow vibrant pop while inactive words fade to grey.', previewCss: 'color: #FFA500; font-weight: 800;', badge: '🎨 Gradient', html: '<span style="color: #808080;">PURE</span> <span style="color: #FFB800; text-shadow: 0 2px 6px rgba(255,184,0,0.6); display: inline-block; transform: scale(1.15);">VIBRANCE</span>' },
    { id: 'cinematic_swing', name: 'Cinematic Swing', desc: 'Elegant swing-in tilt rotation with soft dimmed backdrop.', previewCss: 'color: #FFFF00; font-weight: 700;', badge: '🎬 Movie', html: '<span style="color: #ffff00; display: inline-block; transform: rotate(4deg) scale(1.1);">CINEMATIC</span>' },
    { id: 'karaoke_glow', name: 'Karaoke Glow', desc: 'Glowing neon yellow outline with soft background blur.', previewCss: 'color: #FFFF00; font-weight: 800;', badge: '✨ Glowing', html: '<span style="color: #FFFF00; text-shadow: 0 0 12px #FFFF00; display: inline-block; transform: scale(1.1);">GLOWING</span>' },
    { id: 'minimal_fade', name: 'Minimal Fade', desc: 'High-end minimalist clean design with pure opacity transitions.', previewCss: 'color: #FFFFFF; font-weight: 600;', badge: '🤍 Minimalist', html: '<span style="color: #ffffff; font-weight: 700;">CLEAN</span> <span style="color: #ffffff; opacity: 0.3;">FADE</span>' },
    { id: 'future_cyber', name: 'Future Cyber', desc: 'Active cyan glow outline with bright yellow fill and swift scale.', previewCss: 'color: #00FFCC; font-weight: 800;', badge: '🛸 Sci-Fi', html: '<span style="color: #FFFF00; text-shadow: 0 0 8px #00FF00; display: inline-block; transform: scale(1.2);">FUTURE</span>' }
  ];

  const CAPTION_STYLES_DATA = [...VIP_CAPTION_STYLES_DATA, ...STANDARD_CAPTION_STYLES_DATA];

  function createCaptionCardElement(st, selected) {
    const isSelected = st.id === selected;
    const isVip = !!st.isVip;
    const card = document.createElement('div');
    card.className = `caption-card ${isVip ? 'vip-card' : ''} ${isSelected ? 'selected' : ''}`;
    card.setAttribute('data-style', st.id);
    
    if (isVip) {
      card.style.cssText = `
        border-radius: 14px; padding: 22px; cursor: pointer; transition: all 0.25s ease;
        display: flex; flex-direction: column; justify-content: space-between; position: relative;
      `;
    } else {
      card.style.cssText = `
        background: rgba(20, 20, 28, 0.85); border: ${isSelected ? '2px solid var(--accent-cyan)' : '1px solid var(--border-color)'};
        border-radius: 12px; padding: 20px; cursor: pointer; transition: all 0.25s ease;
        box-shadow: ${isSelected ? '0 0 25px rgba(0, 240, 255, 0.3)' : 'none'};
        display: flex; flex-direction: column; justify-content: space-between; position: relative;
      `;
    }

    const checkBorderColor = isVip ? '#FFD700' : 'var(--accent-cyan)';
    const checkBgColor = isVip ? '#FFD700' : 'var(--accent-cyan)';
    const badgeHtml = isVip ? `<span class="vip-badge-pill"><i class="ri-vip-crown-2-fill"></i> ${st.badge}</span>` : `<span style="font-size: 0.75rem; background: rgba(255,255,255,0.08); padding: 4px 10px; border-radius: 20px; color: var(--accent-cyan); font-weight: 600;">${st.badge}</span>`;

    card.innerHTML = `
      ${isVip ? '<div class="vip-glow-mesh"></div>' : ''}
      <div>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
          ${badgeHtml}
          <div class="radio-check" style="width: 22px; height: 22px; border-radius: 50%; border: 2px solid ${isSelected ? checkBorderColor : 'var(--text-muted)'}; background: ${isSelected ? checkBgColor : 'transparent'}; display: flex; align-items: center; justify-content: center; color: #000; font-size: 0.85rem; font-weight: 900;">
            ${isSelected ? '✓' : ''}
          </div>
        </div>
        <h4 style="color: ${isVip ? '#fff' : 'var(--text-main)'}; font-size: 1.2rem; margin-bottom: 8px; font-weight: 800; display: flex; align-items: center; gap: 6px;">
          ${st.name} ${isVip ? '<i class="ri-sparkling-fill" style="color: #FFD700; font-size: 1rem;"></i>' : ''}
        </h4>
        <p style="color: ${isVip ? '#cbd5e1' : 'var(--text-muted)'}; font-size: 0.86rem; line-height: 1.45; margin-bottom: 16px;">${st.desc}</p>
      </div>
      <div style="background: ${isVip ? 'rgba(0,0,0,0.75)' : 'rgba(0,0,0,0.6)'}; border: ${isVip ? '1px solid rgba(255,215,0,0.35)' : '1px dashed rgba(255,255,255,0.15)'}; padding: 18px 10px; border-radius: 10px; text-align: center; overflow: hidden; box-shadow: ${isVip ? 'inset 0 0 15px rgba(0,0,0,0.6)' : 'none'};">
        <div style="${st.previewCss || ''}">
          ${st.html}
        </div>
      </div>
    `;

    card.addEventListener('click', () => {
      localStorage.setItem('captionStyle', st.id);
      const cfg = document.getElementById('config-caption-style');
      if (cfg) cfg.value = st.id;
      renderCaptionStudioGrid();
      
      const btnText = document.getElementById('btn-proceed-modal-text');
      if (btnText && (!currentPendingJob || !currentPendingJob.isStandaloneTool)) {
        btnText.textContent = `Generate Clips (${st.name})`;
      }
    });

    return card;
  }

  function renderCaptionStudioGrid() {
    const vipGrid = document.getElementById('vip-caption-styles-grid');
    const stdGrid = document.getElementById('caption-styles-grid');
    if (!stdGrid) return;
    
    const selected = localStorage.getItem('captionStyle') || 'aftereffect_preset';

    if (vipGrid) {
      vipGrid.innerHTML = '';
      VIP_CAPTION_STYLES_DATA.forEach(st => {
        vipGrid.appendChild(createCaptionCardElement(st, selected));
      });
    }

    stdGrid.innerHTML = '';
    STANDARD_CAPTION_STYLES_DATA.forEach(st => {
      stdGrid.appendChild(createCaptionCardElement(st, selected));
    });
  }

  function openCaptionStudio(source, isYoutube = false, isExistingUpload = false, isStandaloneTool = false) {
    currentPendingJob = { source, isYoutube, isExistingUpload, isStandaloneTool };
    renderCaptionStudioGrid();

    const modal = document.getElementById('modal-caption-studio');
    if (!modal) return;
    
    document.getElementById('caption-studio-main')?.classList.remove('hidden');
    document.getElementById('standalone-caption-loading')?.classList.add('hidden');
    document.getElementById('standalone-caption-result')?.classList.add('hidden');

    const charSection = document.getElementById('character-studio-section');
    const coverSection = document.getElementById('cover-studio-section');
    const btnText = document.getElementById('btn-proceed-modal-text');
    if (isStandaloneTool) {
      if (charSection) charSection.classList.add('hidden');
      if (coverSection) coverSection.classList.add('hidden');
      document.getElementById('caption-studio-title').innerHTML = `Add Viral Captions: <span style="color:var(--brand-purple);">Choose Style</span>`;
      document.getElementById('caption-studio-subtitle').textContent = `Select the animation style to burn onto your uploaded clip!`;
      if (btnText) btnText.textContent = `Burn Captions Onto Video`;
    } else {
      if (charSection) charSection.classList.remove('hidden');
      if (coverSection) coverSection.classList.remove('hidden');
      renderStudioCharactersGrid();
      renderStudioCoversGrid();
      document.getElementById('caption-studio-title').innerHTML = `Step 2: Choose <span style="color:var(--brand-purple);">Presenter, Cover & Style</span>`;
      document.getElementById('caption-studio-subtitle').textContent = `Select your AI presenter, universal cover thumbnail, and motion typography preset below.`;
      const curStyle = localStorage.getItem('captionStyle') || 'aftereffect_preset';
      const curObj = CAPTION_STYLES_DATA.find(s => s.id === curStyle);
      const name = curObj ? curObj.name : 'Selected Style';
      if (btnText) btnText.textContent = `Generate Clips (${name})`;
    }

    modal.classList.remove('hidden');
  }

  document.getElementById('btn-caption-studio-close')?.addEventListener('click', () => {
    document.getElementById('modal-caption-studio')?.classList.add('hidden');
  });

  const btnAddCaptionsTool = document.getElementById('btn-add-captions-tool');
  const standaloneCaptionFile = document.getElementById('standalone-caption-file');
  if (btnAddCaptionsTool && standaloneCaptionFile) {
    btnAddCaptionsTool.addEventListener('click', () => standaloneCaptionFile.click());
    standaloneCaptionFile.addEventListener('change', (e) => {
      if (e.target.files.length) openCaptionStudio(e.target.files[0], false, false, true);
    });
  }

  const btnStudioBack = document.getElementById('btn-caption-studio-back');
  const btnStudioProceed = document.getElementById('btn-caption-studio-proceed');
  if (btnStudioBack) {
    btnStudioBack.addEventListener('click', () => {
      document.getElementById('modal-caption-studio')?.classList.add('hidden');
    });
  }
  if (btnStudioProceed) {
    btnStudioProceed.addEventListener('click', async () => {
      // Fallback: If currentPendingJob was not set, derive from stagedFile or yt-link-input
      if (!currentPendingJob) {
        const ytInput = document.getElementById('yt-link-input')?.value?.trim();
        if (stagedFile) {
          currentPendingJob = { source: stagedFile, isYoutube: false, isExistingUpload: false, isStandaloneTool: false };
        } else if (ytInput) {
          currentPendingJob = { source: ytInput, isYoutube: true, isExistingUpload: false, isStandaloneTool: false };
        } else {
          Toast.show("Please select a video file or enter a YouTube link first.", "info");
          document.getElementById('modal-caption-studio')?.classList.add('hidden');
          return;
        }
      }

      if (currentPendingJob.isStandaloneTool) {
        document.getElementById('caption-studio-main')?.classList.add('hidden');
        document.getElementById('standalone-caption-loading')?.classList.remove('hidden');

        const formData = new FormData();
        formData.append('file', currentPendingJob.source);
        formData.append('style', localStorage.getItem('captionStyle') || 'kinetic_slide');

        try {
          const res = await fetch('/api/tools/add-captions', {
            method: 'POST',
            body: formData
          });
          const data = await res.json();
          if (!data.success) {
            Toast.show("Error adding captions: " + (data.error || "Unknown error"), "error");
            document.getElementById('standalone-caption-loading')?.classList.add('hidden');
            document.getElementById('caption-studio-main')?.classList.remove('hidden');
            return;
          }
          document.getElementById('standalone-caption-loading')?.classList.add('hidden');
          document.getElementById('standalone-caption-result')?.classList.remove('hidden');
          const player = document.getElementById('standalone-caption-video-player');
          if (player) player.src = data.video_url;
          const dl = document.getElementById('btn-download-captioned');
          if (dl) dl.href = data.video_url;
        } catch (e) {
          Toast.show("Network or system error: " + e.message, "error");
          document.getElementById('standalone-caption-loading')?.classList.add('hidden');
          document.getElementById('caption-studio-main')?.classList.remove('hidden');
        }
      } else {
        const jobToStart = { ...currentPendingJob };
        document.getElementById('modal-caption-studio')?.classList.add('hidden');
        startProcessing(jobToStart.source, jobToStart.isYoutube, jobToStart.isExistingUpload);
      }
    });
  }
  const btnStudioDone = document.getElementById('btn-caption-studio-done');
  if (btnStudioDone) {
    btnStudioDone.addEventListener('click', () => {
      if (standaloneCaptionFile) standaloneCaptionFile.click();
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

  const amazonStoreTag = document.getElementById('amazon-store-tag');
  if (amazonStoreTag) {
    amazonStoreTag.value = localStorage.getItem('amazonStoreTag') || '';
    amazonStoreTag.addEventListener('input', (e) => {
      localStorage.setItem('amazonStoreTag', e.target.value.trim());
    });
  }

  const optYtComment = document.getElementById('opt-yt-comment');
  if (optYtComment) {
    const savedYtComment = localStorage.getItem('ytCommentEnabled');
    optYtComment.checked = savedYtComment !== 'false'; // Default true
    optYtComment.addEventListener('change', (e) => {
      localStorage.setItem('ytCommentEnabled', e.target.checked);
    });
  }

  const optYtShopping = document.getElementById('opt-yt-shopping');
  if (optYtShopping) {
    const savedYtShopping = localStorage.getItem('ytShoppingEnabled');
    optYtShopping.checked = savedYtShopping === 'true'; // Default false since requires YPP
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
    if (typeof gsap !== 'undefined') {
      try { gsap.fromTo(".modal", { scale: 0.98, opacity: 0, y: 10 }, { scale: 1, opacity: 1, y: 0, duration: 0.2, ease: "power2.out" }); } catch(e){}
    }
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
    const igBadge = document.getElementById('ig-status-badge');
    const igButton = document.getElementById('btn-connect-ig');
    const ytStatus = document.getElementById('yt-status-text');
    const ytBadge = document.getElementById('yt-status-badge');
    const ytButton = document.getElementById('btn-connect-yt');
    const overviewPill = document.getElementById('social-overview-pill');

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

      let connectedCount = 0;

      if (igStatus) {
        if (data.instagram_connected) {
          connectedCount++;
          const queueText = (waiting || uploading || completed) ? ` (Queue: ${waiting} pending, ${completed} published)` : '';
          const userStr = data.instagram_username ? `@${data.instagram_username.replace('@', '')}` : 'Active Session';
          igStatus.textContent = `Connected: ${userStr}${queueText}`;
          if (igBadge) igBadge.classList.add('connected');
          if (igButton) igButton.innerHTML = '<i class="ri-refresh-line"></i> <span>Reconnect Instagram</span>';
        } else {
          igStatus.textContent = 'Not connected';
          if (igBadge) igBadge.classList.remove('connected');
          if (igButton) igButton.innerHTML = '<i class="ri-instagram-line"></i> <span>Connect Instagram</span>';
        }
      }

      if (ytStatus) {
        const ytTitle = document.getElementById('yt-channel-title');
        const ytSwitch = document.getElementById('btn-switch-yt');
        const ytDisconnect = document.getElementById('btn-disconnect-yt');
        if (data.youtube_connected) {
          connectedCount++;
          const channel = data.youtube_channel || {};
          const channelName = channel.name || 'Active Session';
          const handle = channel.handle ? ` (${channel.handle})` : '';
          if (ytTitle) ytTitle.textContent = channelName;
          ytStatus.textContent = `Connected: ${channelName}${handle}`;
          if (ytBadge) ytBadge.classList.add('connected');
          if (ytButton) ytButton.innerHTML = '<i class="ri-refresh-line"></i> <span>Reconnect YouTube</span>';
          if (ytSwitch) ytSwitch.classList.remove('hidden');
          if (ytDisconnect) ytDisconnect.classList.remove('hidden');
        } else {
          if (ytTitle) ytTitle.textContent = 'YouTube Studio';
          ytStatus.textContent = 'Not connected';
          if (ytBadge) ytBadge.classList.remove('connected');
          if (ytButton) ytButton.innerHTML = '<i class="ri-youtube-line"></i> <span>Connect YouTube</span>';
          if (ytSwitch) ytSwitch.classList.add('hidden');
          if (ytDisconnect) ytDisconnect.classList.add('hidden');
        }
      }

      if (overviewPill) {
        overviewPill.textContent = `${connectedCount} / 2 Connected`;
      }
    } catch (_) {
      if (igStatus) igStatus.textContent = 'Status unavailable';
      if (ytStatus) ytStatus.textContent = 'Status unavailable';
    }
  }

  async function loadServerInfo() {
    try {
      const res = await fetch('/api/server-info');
      const data = await res.json();
      const wifiEl = document.getElementById('wifi-server-info');
      if (wifiEl && data.wifi_url) {
        wifiEl.innerHTML = `Open on your phone: <a href="${data.wifi_url}" target="_blank" style="color:#818cf8; font-weight:700; text-decoration:none;">${data.wifi_url}</a>`;
      }
    } catch (_) {}
  }
  loadServerInfo();

  document.getElementById('btn-connect-ig')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    button.innerHTML = '<i class="ri-loader-4-line spin"></i> <span>Connecting...</span>';
    try {
      const response = await fetch('/api/social/instagram/connect-playwright', { method: 'POST' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Instagram login failed');
      Toast.show("Instagram session saved successfully!", "success");
    } catch (error) {
      Toast.show("Instagram connection error: " + error.message, "error");
    } finally {
      button.disabled = false;
      await refreshSocialStatus();
    }
  });

  document.getElementById('btn-connect-yt')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    button.innerHTML = '<i class="ri-loader-4-line spin"></i> <span>Connecting...</span>';
    try {
      const response = await fetch('/api/social/youtube/connect-playwright', { method: 'POST' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'YouTube login failed');
      Toast.show("YouTube Studio connected successfully!", "success");
    } catch (error) {
      Toast.show("YouTube connection error: " + error.message, "error");
    } finally {
      button.disabled = false;
      await refreshSocialStatus();
    }
  });

  document.getElementById('btn-disconnect-yt')?.addEventListener('click', async (event) => {
    if (!confirm('Disconnect YouTube? You will need to log in again to publish videos.')) return;
    const button = event.currentTarget;
    button.disabled = true;
    button.innerHTML = '<i class="ri-loader-4-line spin"></i> <span>Disconnecting...</span>';
    try {
      await fetch('/api/social/youtube/disconnect', { method: 'POST' });
      Toast.show("YouTube disconnected", "info");
    } catch (error) {
      console.error('Disconnect failed:', error);
    } finally {
      button.disabled = false;
      await refreshSocialStatus();
    }
  });

  document.getElementById('btn-switch-yt')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    button.innerHTML = '<i class="ri-loader-4-line spin"></i> <span>Opening Studio...</span>';
    try {
      const response = await fetch('/api/social/youtube/connect-playwright', { method: 'POST' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'YouTube Studio launch failed');
    } catch (error) {
      const ytStatus = document.getElementById('yt-status-text');
      if (ytStatus) ytStatus.textContent = error.message;
    } finally {
      button.disabled = false;
      await refreshSocialStatus();
    }
  });

  refreshSocialStatus();
  
  // Ask Title & Hashtags Modal
  const modalAskCaption = document.getElementById('modal-ask-caption');
  const btnAskCaption = document.getElementById('btn-ask-caption');
  const btnAskUpload = document.getElementById('btn-ask-upload');
  const askCaptionFile = document.getElementById('ask-caption-file');
  const btnCloseAskCaption = document.getElementById('btn-close-ask-caption');
  
  if (btnAskCaption && modalAskCaption) {
    btnAskCaption.addEventListener('click', () => {
      modalAskCaption.classList.remove('hidden');
    });
  }
  if (btnCloseAskCaption && modalAskCaption) {
    btnCloseAskCaption.addEventListener('click', () => {
      modalAskCaption.classList.add('hidden');
    });
  }
  
  if (btnAskUpload && askCaptionFile) {
    btnAskUpload.addEventListener('click', () => askCaptionFile.click());
  }
  
  if (askCaptionFile) {
    askCaptionFile.addEventListener('change', async (e) => {
      if(!e.target.files.length) return;
      const file = e.target.files[0];
      
      document.getElementById('ask-caption-loading')?.classList.remove('hidden');
      document.getElementById('ask-caption-result')?.classList.add('hidden');
      if (btnAskUpload) btnAskUpload.style.display = 'none';
      
      const formData = new FormData();
      formData.append('file', file);
      
      try {
        const res = await fetch('/api/tools/generate-caption', {
          method: 'POST',
          body: formData
        });
        const data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Caption generation failed');
        
        document.getElementById('ask-caption-loading')?.classList.add('hidden');
        document.getElementById('ask-caption-result')?.classList.remove('hidden');
        if (btnAskUpload) btnAskUpload.style.display = 'block';
        
        const copyText = `Title: ${data.title}\n\nCaption:\n${data.caption}`;
        const txtArea = document.getElementById('ask-caption-text');
        if (txtArea) txtArea.value = copyText;
        
        // Save to localStorage history
        let capHist = JSON.parse(localStorage.getItem('captionHistory') || '[]');
        capHist.unshift({
          title: data.title,
          caption: data.caption,
          date: new Date().toLocaleDateString() + ' ' + new Date().toLocaleTimeString()
        });
        localStorage.setItem('captionHistory', JSON.stringify(capHist.slice(0, 50)));
      } catch(err) {
        console.error(err);
        Toast.show("Failed to generate captions: " + err.message, "error");
        document.getElementById('ask-caption-loading')?.classList.add('hidden');
        if (btnAskUpload) btnAskUpload.style.display = 'block';
      }
    });
  }
  
  document.getElementById('btn-ask-copy')?.addEventListener('click', async (e) => {
    const text = document.getElementById('ask-caption-text')?.value || document.getElementById('ask-caption-text')?.textContent || '';
    try {
      await navigator.clipboard.writeText(text);
      const btn = e.target.closest('button');
      if (btn) {
        const orig = btn.innerHTML;
        btn.innerHTML = '<i class="ri-check-line"></i> Copied!';
        setTimeout(() => btn.innerHTML = orig, 2000);
      }
    } catch(err) {}
  });

  // Ask Product Suggestion Modal
  const modalAskProduct = document.getElementById('modal-ask-product');
  const btnAskProduct = document.getElementById('btn-ask-product');
  const btnAskProductUpload = document.getElementById('btn-ask-product-upload');
  const askProductFile = document.getElementById('ask-product-file');
  const btnCloseAskProduct = document.getElementById('btn-close-ask-product');
  
  if (btnAskProduct && modalAskProduct) {
    btnAskProduct.addEventListener('click', () => {
      modalAskProduct.classList.remove('hidden');
    });
  }
  if (btnCloseAskProduct && modalAskProduct) {
    btnCloseAskProduct.addEventListener('click', () => {
      modalAskProduct.classList.add('hidden');
    });
  }
  
  if (btnAskProductUpload && askProductFile) {
    btnAskProductUpload.addEventListener('click', () => askProductFile.click());
  }
  
  if (askProductFile) {
    askProductFile.addEventListener('change', async (e) => {
      if(!e.target.files.length) return;
      const file = e.target.files[0];
      
      document.getElementById('ask-product-loading')?.classList.remove('hidden');
      document.getElementById('ask-product-result')?.classList.add('hidden');
      if (btnAskProductUpload) btnAskProductUpload.style.display = 'none';
      
      const formData = new FormData();
      formData.append('file', file);
      
      try {
        const res = await fetch('/api/tools/generate-products', {
          method: 'POST',
          body: formData
        });
        const data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Product generation failed');
        
        document.getElementById('ask-product-loading')?.classList.add('hidden');
        document.getElementById('ask-product-result')?.classList.remove('hidden');
        if (btnAskProductUpload) btnAskProductUpload.style.display = 'block';
        
        const listContainer = document.getElementById('ask-product-list');
        if (listContainer) {
          listContainer.innerHTML = '';
          if (data.products && data.products.length > 0) {
            data.products.forEach(prod => {
              const amzSearch = `https://www.amazon.com/s?k=${encodeURIComponent(prod.search_query || prod.product_name)}`;
              listContainer.innerHTML += `
                <div style="background: var(--bg-app); padding: 12px; border-radius: 6px; border: 1px solid var(--border-light);">
                  <div style="font-weight: 700; color: var(--text-main); margin-bottom: 4px;">${escapeHtml(prod.product_name)}</div>
                  <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 8px;">${escapeHtml(prod.reason || '')}</div>
                  <a href="${amzSearch}" target="_blank" class="btn-outline-dashed" style="display: inline-flex; align-items:center; gap:4px; color: #f59e0b; padding: 4px 10px; font-size: 11px; text-decoration: none;">
                    <i class="ri-amazon-fill"></i> Search on Amazon
                  </a>
                </div>
              `;
            });
          } else {
            listContainer.innerHTML = `<div class="text-muted" style="padding:10px;">No specific products found for this clip.</div>`;
          }
        }
      } catch(err) {
        console.error(err);
        Toast.show("Failed to generate product suggestions: " + err.message, "error");
        document.getElementById('ask-product-loading')?.classList.add('hidden');
        if (btnAskProductUpload) btnAskProductUpload.style.display = 'block';
      }
    });
  }

  // Upload Center Drawer / Modal
  const modalUploadCenter = document.getElementById('modal-upload-center');
  const btnUploadCenter = document.getElementById('btn-upload-center');
  const btnCloseUploadCenter = document.getElementById('btn-close-upload-center');
  if (btnUploadCenter && modalUploadCenter) {
    btnUploadCenter.addEventListener('click', () => {
      modalUploadCenter.classList.remove('hidden');
      if (typeof loadUploadCenter === 'function') loadUploadCenter();
    });
  }
  if (btnCloseUploadCenter && modalUploadCenter) {
    btnCloseUploadCenter.addEventListener('click', () => {
      modalUploadCenter.classList.add('hidden');
    });
  }

  document.querySelectorAll('.close-modal').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.modal-backdrop').forEach(m => m.classList.add('hidden'));
    });
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

  // Legacy history interactions removed to prevent JS errors with new UI layout

  const tabClip = document.getElementById('tab-clip-history');
  const tabCaption = document.getElementById('tab-caption-history');
  const histContainer = document.getElementById('history-container');
  const capHistContainer = document.getElementById('caption-history-container');

  if (tabClip && tabCaption && histContainer && capHistContainer) {
    tabClip.addEventListener('click', () => {
      tabClip.classList.add('active');
      tabCaption.classList.remove('active');
      histContainer.classList.remove('hidden');
      capHistContainer.classList.add('hidden');
      renderHistory();
    });

    tabCaption.addEventListener('click', () => {
      tabCaption.classList.add('active');
      tabClip.classList.remove('active');
      histContainer.classList.add('hidden');
      capHistContainer.classList.remove('hidden');
      renderCaptionHistory();
    });
  }

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

  // Legacy btnBackHome listener removed

  // ----------------------------------------------------
  // Core API Logic & WebSockets
  // ----------------------------------------------------
  
  function updateStepRing(stepId, percent) {
    const card = document.getElementById(stepId);
    if (!card) return;
    const ringFill = card.querySelector('.ring-fill');
    if (ringFill) {
      const clamped = Math.max(0, Math.min(100, Math.round(percent)));
      ringFill.setAttribute('stroke-dasharray', `${clamped}, 100`);
    }
  }

  function updateProgress(stepId, name, percent, exactStepPercent = null) {
    // Map virtual steps (like step-download) to physical stepper IDs
    if (stepId === 'step-download') stepId = 'step-demux';

    const stepMsgMap = {
      'step-demux': 'Extracting audio & video streams...',
      'step-asr': 'Transcribing speech locally with Whisper...',
      'step-hook': 'Detecting viral hooks & retention spikes...',
      'step-face': 'Tracking speaker faces & auto-framing...',
      'step-subs': 'Baking kinetic subtitle animations...',
      'step-render': 'Rendering final vertical clips...'
    };
    
    if (stepId && stepMsgMap[stepId]) {
      const funText = document.getElementById('fun-status-text');
      if (funText) funText.textContent = stepMsgMap[stepId];
    }

    if (stepId) {
      document.querySelectorAll('.stepper .step').forEach(c => {
        if (c.id !== stepId) c.classList.remove('active');
      });
      const card = document.getElementById(stepId);
      if (card) {
        card.classList.remove('hidden');
        card.classList.add('active');
        
        // Update SVG circular ring on active step
        const ringPercent = exactStepPercent !== null ? exactStepPercent : Math.min(100, (percent / (pipelineStageMap[Object.keys(pipelineStageMap).find(k => pipelineStageMap[k].id === stepId) || 1]?.percent || 100)) * 100);
        updateStepRing(stepId, ringPercent || percent);

        // Mark preceding steps as completed
        const steps = Array.from(document.querySelectorAll('.stepper .step'));
        const idx = steps.indexOf(card);
        if (idx > 0) {
          for (let i = 0; i < idx; i++) {
            const prev = steps[i];
            prev.classList.remove('active');
            prev.classList.add('completed', 'done');
            updateStepRing(prev.id, 100);
            const pContent = prev.querySelector('.step-icon-content');
            if (pContent) pContent.innerHTML = '<i class="ri-check-line"></i>';
            const prevConnector = prev.nextElementSibling;
            if (prevConnector && prevConnector.classList.contains('step-connector')) {
              prevConnector.classList.add('completed');
            }
          }
        }
      }
    }
    
    if (procBar) procBar.style.width = Math.min(100, Math.max(0, percent)) + "%";
    if (procStageName) procStageName.textContent = name + (name.endsWith('...') || name.endsWith(')') ? '' : '...');
    
    if (typeof gsap !== 'undefined' && procPercent) {
      try {
        gsap.to(procPercent, {
          innerHTML: Math.round(percent) + "%", duration: 0.3, snap: { innerHTML: 1 },
          onUpdate: function() { procPercent.innerHTML = Math.round(this.targets()[0].innerHTML.replace('%','')) + "%"; }
        });
      } catch(e) {
        procPercent.textContent = Math.round(percent) + "%";
      }
    } else if (procPercent) {
      procPercent.textContent = Math.round(percent) + "%";
    }
  }

  function appendLog(message) {
    const empty = document.getElementById('empty-log-state');
    if (empty) empty.remove();
    const p = document.createElement('p');
    p.textContent = String(message).replace(/<[^>]*>/g, '');
    consoleOutput.appendChild(p);
    consoleOutput.scrollTop = consoleOutput.scrollHeight;
  }

  function resetSteps() {
    pipelineClip = { current: 0, total: 0 };
    document.querySelectorAll('.stepper .step').forEach((c, i) => {
      c.classList.remove('active', 'completed', 'done');
      updateStepRing(c.id, 0);
      const content = c.querySelector('.step-icon-content');
      if (content) content.innerHTML = i + 1;
    });
    document.querySelectorAll('.stepper .step-connector').forEach(c => c.classList.remove('completed'));
    document.getElementById('step-download')?.classList.add('hidden');
    document.getElementById('btn-terminate-job')?.classList.add('hidden');
    
    const stageName = document.getElementById('proc-stage-name');
    if (stageName) stageName.textContent = 'Pipeline Ready';
    
    const statusBadge = document.getElementById('pipeline-status-badge');
    if (statusBadge) {
      statusBadge.textContent = 'Standby';
      statusBadge.style.color = '';
    }

    const jobMeta = document.getElementById('proc-job-meta');
    if (jobMeta) jobMeta.textContent = 'Select or drop a video file above to begin';

    if (procBar) procBar.style.width = "0%";
    if (procPercent) procPercent.textContent = "Estimated time remaining: —";
    const procSpeed = document.getElementById('proc-speed');
    if (procSpeed) procSpeed.textContent = "Avg. Speed: —";

    consoleOutput.innerHTML = '<div id="empty-log-state" style="text-align:center; padding:20px; color:#a0a0aa; font-size:13px;">No activity yet</div>';
  }

  async function startProcessing(fileOrUrl, isYoutube=false, isExistingUpload=false) {
    const stageName = document.getElementById('proc-stage-name');
    if (stageName) stageName.textContent = 'Initializing Pipeline...';
    const statusBadge = document.getElementById('pipeline-status-badge');
    if (statusBadge) {
      statusBadge.textContent = 'Active';
      statusBadge.style.color = '';
    }

    document.getElementById('proc-filename').textContent = typeof fileOrUrl === 'string' ? fileOrUrl : fileOrUrl.name;
    if (isYoutube) document.getElementById('proc-filename').textContent = "YouTube Video";
    
    resetSteps();
    if (statusBadge) statusBadge.textContent = 'Active';
    document.getElementById('btn-terminate-job')?.classList.remove('hidden');
    
    const launchPipeline = async () => {
      sectionUpload.classList.add('hidden');
      sectionProcessing.classList.remove('hidden');
      if (typeof gsap !== 'undefined') {
        try { gsap.fromTo(sectionProcessing, { y: 50, opacity: 0 }, { y: 0, opacity: 1, duration: 0.8, ease: "power3.out" }); } catch(e){}
      }
      
      try {
        // Send config (model, caption_style, etc) FIRST before initiating connections
        async function sendConfig(jobId) {
          const model = document.getElementById('config-model')?.value || 'small';
          const captionStyle = localStorage.getItem('captionStyle') || document.getElementById('config-caption-style')?.value || 'aftereffect_preset';
          const commentaryMode = document.getElementById('config-commentary-mode')?.value || 'hook_commentary';
          const commentaryVoice = document.getElementById('config-commentary-voice')?.value || 'af_sarah';
          const character = localStorage.getItem('selectedCharacter') || document.getElementById('config-character-select')?.value || 'anime_presenter.png';
          const cover = localStorage.getItem('selectedCover') || document.getElementById('config-cover-select')?.value || 'default_cover.jpg';
          try {
            await fetch(`/config/${jobId}`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ 
                 model: model,
                 caption_style: captionStyle,
                 commentary_mode: commentaryMode,
                 commentary_voice: commentaryVoice,
                 character: character,
                 cover: cover,
                 phase: 'all'
              })
            });
          } catch(e) { console.error("Config send failed", e); }
        }

        if (isYoutube) {
          document.getElementById('step-download')?.classList.remove('hidden');
          // fetch job ID from API
          const res = await fetch('/api/download-yt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: fileOrUrl })
          });
          const data = await res.json();
          if (data.job_id) {
            currentJobId = data.job_id;
            localStorage.setItem('currentJobId', data.job_id);
            localStorage.setItem('currentJobId_ts', Date.now());
            localStorage.setItem('ytUrl', fileOrUrl);
            await sendConfig(data.job_id);
            connectYoutubeWS(data.job_id, fileOrUrl);
          } else {
            throw new Error(data.error || "Failed to start YouTube download job");
          }
        } else if (isExistingUpload) {
          const res = await fetch(`/api/start-from-upload/${encodeURIComponent(fileOrUrl)}`, { method: 'POST' });
          const data = await res.json();
          if (data.job_id) {
            currentJobId = data.job_id;
            localStorage.setItem('currentJobId', data.job_id);
            localStorage.setItem('currentJobId_ts', Date.now());
            if (data.filename) {
              const fnEl = document.getElementById('proc-filename');
              if (fnEl) fnEl.textContent = data.filename;
            }
            await sendConfig(data.job_id);
            connectPipelineWS(data.job_id);
          } else {
            throw new Error(data.error || "Failed to start pipeline from existing upload");
          }
        } else {
           // Normal file upload
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
           } else {
             throw new Error(data.error || "Upload failed");
           }
        }
      } catch(e) {
        console.error("Pipeline initialization error:", e);
        const errMsg = e.message || "Failed to start pipeline";
        updateProgress(null, `Error: ${errMsg}`, 0);
        Toast.show(`Initialization error: ${errMsg}`, "error");
      }
    };

    // Direct synchronous launch of pipeline
    await launchPipeline();
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
         updateProgress('step-demux', 'Starting Download...', 0, 0);
      } else if (data.type === 'ytdl_log') {
         appendLog(data.raw);
      } else if (data.type === 'ytdl_progress') {
         const pct = Math.max(0, Math.min(100, Number(data.percent) || 0));
         const roundedPct = Math.round(pct);
         const phaseLabel = data.phase === 'audio' ? 'Downloading Audio Stream' : (data.phase === 'merging' ? 'Merging Video & Audio' : 'Downloading Video');
         
         updateProgress('step-demux', `${phaseLabel} (${roundedPct}%)`, roundedPct, roundedPct);
         
         const procSpeed = document.getElementById('proc-speed');
         if (procSpeed) {
           const speedText = data.speed ? `Avg. Speed: ${data.speed}` : '';
           const sizeText = data.size ? ` · ${data.size}` : '';
           procSpeed.textContent = (speedText + sizeText).trim() || 'Downloading...';
         }
         const procPercent = document.getElementById('proc-percent');
         if (procPercent) {
           const etaText = data.eta ? `ETA: ${data.eta} · ` : '';
           procPercent.textContent = `${etaText}${roundedPct}%`;
         }
      } else if (data.type === 'ytdl_done') {
         const fn = data.filename || 'Downloaded Video';
         const pfn = document.getElementById('proc-filename');
         if (pfn) pfn.textContent = fn;
         appendLog(`<span class="log-highlight">[YT-DLP]</span> Download completed (${data.size_mb ? data.size_mb + ' MB' : '1080p Full HD'}). Connecting to AI pipeline...`);
         updateProgress('step-demux', 'Download Finished', 100, 100);
         localStorage.removeItem('ytUrl');
         if (currentWs) currentWs.close();
         setTimeout(() => {
           connectPipelineWS(jobId);
         }, 300);
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
    
    // Poll for script updates live during pipeline execution
    const scriptPoll = setInterval(() => {
      fetchJobScript(jobId);
    }, 3000);
    fetchJobScript(jobId);

    currentWs = new WebSocket(wsUrl);
    currentWs.onclose = () => {
      clearInterval(scriptPoll);
    };
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
        fetchJobScript(jobId);
      } else if (data.type === 'clip_start') {
        pipelineClip = { current: data.clip_num, total: data.total };
        if (data.raw) {
          appendLog(`<span class="log-info" style="color:var(--text-muted)">[Log]</span> ${data.raw}`);
        }
        fetchJobScript(jobId);
      } else if (data.type === 'video_metadata') {
        if (!data.error) {
          const trySet = (id, txt) => { const el = document.getElementById(id); if (el) el.innerText = txt; };
          trySet('footer-fps', `FPS: ${data.fps}`);
          trySet('footer-format', `Format: ${data.format}`);
          trySet('footer-audio', `Audio: ${data.audio}`);
          trySet('footer-dur', `Duration: ${data.duration}`);
          trySet('footer-path', `Path: ${data.path}`);
          
          trySet('ui-res', data.resolution);
          trySet('ui-dur', data.duration);
          trySet('ui-fmt', data.format);
          
          trySet('proc-job-meta', `Resolution: ${data.resolution} \u00a0\u00a0 Duration: ${data.duration}`);
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
        fetchJobScript(jobId);
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
        clearInterval(scriptPoll);
        appendLog(`<span class="log-error">[Error]</span> ${data.message}`);
        updateProgress(null, 'Pipeline failed', 0);
        if (data.message === 'Job not found.') {
          localStorage.removeItem('currentJobId');
          setTimeout(() => btnCancel.click(), 1500);
        }
      } else if (data.type === 'log') {
        appendLog(`<span class="log-info" style="color:var(--text-muted)">[Log]</span> ${data.raw}`);
      } else if (data.type === 'warning') {
        appendLog(`<span class="log-warning">[Warning]</span> ${data.raw}`);
      } else if (data.type === 'phase_1_complete') {
        appendLog(`<span class="log-highlight">[System]</span> Phase 1 analysis complete.`);
        if (data.metadata) {
          renderScriptPreview(data.metadata);
        } else {
          fetchJobScript(jobId);
        }
      } else if (data.type === 'done') {
        clearInterval(scriptPoll);
        fetchJobScript(jobId);
        if (!data.success) {
          appendLog('[Error] Pipeline failed. Check the preceding log entries.');
          updateProgress(null, 'Pipeline failed', 0);
        } else {
          updateProgress('step-render', "Finished Processing", 100);
          appendLog(`<span class="log-highlight">[Success]</span> Pipeline completed.`);
          setTimeout(() => fetchClips(jobId), 1000);
        }
      }
    };
  }

  let currentLoadedScript = [];
  let currentScriptJobId = null;

  async function populateScriptJobSelector() {
    try {
      const res = await fetch('/history');
      if (!res.ok) return;
      const data = await res.json();
      const history = data.history || [];
      
      const selectors = [
        document.getElementById('script-job-selector'),
        document.getElementById('fs-job-selector')
      ].filter(Boolean);

      if (history.length === 0) {
        selectors.forEach(sel => {
          sel.innerHTML = '<option value="">No previous jobs</option>';
        });
        return;
      }

      let optionsHtml = '';
      history.forEach((job, idx) => {
        const d = job.created ? new Date(job.created * 1000) : new Date();
        const dateStr = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        const rawName = job.filename || `Job ${job.job_id.slice(0, 8)}`;
        const cleanName = rawName.replace(/^job_|\.mp4$/gi, '');
        const clipCount = job.clip_count || (job.clips ? job.clips.length : 0);
        const label = `${cleanName} (${clipCount} clips · ${dateStr})`;
        optionsHtml += `<option value="${job.job_id}">${escapeHtml(label)}</option>`;
      });

      selectors.forEach(sel => {
        sel.innerHTML = optionsHtml;
        if (currentScriptJobId) {
          sel.value = currentScriptJobId;
        }
      });

      // If no job selected yet, pick the first one
      if (!currentScriptJobId && history.length > 0) {
        currentScriptJobId = history[0].job_id;
        selectors.forEach(sel => sel.value = currentScriptJobId);
        fetchJobScript(currentScriptJobId);
      }
    } catch(e) {
      console.warn("populateScriptJobSelector error:", e);
    }
  }

  // Bind change listeners to script job selectors
  const jobSel = document.getElementById('script-job-selector');
  const fsJobSel = document.getElementById('fs-job-selector');
  
  if (jobSel) {
    jobSel.addEventListener('change', function() {
      currentScriptJobId = this.value;
      if (fsJobSel) fsJobSel.value = this.value;
      fetchJobScript(this.value);
    });
  }
  
  if (fsJobSel) {
    fsJobSel.addEventListener('change', function() {
      currentScriptJobId = this.value;
      if (jobSel) jobSel.value = this.value;
      fetchJobScript(this.value);
    });
  }

  // Fullscreen Script Modal Bindings
  const modalFsScript = document.getElementById('modal-script-fullscreen');
  const btnOpenFsScript = document.getElementById('btn-fullscreen-script');
  const btnCloseFsScript = document.getElementById('btn-close-fs-script');
  const overlayFsScript = document.getElementById('overlay-fs-script');
  const searchFsScript = document.getElementById('fs-script-search');

  function openFullscreenScript() {
    if (modalFsScript) {
      modalFsScript.classList.remove('hidden');
      if (fsJobSel && currentScriptJobId) fsJobSel.value = currentScriptJobId;
      renderFullscreenScriptCards(currentLoadedScript);
    }
  }

  function closeFullscreenScript() {
    if (modalFsScript) modalFsScript.classList.add('hidden');
  }

  btnOpenFsScript?.addEventListener('click', openFullscreenScript);
  btnCloseFsScript?.addEventListener('click', closeFullscreenScript);
  overlayFsScript?.addEventListener('click', closeFullscreenScript);

  searchFsScript?.addEventListener('input', function() {
    const query = this.value.toLowerCase().trim();
    if (!query) {
      renderFullscreenScriptCards(currentLoadedScript);
      return;
    }
    const filtered = currentLoadedScript.filter((clip, idx) => {
      const title = (clip.title || `clip ${idx + 1}`).toLowerCase();
      let hook = '';
      let comm = '';
      if (clip.editorial_data) {
        hook = typeof clip.editorial_data.hook === 'object' ? (clip.editorial_data.hook?.text || '') : (clip.editorial_data.hook || '');
        if (clip.editorial_data.commentary_segments) {
          comm = clip.editorial_data.commentary_segments.map(s => s.text || '').join(' ');
        }
      }
      return title.includes(query) || hook.toLowerCase().includes(query) || comm.toLowerCase().includes(query);
    });
    renderFullscreenScriptCards(filtered);
  });

  async function fetchJobScript(jobId) {
    if (!jobId) return;
    currentScriptJobId = jobId;
    try {
      const res = await fetch(`/api/script/${jobId}`);
      if (!res.ok) return;
      const data = await res.json();
      currentLoadedScript = data.script || [];
      renderScriptPreview(currentLoadedScript);
      if (modalFsScript && !modalFsScript.classList.contains('hidden')) {
        renderFullscreenScriptCards(currentLoadedScript);
      }
    } catch(e) {
      console.warn("fetchJobScript error:", e);
    }
  }

  function renderScriptPreview(metadata) {
    const container = document.getElementById('review-cards-container');
    if (!container) return;
    if (!metadata || metadata.length === 0) {
      container.innerHTML = `
        <div class="empty-script">
          <div class="empty-icon"><i class="ri-file-list-3-line"></i></div>
          <h4>No Script Generated For This Job</h4>
          <p>This job either used raw clipping or has no AI commentary script associated.</p>
        </div>
      `;
      return;
    }
    
    let html = '';
    metadata.forEach((clip, idx) => {
      const startSec = (clip.start_ms || 0) / 1000;
      const endSec = (clip.end_ms || 0) / 1000;
      const timeStr = `${Math.floor(startSec / 60)}:${Math.floor(startSec % 60).toString().padStart(2, '0')} - ${Math.floor(endSec / 60)}:${Math.floor(endSec % 60).toString().padStart(2, '0')}`;
      const scoreStr = clip.hook_score ? `${clip.hook_score}/100` : '—';
      const rawTitle = clip.title || (`Viral Clip #${idx + 1}`);
      const cleanTitle = rawTitle.replace(/^(?:clip[_\s\-]*\d+[_\s\-]*|\d+[\.\:\-]\s*)+/i, '').trim() || rawTitle;

      let hookText = '';
      let commentaryText = '';

      if (clip.editorial_data) {
        hookText = typeof clip.editorial_data.hook === 'object' ? (clip.editorial_data.hook?.text || '') : (clip.editorial_data.hook || '');
        if (clip.editorial_data.commentary_segments && clip.editorial_data.commentary_segments.length > 0) {
          commentaryText = clip.editorial_data.commentary_segments.map(s => s.text || '').filter(Boolean).join(' ');
        }
      }

      if (!hookText && clip.hook_text) hookText = clip.hook_text;
      if (!commentaryText && clip.commentary_text) commentaryText = clip.commentary_text;

      html += `
        <div class="script-preview-card" style="background: rgba(18, 18, 20, 0.75); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 14px; margin-bottom: 14px;">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); flex-wrap: wrap; gap: 6px;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span class="clip-num-badge" style="background: rgba(99, 102, 241, 0.15); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.3); padding: 2px 8px; border-radius: 8px; font-weight: 700; font-size: 0.72rem;">Clip #${idx + 1}</span>
              <strong style="color: #f3f4f6; font-size: 0.9rem;">${escapeHtml(cleanTitle)}</strong>
            </div>
            <span style="font-size: 0.75rem; color: #9ca3af;">${timeStr} · <span style="color:#f59e0b; font-weight:600;"><i class="ri-fire-fill"></i> Score: ${scoreStr}</span></span>
          </div>

          ${hookText ? `
            <div style="margin-bottom: 10px; background: rgba(99, 102, 241, 0.08); border-left: 3px solid #6366f1; padding: 10px 12px; border-radius: 6px;">
              <div style="font-size: 0.7rem; font-weight: 700; color: #818cf8; text-transform: uppercase; margin-bottom: 4px; letter-spacing: 0.5px;">
                <i class="ri-mic-line"></i> Opening Hook (Presenter Intro)
              </div>
              <p style="margin: 0; font-size: 0.84rem; line-height: 1.45; color: #e5e7eb;">${escapeHtml(hookText)}</p>
            </div>
          ` : ''}

          ${commentaryText ? `
            <div style="background: rgba(16, 185, 129, 0.08); border-left: 3px solid #10b981; padding: 10px 12px; border-radius: 6px;">
              <div style="font-size: 0.7rem; font-weight: 700; color: #34d399; text-transform: uppercase; margin-bottom: 4px; letter-spacing: 0.5px;">
                <i class="ri-chat-voice-line"></i> Explainer Commentary (Pause Breakdown)
              </div>
              <p style="margin: 0; font-size: 0.84rem; line-height: 1.45; color: #e5e7eb;">${escapeHtml(commentaryText)}</p>
            </div>
          ` : ''}
        </div>
      `;
    });

    container.innerHTML = html;
  }

  function renderFullscreenScriptCards(metadata) {
    const container = document.getElementById('fs-script-cards-container');
    if (!container) return;
    if (!metadata || metadata.length === 0) {
      container.innerHTML = `
        <div class="empty-script" style="padding: 40px; text-align: center;">
          <div class="empty-icon" style="font-size: 36px; margin-bottom: 12px;"><i class="ri-file-search-line"></i></div>
          <h4 style="font-size: 1.1rem; color: var(--text-main);">No Matching Dialogues Found</h4>
          <p style="color: var(--text-muted);">Try adjusting your search query or select another job.</p>
        </div>
      `;
      return;
    }

    let html = '';
    metadata.forEach((clip, idx) => {
      const startSec = (clip.start_ms || 0) / 1000;
      const endSec = (clip.end_ms || 0) / 1000;
      const timeStr = `${Math.floor(startSec / 60)}:${Math.floor(startSec % 60).toString().padStart(2, '0')} - ${Math.floor(endSec / 60)}:${Math.floor(endSec % 60).toString().padStart(2, '0')}`;
      const scoreStr = clip.hook_score ? `${clip.hook_score}/100` : '—';
      const rawTitle = clip.title || (`Viral Clip #${idx + 1}`);
      const cleanTitle = rawTitle.replace(/^(?:clip[_\s\-]*\d+[_\s\-]*|\d+[\.\:\-]\s*)+/i, '').trim() || rawTitle;

      let hookText = '';
      let commentaryText = '';

      if (clip.editorial_data) {
        hookText = typeof clip.editorial_data.hook === 'object' ? (clip.editorial_data.hook?.text || '') : (clip.editorial_data.hook || '');
        if (clip.editorial_data.commentary_segments && clip.editorial_data.commentary_segments.length > 0) {
          commentaryText = clip.editorial_data.commentary_segments.map(s => s.text || '').filter(Boolean).join(' ');
        }
      }

      if (!hookText && clip.hook_text) hookText = clip.hook_text;
      if (!commentaryText && clip.commentary_text) commentaryText = clip.commentary_text;

      html += `
        <div class="fs-script-card">
          <div class="fs-card-header">
            <div style="display: flex; align-items: center; gap: 10px;">
              <span class="clip-num-badge" style="background: rgba(99, 102, 241, 0.15); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.3); padding: 4px 10px; border-radius: 8px; font-weight: 700; font-size: 0.8rem;">Clip #${idx + 1}</span>
              <strong style="color: var(--text-main); font-size: 1.05rem;">${escapeHtml(cleanTitle)}</strong>
            </div>
            <div style="display: flex; align-items: center; gap: 10px;">
              <span style="font-size: 0.82rem; color: var(--text-muted);"><i class="ri-time-line"></i> ${timeStr}</span>
              <span style="font-size: 0.82rem; color: #f59e0b; font-weight: 600; background: rgba(245, 158, 11, 0.1); padding: 2px 8px; border-radius: 6px;"><i class="ri-fire-fill"></i> Score: ${scoreStr}</span>
            </div>
          </div>

          ${hookText ? `
            <div class="fs-dialogue-block fs-dialogue-hook">
              <div class="fs-dialogue-label" style="color: #818cf8;">
                <i class="ri-mic-line"></i> <span>Opening Hook (Frame 0 — Anime Teacher Intro)</span>
              </div>
              <p class="fs-dialogue-text">"${escapeHtml(hookText)}"</p>
            </div>
          ` : ''}

          ${commentaryText ? `
            <div class="fs-dialogue-block fs-dialogue-comm">
              <div class="fs-dialogue-label" style="color: #34d399;">
                <i class="ri-chat-voice-line"></i> <span>Mid-Clip Concept Breakdown (Video Freeze-Frame Explanation)</span>
              </div>
              <p class="fs-dialogue-text">"${escapeHtml(commentaryText)}"</p>
            </div>
          ` : ''}
        </div>
      `;
    });

    container.innerHTML = html;
  }

  async function fetchClips(jobId) {
    try {
      const url = jobId ? `/clips/${jobId}` : '/clips';
      const res = await fetch(url);
      const data = await res.json();
      
      localStorage.removeItem('currentJobId');
      
      const clips = data.clips || [];
      renderClips(clips);
      
      if (clips.length > 0) {
        Toast.show(`🎉 All done! Generated ${clips.length} viral clips.`, "success");
        // Also populate main player if first clip is available
        const mainPlayer = document.getElementById('main-player');
        if (mainPlayer && clips[0] && clips[0].url) {
          mainPlayer.src = clips[0].url;
          mainPlayer.classList.remove('hidden');
          document.getElementById('dropzone')?.classList.add('hidden');
          const titleEl = document.getElementById('player-title');
          if (titleEl) titleEl.textContent = clips[0].title || "Generated Clip";
        }
      }
    } catch(e) { console.error(e); }
  }

  async function fetchGalleryClips(jobId = null) {
    const container = document.getElementById('clips-container');
    if (container) {
      container.innerHTML = `
        <div style="text-align:center; padding:50px 20px; color:var(--text-muted);">
          <i class="ri-loader-4-line spin" style="font-size:32px; color:var(--brand-purple); display:block; margin-bottom:12px;"></i>
          <p style="font-size:0.95rem; font-weight:500; color:#f3f4f6;">Loading Clip Gallery...</p>
        </div>`;
    }
    try {
      const res = await fetch('/history');
      const data = await res.json();
      let historyJobs = data.history || [];
      if (jobId) {
        historyJobs = historyJobs.filter(j => j.job_id === jobId);
      }
      renderGalleryJobs(historyJobs);
    } catch(e) {
      console.error("Gallery fetch failed:", e);
      if (container) {
        container.innerHTML = `
          <div style="text-align:center; padding:50px 20px; color:var(--text-muted);">
            <i class="ri-error-warning-line" style="font-size:36px; color:#ef4444; margin-bottom:12px; display:block;"></i>
            <h4 style="color:#f3f4f6; margin-bottom:6px;">Failed to Load Gallery</h4>
            <p style="font-size:0.85rem;">Could not connect to clip storage service.</p>
          </div>`;
      }
    }
  }

  function escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str ?? '';
    return d.innerHTML;
  }

  function renderGalleryJobs(historyJobs) {
    const container = document.getElementById('clips-container');
    if(!container) return;
    
    if(!historyJobs || historyJobs.length === 0) {
      container.innerHTML = `
        <div style="text-align:center; padding:60px 20px; color:var(--text-muted); background:rgba(255,255,255,0.02); border:1px dashed rgba(255,255,255,0.1); border-radius:12px;">
          <i class="ri-film-line" style="font-size:40px; color:var(--brand-purple); opacity:0.6; margin-bottom:12px; display:block;"></i>
          <h4 style="color:#f3f4f6; margin-bottom:6px; font-size:1.1rem;">No Clips Generated Yet</h4>
          <p style="font-size:0.88rem; max-width:400px; margin:0 auto 16px; color:#9ca3af;">Upload a long-form video or select an existing file from Recent Videos to automatically extract viral vertical clips.</p>
        </div>`;
      return;
    }

    let html = '';
    let hasAnyClips = false;

    historyJobs.forEach(job => {
      const clips = job.clips || [];
      if (clips.length === 0) return;
      hasAnyClips = true;

      const createdDate = job.created ? new Date(job.created * 1000).toLocaleString() : 'Recent';
      const videoName = job.filename || job.job_id;

      let clipsHtml = '';
      clips.forEach((clip, i) => {
        const score = typeof clip.hook_score !== 'undefined' ? clip.hook_score : '?';
        const rawTitle = clip.title || ('Viral Clip ' + (i+1));
        const cleanTitle = rawTitle.replace(/^(?:clip[_\s\-]*\d+[_\s\-]*|\d+[\.\:\-]\s*)+/i, '').trim() || rawTitle;
        const cleanCaption = (clip.social_caption || '').replace(/^(?:clip[_\s\-]*\d+[_\s\-]*|\d+[\.\:\-]\s*)+/i, '').trim();

        const numBadgeHtml = clip.clip_number 
          ? `<span class="clip-num-badge" style="background:rgba(99, 102, 241, 0.15); color:#818cf8; border:1px solid rgba(99, 102, 241, 0.3); padding:2px 8px; border-radius:12px; font-weight:700; font-size:0.75rem; letter-spacing:0.5px;">Clip #${clip.clip_number}</span>`
          : `<span class="clip-num-badge" style="background:rgba(99, 102, 241, 0.15); color:#818cf8; border:1px solid rgba(99, 102, 241, 0.3); padding:2px 8px; border-radius:12px; font-weight:700; font-size:0.75rem; letter-spacing:0.5px;">Clip #${i + 1}</span>`;

        let productsHtml = '';
        if (clip.product_recommendations && clip.product_recommendations.length > 0) {
          productsHtml = `<div class="product-suggestions" style="margin-bottom: 15px; background: rgba(255, 153, 0, 0.1); border-left: 3px solid #ff9900; padding: 10px; border-radius: 6px;">
            <div style="font-size: 0.75rem; font-weight: 700; color: #ff9900; text-transform: uppercase; margin-bottom: 6px; letter-spacing: 0.5px;"><i class="ri-amazon-fill"></i> Amazon Suggestion</div>
          `;
          const amzTag = (localStorage.getItem('amazonStoreTag') || '').trim();
          clip.product_recommendations.forEach(prod => {
            let amzSearch = `https://www.amazon.com/s?k=${encodeURIComponent(prod.search_query || prod.product_name)}`;
            if (amzTag) amzSearch += `&tag=${encodeURIComponent(amzTag)}`;
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

        clipsHtml += `
          <div class="clip-card" style="opacity:0; transform:translateY(30px);">
            <div style="position:relative;">
              <video src="${clip.url}" class="clip-video" controls preload="metadata"${clip.thumbnail_url ? ` poster="${clip.thumbnail_url}"` : ''}></video>
            </div>
            <div class="clip-body">
              <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;">
                ${numBadgeHtml}
                <div class="clip-score" style="margin-top:0;"><i class="ri-fire-fill" style="color:#f59e0b;"></i> Score: ${score}/100</div>
              </div>
              <h3 class="clip-title" style="margin-bottom:8px; font-size:1.05rem; font-weight:700;">${escapeHtml(cleanTitle)}</h3>
              <div style="position:relative;">
                 <p class="clip-caption" style="font-size:0.85rem; color:#8b8b99; margin-bottom:15px; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden;">${escapeHtml(cleanCaption)}</p>
                 <button class="btn-outline btn-sm btn-copy" data-text="${encodeURIComponent(cleanTitle + '\n\n' + cleanCaption)}" style="position:absolute; right:0; top:-10px; padding:2px 6px; font-size:0.7rem;"><i class="ri-clipboard-line"></i> Copy</button>
              </div>
              ${productsHtml}
              <div class="clip-footer">
                <span class="text-xs text-muted" style="font-weight:600; letter-spacing:1px; text-transform:uppercase;">Job Reel</span>
                <div class="platform-toggles">
                  <a href="${clip.url}" download class="btn-outline btn-sm" style="padding:6px 12px; margin-right:8px; border-radius:8px; font-size:0.85rem; text-decoration:none;"><i class="ri-download-cloud-2-line"></i></a>
                  <button class="btn-primary btn-sm btn-publish" data-clip="${clip.url}" data-products='${JSON.stringify(clip.product_recommendations || []).replace(/'/g, "&#39;")}' style="padding:6px 16px; font-size:0.8rem;">Publish</button>
                </div>
              </div>
            </div>
          </div>
        `;
      });

      html += `
        <div class="job-gallery-block" style="margin-bottom: 35px; background: rgba(18, 18, 20, 0.85); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 14px; padding: 22px;">
          <div class="job-gallery-header" style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; padding-bottom: 14px; border-bottom: 1px solid rgba(255, 255, 255, 0.08); flex-wrap: wrap; gap: 12px;">
            <div>
              <h3 style="font-size: 1.15rem; font-weight: 700; color: #f3f4f6; margin-bottom: 4px; display: flex; align-items: center; gap: 8px;">
                <i class="ri-film-line" style="color: #818cf8;"></i> ${escapeHtml(videoName)}
              </h3>
              <span style="font-size: 0.82rem; color: #9ca3af;">
                <i class="ri-time-line"></i> ${createdDate} · <strong style="color: #e5e7eb;">${clips.length} Clip${clips.length > 1 ? 's' : ''}</strong>
              </span>
            </div>
            <button class="btn-primary-gradient btn-job-mass-post" data-job-id="${escapeHtml(job.job_id)}" style="padding: 9px 20px; border-radius: 8px; font-weight: 600; font-size: 0.85rem; display: flex; align-items: center; gap: 8px;">
              <i class="ri-send-plane-fill"></i> Publish All (${clips.length} Clips)
            </button>
          </div>
          <div id="job-grid-${escapeHtml(job.job_id)}" class="clips-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px;">
            ${clipsHtml}
          </div>
        </div>
      `;
    });

    if (!hasAnyClips) {
      container.innerHTML = `
        <div style="text-align:center; padding:60px 20px; color:var(--text-muted); background:rgba(255,255,255,0.02); border:1px dashed rgba(255,255,255,0.1); border-radius:12px;">
          <i class="ri-film-line" style="font-size:40px; color:var(--brand-purple); opacity:0.6; margin-bottom:12px; display:block;"></i>
          <h4 style="color:#f3f4f6; margin-bottom:6px; font-size:1.1rem;">No Completed Clips Found</h4>
          <p style="font-size:0.88rem; max-width:400px; margin:0 auto; color:#9ca3af;">Clips will appear here once rendering is finished.</p>
        </div>`;
      return;
    }

    container.innerHTML = html;
    if (typeof gsap !== 'undefined') {
      try { gsap.to("#clips-container .clip-card", { y: 0, opacity: 1, duration: 0.4, stagger: 0.05, ease: "power2.out", delay: 0.1 }); } catch(e){}
    }
  }

  function renderClips(clips) {
    // If a flat list of clips is passed, render them wrapped in a single job grid
    renderGalleryJobs([{
      job_id: currentJobId || 'current_job',
      filename: 'Active Session Clips',
      created: Date.now() / 1000,
      clips: clips
    }]);
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
          link.download = `cliphub-upload-${uploadId}.log`;
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
    if (!container) return;
    container.innerHTML = `
      <div style="text-align:center; padding:50px 20px; color:var(--text-muted);">
        <i class="ri-loader-4-line spin" style="font-size:32px; color:var(--brand-purple); display:block; margin-bottom:12px;"></i>
        <p style="font-size:0.95rem; font-weight:500; color:#f3f4f6;">Loading Processing History...</p>
      </div>`;
    
    try {
      const res = await fetch('/history');
      const data = await res.json();
      const historyJobs = data.history || [];
      
      if(historyJobs.length === 0) {
        container.innerHTML = `
          <div style="text-align:center; padding:60px 20px; color:var(--text-muted); background:rgba(255,255,255,0.02); border:1px dashed rgba(255,255,255,0.1); border-radius:12px;">
            <i class="ri-history-line" style="font-size:40px; color:var(--brand-purple); opacity:0.6; margin-bottom:12px; display:block;"></i>
            <h4 style="color:#f3f4f6; margin-bottom:6px; font-size:1.1rem;">No Processing History Found</h4>
            <p style="font-size:0.88rem; max-width:400px; margin:0 auto; color:#9ca3af;">Your past clipping jobs and generated reels will be recorded and organized here.</p>
          </div>`;
        return;
      }
      
      let html = '';
      let renderedAnyJob = false;
      
      historyJobs.forEach((job) => {
        const clips = job.clips || [];
        if (clips.length === 0) return;
        renderedAnyJob = true;
        
        const createdDate = job.created ? new Date(job.created * 1000).toLocaleString() : 'Recent';
        const videoName = job.filename || job.job_id;
        
        let clipsHtml = '';
        clips.forEach((clip, i) => {
          const score = typeof clip.hook_score !== 'undefined' ? clip.hook_score : '?';
          const rawTitle = clip.title || ('Viral Clip ' + (i+1));
          const cleanTitle = rawTitle.replace(/^(?:clip[_\s\-]*\d+[_\s\-]*|\d+[\.\:\-]\s*)+/i, '').trim() || rawTitle;
          const cleanCaption = (clip.social_caption || '').replace(/^(?:clip[_\s\-]*\d+[_\s\-]*|\d+[\.\:\-]\s*)+/i, '').trim();

          const numBadgeHtml = clip.clip_number 
            ? `<span class="clip-num-badge" style="background:rgba(99, 102, 241, 0.15); color:#818cf8; border:1px solid rgba(99, 102, 241, 0.3); padding:2px 8px; border-radius:12px; font-weight:700; font-size:0.75rem; letter-spacing:0.5px;">Clip #${clip.clip_number}</span>`
            : `<span class="clip-num-badge" style="background:rgba(99, 102, 241, 0.15); color:#818cf8; border:1px solid rgba(99, 102, 241, 0.3); padding:2px 8px; border-radius:12px; font-weight:700; font-size:0.75rem; letter-spacing:0.5px;">Clip #${i + 1}</span>`;

          let productsHtml = '';
          if (clip.product_recommendations && clip.product_recommendations.length > 0) {
            productsHtml = `<div class="product-suggestions" style="margin-bottom: 15px; background: rgba(255, 153, 0, 0.1); border-left: 3px solid #ff9900; padding: 10px; border-radius: 6px;">
              <div style="font-size: 0.75rem; font-weight: 700; color: #ff9900; text-transform: uppercase; margin-bottom: 6px; letter-spacing: 0.5px;"><i class="ri-amazon-fill"></i> Amazon Suggestion</div>
            `;
            const amzTag = (localStorage.getItem('amazonStoreTag') || '').trim();
            clip.product_recommendations.forEach(prod => {
              let amzSearch = `https://www.amazon.com/s?k=${encodeURIComponent(prod.search_query || prod.product_name)}`;
              if (amzTag) amzSearch += `&tag=${encodeURIComponent(amzTag)}`;
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

          clipsHtml += `
            <div class="clip-card" style="opacity:0; transform:translateY(20px);">
              <div style="position:relative;">
                <video src="${clip.url}" class="clip-video" controls preload="metadata"${clip.thumbnail_url ? ` poster="${clip.thumbnail_url}"` : ''}></video>
              </div>
              <div class="clip-body">
                <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;">
                  ${numBadgeHtml}
                  <div class="clip-score" style="margin-top:0;"><i class="ri-fire-fill" style="color:#f59e0b;"></i> Score: ${score}/100</div>
                </div>
                <h3 class="clip-title" style="margin-bottom:8px; font-size:1.05rem; font-weight:700;">${escapeHtml(cleanTitle)}</h3>
                <div style="position:relative;">
                   <p class="clip-caption" style="font-size:0.85rem; color:#8b8b99; margin-bottom:15px; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden;">${escapeHtml(cleanCaption)}</p>
                   <button class="btn-outline btn-sm btn-copy" data-text="${encodeURIComponent(cleanTitle + '\n\n' + cleanCaption)}" style="position:absolute; right:0; top:-10px; padding:2px 6px; font-size:0.7rem;"><i class="ri-clipboard-line"></i> Copy</button>
                </div>
                ${productsHtml}
                <div class="clip-footer">
                  <span class="text-xs text-muted" style="font-weight:600; letter-spacing:1px; text-transform:uppercase;">History</span>
                  <div class="platform-toggles">
                    <a href="${clip.url}" download class="btn-outline btn-sm" style="padding:4px 12px; margin-right:8px; font-size:0.8rem; text-decoration:none;"><i class="ri-download-cloud-2-line"></i></a>
                    <button class="btn-primary btn-sm btn-publish" data-clip="${clip.url}" data-products='${JSON.stringify(clip.product_recommendations || []).replace(/'/g, "&#39;")}' style="padding:4px 12px; font-size:0.8rem;">Publish</button>
                  </div>
                </div>
              </div>
            </div>
          `;
        });

        html += `
          <div class="job-history-block" style="margin-bottom: 35px; background: rgba(18, 18, 20, 0.8); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 20px;">
            <div class="job-history-header" style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; padding-bottom: 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.08);">
              <div>
                <h3 style="font-size: 1.1rem; font-weight: 700; color: #f3f4f6; margin-bottom: 4px; display: flex; align-items: center; gap: 8px;">
                  <i class="ri-film-line" style="color: #818cf8;"></i> ${escapeHtml(videoName)}
                </h3>
                <span style="font-size: 0.8rem; color: #9ca3af;">
                  <i class="ri-time-line"></i> ${createdDate} · <strong style="color: #e5e7eb;">${clips.length} Clip${clips.length > 1 ? 's' : ''}</strong>
                </span>
              </div>
              <button class="btn-primary btn-sm btn-job-mass-post" data-job-id="${escapeHtml(job.job_id)}" style="background: linear-gradient(135deg, #6366f1, #4f46e5); padding: 8px 16px; border-radius: 8px; font-weight: 600; font-size: 0.85rem; display: flex; align-items: center; gap: 6px;">
                <i class="ri-rocket-line"></i> Mass Post Video Clips (${clips.length})
              </button>
            </div>
            <div id="job-grid-${escapeHtml(job.job_id)}" class="clips-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 20px;">
              ${clipsHtml}
            </div>
          </div>
        `;
      });
      
      if (!renderedAnyJob) {
        container.innerHTML = `
          <div style="text-align:center; padding:60px 20px; color:var(--text-muted); background:rgba(255,255,255,0.02); border:1px dashed rgba(255,255,255,0.1); border-radius:12px;">
            <i class="ri-history-line" style="font-size:40px; color:var(--brand-purple); opacity:0.6; margin-bottom:12px; display:block;"></i>
            <h4 style="color:#f3f4f6; margin-bottom:6px; font-size:1.1rem;">No Clips Found in History</h4>
            <p style="font-size:0.88rem; max-width:400px; margin:0 auto; color:#9ca3af;">No completed video clips were found in your output storage.</p>
          </div>`;
        return;
      }
      
      container.innerHTML = html;
      if (typeof gsap !== 'undefined') {
        try { gsap.to("#history-container .clip-card", { y: 0, opacity: 1, duration: 0.4, stagger: 0.05, ease: "power2.out", delay: 0.1 }); } catch(e){}
      }
      
    } catch(e) {
      console.error("renderHistory error:", e);
      container.innerHTML = `
        <div style="text-align:center; padding:50px 20px; color:var(--text-muted);">
          <i class="ri-error-warning-line" style="font-size:36px; color:#ef4444; margin-bottom:12px; display:block;"></i>
          <h4 style="color:#f3f4f6; margin-bottom:6px;">Failed to Load History</h4>
          <p style="font-size:0.85rem;">Could not retrieve job records from server.</p>
        </div>`;
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
    const resetToUpload = () => {
      sectionProcessing.classList.add('hidden');
      sectionUpload.classList.remove('hidden');
      if (typeof gsap !== 'undefined') {
        try { gsap.fromTo(sectionUpload, { y: -30, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6, ease: "power3.out" }); } catch(e){}
      }
      loadRecentUploads();
    };

    if (typeof gsap !== 'undefined') {
      try {
        gsap.to(sectionProcessing, { 
          opacity: 0, y: 30, duration: 0.5, ease: "power2.inOut", 
          onComplete: resetToUpload
        });
      } catch(e) {
        resetToUpload();
      }
    } else {
      resetToUpload();
    }
  });

  const btnBackFromClips = document.getElementById('btn-back-from-clips');
  if (btnBackFromClips) {
    btnBackFromClips.addEventListener('click', () => {
      const resetClipsToUpload = () => {
        sectionClips.classList.add('hidden');
        sectionUpload.classList.remove('hidden');
        if (typeof gsap !== 'undefined') {
          try { gsap.fromTo(sectionUpload, { y: -30, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6, ease: "power3.out" }); } catch(e){}
        }
        loadRecentUploads();
      };
      if (typeof gsap !== 'undefined') {
        try {
          gsap.to(sectionClips, { 
            opacity: 0, y: 30, duration: 0.4, ease: "power2.inOut", 
            onComplete: resetClipsToUpload
          });
        } catch(e) {
          resetClipsToUpload();
        }
      } else {
        resetClipsToUpload();
      }
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
    document.getElementById('btn-confirm-publish').classList.add('hidden');
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
      let products = [];
      try {
        products = JSON.parse(btn.getAttribute('data-products') || '[]');
      } catch(e) {}
      const cleanPath = clipPath.replace(/^https?:\/\/[^\/]+/, '');
      const parts = cleanPath.split('/').filter(Boolean);
      if (parts.length >= 2) {
        const filename = parts[parts.length - 1];
        const jobId = parts[parts.length - 2];
        executePublish(jobId, filename, title, caption, products, platforms, btn, true);
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

  document.addEventListener('click', (e) => {
    const jobBtn = e.target.closest('.btn-job-mass-post');
    if (jobBtn) {
      const jobId = jobBtn.getAttribute('data-job-id');
      jobBtn.innerHTML = '<i class="ri-check-line"></i> Mass Post Initiated';
      jobBtn.classList.add('btn-success');
      triggerMassPublish(`#job-grid-${jobId}`);
    }
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
      try { products = JSON.parse(btn.getAttribute('data-products') || '[]'); } catch(e) {}
      
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
      document.getElementById('btn-confirm-publish').classList.remove('hidden');
      document.getElementById('btn-publish-done').classList.add('hidden');
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
          Toast.show('Please select at least one platform (YouTube or Instagram).', 'warning');
          return;
        }
        
        selectionView.classList.add('hidden');
        progressView.classList.remove('hidden');
        document.getElementById('btn-confirm-publish').classList.add('hidden');
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
      const amazonStoreTag = (localStorage.getItem('amazonStoreTag') || '').trim();
      const enableCommentAffiliate = (document.getElementById('opt-yt-comment')?.checked ?? (localStorage.getItem('ytCommentEnabled') !== 'false'));
      const enableNativeShopping = (document.getElementById('opt-yt-shopping')?.checked ?? (localStorage.getItem('ytShoppingEnabled') === 'true'));

      const response = await fetch('/api/social/post', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          job_id: jobId, clip_filename: filename, title: title, caption: caption,
          platforms: platforms, allow_duplicate: false, product_recommendations: products,
          amazon_store_tag: amazonStoreTag, enable_comment_affiliate: enableCommentAffiliate,
          enable_native_shopping: enableNativeShopping
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
              platforms: platforms, allow_duplicate: true, product_recommendations: products,
              amazon_store_tag: amazonStoreTag, enable_comment_affiliate: enableCommentAffiliate,
              enable_native_shopping: enableNativeShopping
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
              document.getElementById('btn-confirm-publish').classList.add('hidden');
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
            btn.textContent = data.error || 'Failed';
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

  // ─── Pipeline Job Termination System (Double Confirmation) ───
  const btnTerminateJob = document.getElementById('btn-terminate-job');
  const modalConfirmTerminate = document.getElementById('modal-confirm-terminate');
  const terminateStep1 = document.getElementById('terminate-step-1');
  const terminateStep2 = document.getElementById('terminate-step-2');
  const btnCancelTerminate = document.getElementById('btn-cancel-terminate');
  const btnBackTerminate = document.getElementById('btn-back-terminate');
  const btnProceedTerminateStep2 = document.getElementById('btn-proceed-terminate-step2');
  const btnConfirmKillJob = document.getElementById('btn-confirm-kill-job');
  const overlayConfirmTerminate = document.getElementById('overlay-confirm-terminate');
  const terminateJobName = document.getElementById('terminate-job-name');

  function openTerminateModal() {
    if (!currentJobId) {
      Toast.show("No active job to terminate.", "info");
      return;
    }
    const fnEl = document.getElementById('proc-filename');
    const curName = fnEl ? fnEl.textContent : 'running pipeline';
    if (terminateJobName) terminateJobName.textContent = curName;
    
    // Reset to step 1
    terminateStep1?.classList.remove('hidden');
    terminateStep2?.classList.add('hidden');
    modalConfirmTerminate?.classList.remove('hidden');
  }

  function closeTerminateModal() {
    modalConfirmTerminate?.classList.add('hidden');
  }

  btnTerminateJob?.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    openTerminateModal();
  });

  btnProceedTerminateStep2?.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    terminateStep1?.classList.add('hidden');
    terminateStep2?.classList.remove('hidden');
  });

  btnBackTerminate?.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    terminateStep2?.classList.add('hidden');
    terminateStep1?.classList.remove('hidden');
  });

  btnCancelTerminate?.addEventListener('click', closeTerminateModal);
  overlayConfirmTerminate?.addEventListener('click', closeTerminateModal);

  btnConfirmKillJob?.addEventListener('click', async (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!currentJobId) {
      closeTerminateModal();
      return;
    }

    const jid = currentJobId;
    btnConfirmKillJob.disabled = true;
    btnConfirmKillJob.innerHTML = `<i class="ri-loader-4-line spin"></i> Aborting Process...`;

    try {
      await fetch(`/api/cancel/${jid}`, { method: 'POST' });
      appendLog(`<span class="log-warning" style="color:#ef4444;">[System]</span> Pipeline process aborted and terminated by user.`);
      Toast.show("Pipeline job safely terminated.", "info");
    } catch(err) {
      console.error("Cancel job error:", err);
      Toast.show("Termination signal sent.", "info");
    }

    if (currentWs) {
      try { currentWs.close(); } catch(e) {}
    }

    localStorage.removeItem('currentJobId');
    localStorage.removeItem('currentJobId_ts');
    localStorage.removeItem('ytUrl');
    currentJobId = null;

    closeTerminateModal();
    btnTerminateJob?.classList.add('hidden');
    
    const statusBadge = document.getElementById('pipeline-status-badge');
    if (statusBadge) {
      statusBadge.textContent = 'Cancelled';
      statusBadge.style.color = '#ef4444';
    }
    const stageName = document.getElementById('proc-stage-name');
    if (stageName) stageName.textContent = 'Job Terminated';

    btnConfirmKillJob.disabled = false;
    btnConfirmKillJob.innerHTML = `<i class="ri-close-circle-fill"></i> Abort & Kill Process`;
  });

  // Handle modal close
  document.getElementById('btn-close-publish-modal')?.addEventListener('click', () => {
    document.getElementById('modal-publish').classList.add('hidden');
  });

  // On page load: populate script job selector, characters, covers, and load scripts
  populateScriptJobSelector();
  loadCharacters();
  loadCovers();

  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeFullscreenScript();
      closeTerminateModal();
    }
  });
});
