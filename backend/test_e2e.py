import sys
import logging
from fastapi.testclient import TestClient
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(BACKEND_DIR))

from main import app

client = TestClient(app)

def run_tests():
    print("🚀 Starting E2E Verification...")
    
    res = client.get("/api/health")
    assert res.status_code == 200, f"Health check failed: {res.text}"
    print("✅ Health check passed")
    
    print("📦 Ingesting repository...")
    res = client.post("/api/ingest/github", json={"url": "https://github.com/expressjs/express"})
    assert res.status_code == 200, f"Ingest failed: {res.text}"
    data = res.json()
    session_id = data["session_id"]
    print(f"✅ Ingest passed (Session ID: {session_id}), parsed {len(data.get('files', []))} files.")
    
    print("⚙️ Running analysis pipeline...")
    res = client.post(f"/api/analyze/start/{session_id}")
    assert res.status_code in [200, 202], f"Analysis failed: {res.text}"
    
    import time
    print("⏳ Waiting for analysis to complete...")
    for _ in range(60):
        prog = client.get(f"/api/analyze/progress/{session_id}").json()
        stage = prog.get("stage")
        if stage == "done":
            break
        if stage == "error":
            raise Exception("Analysis pipeline hit an error.")
        time.sleep(0.5)
    else:
        raise Exception("Analysis timed out in test.")
    print("✅ Analysis passed")
    
    print("💀 Checking dead code...")
    res = client.get(f"/api/analysis/dead-code/{session_id}")
    assert res.status_code == 200, f"Dead code failed: {res.text}"
    print("✅ Dead code analysis passed (No crashes!)")
    
    print("🔗 Checking share endpoint...")
    res = client.get(f"/api/comments/{session_id}/share")
    assert res.status_code == 501, f"Share endpoint did not return 501: {res.status_code}"
    print("✅ Share endpoint correctly returned 501")

    print("\n🎉 ALL E2E TESTS PASSED!")

if __name__ == "__main__":
    run_tests()
