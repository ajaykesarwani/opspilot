import asyncio
import httpx
import time
import uuid

API_URL = "http://localhost:8000/api/v1/requests"
REQUESTS_TO_SEND = 50
CONCURRENCY = 10

async def send_request(client, index):
    payload = {
        "subject": f"Load Test Request {index}",
        "body": "This is an automated load test payload.",
        "requester": "load_tester",
        "priority": "low"
    }
    headers = {
        "Idempotency-Key": f"load-test-{uuid.uuid4()}"
    }
    
    start = time.time()
    try:
        response = await client.post(API_URL, json=payload, headers=headers)
        response.raise_for_status()
        duration = time.time() - start
        return {"status": response.status_code, "duration": duration, "error": None}
    except Exception as e:
        duration = time.time() - start
        return {"status": None, "duration": duration, "error": str(e)}

async def main():
    print(f"Starting load test with {REQUESTS_TO_SEND} requests at concurrency {CONCURRENCY}...")
    
    async with httpx.AsyncClient() as client:
        tasks = []
        for i in range(REQUESTS_TO_SEND):
            tasks.append(send_request(client, i))
            
            if len(tasks) >= CONCURRENCY:
                results = await asyncio.gather(*tasks)
                for res in results:
                    if res["error"]:
                        print(f"Failed: {res['error']}")
                tasks = []
                
        if tasks:
            await asyncio.gather(*tasks)

    print("Load test complete. Check Grafana/Prometheus or Jaeger for metrics and traces.")

if __name__ == "__main__":
    asyncio.run(main())
