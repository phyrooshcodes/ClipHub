import requests
import time
import os

base_url = "http://127.0.0.1:7842"

def main():
    resp = requests.get(f"{base_url}/clips")
    data = resp.json()
    clips = data.get("clips", [])
    
    # Get last 6 clips. Assuming they are ordered by clip_number or modified, let's just take the first 6 if it's already sorted.
    # From output, clip_number 10, 9, 8... so it's already sorted by newest.
    clips_to_upload = clips[:6]
    print(f"Found {len(clips_to_upload)} clips to upload.")
    
    upload_ids = []
    for c in clips_to_upload:
        # We need job_id which is in the url. url = /output/{jobId}/{filename}
        parts = c["url"].split('/')
        job_id = parts[2]
        
        payload = {
            "job_id": job_id,
            "clip_filename": c["filename"],
            "title": c["title"],
            "caption": c["social_caption"],
            "platforms": ["youtube"],
            "allow_duplicate": True
        }
        try:
            res = requests.post(f"{base_url}/api/social/post", json=payload)
            data = res.json()
            print(f"Posted {c['filename']}: {data}")
            if "upload_id" in data:
                upload_ids.append(data["upload_id"])
        except Exception as e:
            print(f"Error posting {c['filename']}: {e}")
            
    print("Upload IDs:", upload_ids)
    
    # Poll them
    for i in range(20):
        print(f"\n--- Poll {i} ---")
        for uid in upload_ids:
            try:
                st = requests.get(f"{base_url}/api/social/post-status/{uid}").json()
                print(f"{uid}: {st}")
            except Exception as e:
                print(f"Error querying {uid}: {e}")
        time.sleep(2)

if __name__ == '__main__':
    main()
