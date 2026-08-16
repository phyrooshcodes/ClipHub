import threading
import time
import sys
import os
import uvicorn

import socket

def is_port_in_use(port=7842):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def run_server():
    try:
        from server import app
        uvicorn.run(app, host="127.0.0.1", port=7842, log_level="warning")
    except Exception as e:
        print(f"Server start notice: {e}")

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
    
    print("Launching ClipHub Desktop UI...")
    # Create a native window
    window = webview.create_window(
        title='ClipHub', 
        url='http://127.0.0.1:7842', 
        width=1366, 
        height=850, 
        min_size=(1024, 768),
        background_color='#F8F9FA'
    )
    
    webview.start()

if __name__ == '__main__':
    main()
