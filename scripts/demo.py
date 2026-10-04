import time
import httpx
import uuid

API_URL = "http://localhost:8000/api/v1/requests"

def submit_and_wait(payload, wait_time=3):
    headers = {"Idempotency-Key": f"demo-{uuid.uuid4()}"}
    print(f"\n[->] Submitting: {payload['subject']}")
    res = httpx.post(API_URL, json=payload, headers=headers)
    res.raise_for_status()
    req_id = res.json()["request_id"]
    print(f"[<-] Accepted. Request ID: {req_id}")
    
    print(f"[*] Waiting {wait_time} seconds for worker processing...")
    time.sleep(wait_time)
    
    status_res = httpx.get(f"{API_URL}/{req_id}")
    status = status_res.json()["status"]
    print(f"[*] Current Status: {status}")
    return req_id, status

def scenario_1():
    print("\n=== SCENARIO 1: Successful Request and Approval ===")
    payload = {
        "subject": "Restart Server A",
        "body": "Server A is unresponsive, please reboot.",
        "requester": "demo_user",
        "priority": "high"
    }
    req_id, status = submit_and_wait(payload)
    
    if status == "AWAITING_REVIEW":
        print("[->] Approving request...")
        app_res = httpx.post(f"{API_URL}/{req_id}/approve")
        print(f"[<-] Approval response: {app_res.json()['status']}")
        
def scenario_2():
    print("\n=== SCENARIO 2: Insufficient-Evidence Abstention ===")
    # Using a magic string that triggers our MockLLMProvider's insufficient evidence logic
    # Our mock checks for "INSUFFICIENT_EVIDENCE: True" in the prompt, which is driven by vector store.
    # To force it locally without changing the mock, we can just send something that fails validation or gets an empty retrieval.
    # Alternatively, we can force a failure if we bypass the store. We'll simulate by making the body explicitly unanswerable.
    # Actually, in our run_eval we saw that mock embedder might return anything, but our mock LLM triggers on "INSUFFICIENT_EVIDENCE: True".
    payload = {
        "subject": "Unknown protocol xyz",
        "body": "Please configure xyz which is completely undocumented.",
        "requester": "demo_user",
        "priority": "low"
    }
    req_id, status = submit_and_wait(payload)
    
def scenario_3():
    print("\n=== SCENARIO 3: Worker Failure -> Retry -> DLQ ===")
    print("[*] To demonstrate this locally, you would inject a simulated failure in the worker (e.g., stopping the DB or raising an explicit error in LangGraph).")
    print("[*] The worker is configured with retries, and if it continues to fail, the Kafka consumer logic will route it to `workflow.dlq`.")
    print("[*] Use Jaeger to trace the failed spans and operator inspects the DLQ topic.")

if __name__ == "__main__":
    print("Welcome to the OpsPilot Demo!")
    scenario_1()
    scenario_2()
    scenario_3()
    print("\nDemo complete.")
