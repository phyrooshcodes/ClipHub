import threading
import time
import sys
import os
import socket
import uvicorn

# On Windows, set explicit AppUserModelID so taskbar displays custom icon instead of Python logo
if sys.platform == "win32":
    try:
        import ctypes
        app_id = "phyrooshcodes.cliphub.desktop.studio.1"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass

def is_port_in_use(port=7842):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def run_server():
    try:
        from server import app
        uvicorn.run(app, host="127.0.0.1", port=7842, log_level="warning")
    except Exception as e:
        print(f"Server start notice: {e}")

def _set_win32_window_icon(icon_path: str):
    """Set native window icon on Windows titlebar and taskbar via Win32 API."""
    if sys.platform != "win32" or not os.path.exists(icon_path):
        return
    try:
        import ctypes
        from ctypes import wintypes
        
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x00000010
        LR_DEFAULTSIZE = 0x00000040
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1

        user32 = ctypes.windll.user32
        h_icon_big = user32.LoadImageW(None, icon_path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
        h_icon_small = user32.LoadImageW(None, icon_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)

        def enum_windows_callback(hwnd, extra):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                if "ClipHub" in buff.value:
                    if h_icon_big:
                        user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, h_icon_big)
                    if h_icon_small:
                        user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, h_icon_small)
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        cb = WNDENUMPROC(enum_windows_callback)
        
        def _apply():
            for _ in range(25):
                time.sleep(0.2)
                user32.EnumWindows(cb, 0)
        
        t = threading.Thread(target=_apply, daemon=True)
        t.start()
    except Exception:
        pass

def main():
    try:
        import webview
    except ImportError:
        print("Error: pywebview is not installed. Please run 'pip install pywebview'.")
        sys.exit(1)

    # Prevent server.py from spawning a standard web browser
    os.environ["CLIPHUB_OPEN_BROWSER"] = "0"
    
    if is_port_in_use(7842):
        print("ClipHub Server is already running on http://127.0.0.1:7842")
    else:
        print("Starting ClipHub Local Server...")
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        time.sleep(1.5)
    
    icon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "app_icon.ico"))
    if not os.path.exists(icon_path):
        icon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "ui", "favicon.ico"))
        
    print("Launching ClipHub Desktop UI...")
    _set_win32_window_icon(icon_path)

    # Create native window
    window = webview.create_window(
        title='ClipHub', 
        url='http://127.0.0.1:7842', 
        width=1366, 
        height=850, 
        min_size=(1024, 768),
        background_color='#F8F9FA'
    )
    
    webview.start(icon=icon_path if os.path.exists(icon_path) else None)

if __name__ == '__main__':
    main()
