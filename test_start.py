import requests
import json

r = requests.get('http://localhost:7842/uploads')
print("Uploads:", r.status_code, r.text)

if r.status_code == 200:
    uploads = r.json().get('uploads', [])
    if uploads:
        fn = uploads[0]['filename']
        print("Filename:", fn)
        r2 = requests.post(f'http://localhost:7842/api/start-from-upload/{fn}')
        print("Start:", r2.status_code, r2.text)
        
        if r2.status_code == 200:
            jid = r2.json()['job_id']
            print("Job ID:", jid)
            
            import websocket
            ws = websocket.create_connection(f"ws://localhost:7842/ws/{jid}")
            print("Connected WebSocket")
            while True:
                msg = ws.recv()
                print("WS MSG:", msg)
                if 'done' in msg or 'error' in msg:
                    break
