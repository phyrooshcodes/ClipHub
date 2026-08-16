import os
import time
import requests

def download_file(url, dest):
    print(f"Downloading {url} to {dest}...")
    headers = {}
    if os.path.exists(dest):
        downloaded_bytes = os.path.getsize(dest)
        headers['Range'] = f'bytes={downloaded_bytes}-'
        print(f"Resuming from {downloaded_bytes} bytes...")
    else:
        downloaded_bytes = 0

    try:
        response = requests.get(url, headers=headers, stream=True, timeout=10)
        
        # 416 means requested range not satisfiable (already fully downloaded)
        if response.status_code == 416:
            print("File already fully downloaded.")
            return True
            
        response.raise_for_status()

        total_length = response.headers.get('content-length')
        
        mode = 'ab' if downloaded_bytes > 0 else 'wb'
        with open(dest, mode) as f:
            if total_length is None: # no content length header
                f.write(response.content)
            else:
                dl = 0
                total_length = int(total_length)
                for data in response.iter_content(chunk_size=4096):
                    dl += len(data)
                    f.write(data)
                    
                    # Print progress every ~10MB
                    if dl % (1024 * 1024 * 10) < 4096:
                        done = int(50 * (downloaded_bytes + dl) / (downloaded_bytes + total_length))
                        print(f"\r[{'=' * done}{' ' * (50-done)}] {downloaded_bytes + dl} bytes", end='')
        print("\nDownload complete.")
        return True
    except Exception as e:
        print(f"\nError: {e}")
        return False

def main():
    os.makedirs("temp/wheels", exist_ok=True)
    # Get the exact URL from pypi JSON API
    pkg_info = requests.get("https://pypi.org/pypi/onnxruntime-gpu/1.28.0/json").json()
    whl_url = None
    for r in pkg_info['urls']:
        if r['filename'].endswith('cp314-cp314-win_amd64.whl'):
            whl_url = r['url']
            break
            
    if not whl_url:
        # Fallback to hardcoded if not found in JSON for some reason
        print("Could not find win_amd64 whl url, assuming pip will find it.")
        return

    dest = f"temp/wheels/onnxruntime_gpu-1.28.0-cp314-cp314-win_amd64.whl"
    
    success = False
    while not success:
        success = download_file(whl_url, dest)
        if not success:
            print("Retrying in 2 seconds...")
            time.sleep(2)
            
    print("Download finished!")

if __name__ == "__main__":
    main()
