import asyncio
from fastapi.testclient import TestClient
from server import app
import os
from pathlib import Path

client = TestClient(app)

def test_downloads():
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    (out_dir / "test.mp4").write_text("dummy")

    # Test legitimate
    r = client.get("/output/test.mp4")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"

    # Test path traversal
    r = client.get("/output/..%2F..%2Fetc%2Fpasswd")
    assert r.status_code == 404, f"Expected 404 for traversal, got {r.status_code}"

    r = client.get("/output/..%2F/..%2Fetc%2Fpasswd")
    assert r.status_code == 404

    # Test start-from-upload traversal
    r = client.post("/api/start-from-upload/..%2F..%2Fetc%2Fpasswd")
    assert r.status_code == 404

    # Test SSRF in _bg_social_post
    # Since it's internal we can just verify the code logic by importing it
    # But it's hard to test background task without mocking
    print("Tests passed")

if __name__ == "__main__":
    test_downloads()
