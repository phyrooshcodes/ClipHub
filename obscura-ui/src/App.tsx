import { getCurrentWindow } from '@tauri-apps/api/window';
import './index.css';

function App() {
  const handleMinimize = async () => {
    await getCurrentWindow().minimize();
  };

  const handleClose = async () => {
    await getCurrentWindow().close();
  };

  return (
    <div className="app-container">
      {/* Custom Titlebar */}
      <div className="titlebar" data-tauri-drag-region>
        <div className="titlebar-title" data-tauri-drag-region>
          <i className="ri-movie-2-line"></i>
          <span>Obscura Clips</span>
        </div>
        <div className="titlebar-controls">
          <button className="titlebar-button" onClick={handleMinimize}>
            <i className="ri-subtract-line"></i>
          </button>
          <button className="titlebar-button close" onClick={handleClose}>
            <i className="ri-close-line"></i>
          </button>
        </div>
      </div>

      <div className="main-layout">
        {/* Sidebar */}
        <div className="sidebar glass-panel" style={{ borderRadius: 0 }}>
          <div className="nav-item active">
            <i className="ri-upload-cloud-2-line"></i>
            <span>Upload Center</span>
          </div>
          <div className="nav-item">
            <i className="ri-video-add-line"></i>
            <span>Studio</span>
          </div>
          <div className="nav-item">
            <i className="ri-history-line"></i>
            <span>History</span>
          </div>
          <div style={{ flex: 1 }}></div>
          <div className="nav-item">
            <i className="ri-settings-4-line"></i>
            <span>Settings</span>
          </div>
        </div>

        {/* Content Area */}
        <div className="content-area">
          <h1 style={{ marginBottom: '8px' }}>Automate your <span style={{ color: 'var(--accent-cyan)' }}>Viral Growth</span></h1>
          <p style={{ marginBottom: '40px' }}>Upload a podcast or stream, and let the AI extract, edit, and publish the best clips automatically.</p>
          
          <div className="glass-panel" style={{ padding: '30px' }}>
            <div className="dropzone">
              <i className="ri-upload-cloud-2-line dropzone-icon"></i>
              <h2>Drag & Drop video file here</h2>
              <p>or click to browse from your computer</p>
            </div>
            
            <div style={{ textAlign: 'center', margin: '30px 0', color: 'var(--text-muted)' }}>
              <span>OR</span>
            </div>
            
            <div style={{ display: 'flex', gap: '16px' }}>
              <input type="text" className="input-glass" placeholder="Paste YouTube link here..." />
              <button className="btn btn-primary" style={{ whiteSpace: 'nowrap' }}>
                Fetch Video <i className="ri-arrow-right-line"></i>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
