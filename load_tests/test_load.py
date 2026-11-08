"""
Locust load test suite for ResumeFit.
Simulates 20 to 50 concurrent users evaluating p95 latency and error rate.

Run with:
    locust -f load_tests/test_load.py --headless -u 30 -r 5 --run-time 5m --host http://localhost:8000
"""

from locust import HttpUser, between, task

SAMPLE_RESUME = """
Jane Doe
Senior Backend Engineer | Python, FastAPI, PostgreSQL, Kubernetes, Redis
Summary: High-performance backend engineer building distributed APIs and data pipelines.
Experience:
• Led architectural transition of monolith into 8 FastAPI microservices deployed on Kubernetes, serving 45,000 requests per minute with p99 latency under 45ms.
• Designed PostgreSQL schema and query optimization strategy with connection pooling and composite indexes.
• Built distributed asynchronous task queue with Redis and Celery processing 3.5 million daily notifications.
Skills: Python, FastAPI, Docker, Kubernetes, PostgreSQL, Redis, Pytest
"""

SAMPLE_JD = """
Senior Backend Engineer (Platform)
Requirements:
- 5+ years building production services with Python (FastAPI or Django)
- Strong experience with PostgreSQL, indexing, and connection pooling
- Hands-on experience with Docker and Kubernetes
- Production experience with Redis and microservices
"""


class ResumeFitUser(HttpUser):
    wait_time = between(1, 4)

    def on_start(self):
        """Authenticates user session and acquires CSRF token."""
        # 1. Fetch CSRF token
        csrf_res = self.client.get("/api/v1/auth/csrf")
        if csrf_res.status_code == 200:
            self.csrf_token = csrf_res.json().get("csrf_token")
        else:
            self.csrf_token = ""

        # 2. Login or Register with unique user ID
        import uuid

        user_email = f"loadtest_{uuid.uuid4().hex[:8]}@example.com"
        reg_payload = {
            "email": user_email,
            "password": "LoadTestSecurePassword123!",  # pragma: allowlist secret
        }
        res = self.client.post("/api/v1/auth/register", json=reg_payload)
        if res.status_code == 201:
            self.token = res.json().get("token")
        else:
            self.token = None

    @task(4)
    def check_health(self):
        """Pings liveness and readiness probes (lightweight baseline)."""
        self.client.get("/healthz")
        self.client.get("/readyz")

    @task(2)
    def fetch_history(self):
        """Tests paginated history endpoint."""
        if not self.token:
            return
        headers = {
            "Authorization": f"Bearer {self.token}",
            "X-CSRF-Token": self.csrf_token,
        }
        self.client.get("/api/v1/history?limit=10", headers=headers)

    @task(1)
    def run_analyze(self):
        """Tests CPU and NLP analysis pipeline under load."""
        if not self.token:
            return
        headers = {
            "Authorization": f"Bearer {self.token}",
            "X-CSRF-Token": self.csrf_token,
        }
        payload = {
            "job_title": "Senior Platform Engineer",
            "job_description": SAMPLE_JD,
            "resume_text": SAMPLE_RESUME,
        }
        self.client.post("/api/v1/analyze", data=payload, headers=headers)
