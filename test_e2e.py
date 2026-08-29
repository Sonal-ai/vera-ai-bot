"""Quick end-to-end test: push contexts, tick, and test reply."""
import json
import sys
import io
import urllib.request

# Fix Windows encoding for ₹ and other Unicode
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = "http://localhost:8000"

def post(path, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=35) as r:
        return json.loads(r.read())

def get(path):
    with urllib.request.urlopen(f"{BASE}{path}", timeout=5) as r:
        return json.loads(r.read())

# 1. Health check
print("=== HEALTHZ ===")
print(json.dumps(get("/v1/healthz"), indent=2))

# 2. Metadata
print("\n=== METADATA ===")
print(json.dumps(get("/v1/metadata"), indent=2))

# 3. Push category
print("\n=== PUSH CATEGORY ===")
r = post("/v1/context", {
    "scope": "category", "context_id": "dentists", "version": 1,
    "delivered_at": "2026-04-29T09:45:00Z",
    "payload": {
        "slug": "dentists",
        "voice": {
            "tone": "peer_clinical", "register": "respectful_collegial",
            "salutation_examples": ["Dr. {first_name}"],
            "vocab_taboo": ["guaranteed", "100% safe", "completely cure", "miracle", "best in city"]
        },
        "peer_stats": {"avg_ctr": 0.030, "avg_rating": 4.4, "avg_reviews": 62},
        "digest": [{
            "id": "d_2026W17_jida_fluoride",
            "title": "JIDA Oct 2026 fluoride recall trial",
            "summary": "2,100-patient trial showed 3-month fluoride recall cuts caries recurrence 38% better than 6-month in high-risk adults",
            "citation": "JIDA Oct 2026 p.14"
        }]
    }
})
print(json.dumps(r, indent=2))

# 4. Push merchant
print("\n=== PUSH MERCHANT ===")
r = post("/v1/context", {
    "scope": "merchant", "context_id": "m_001_drmeera", "version": 1,
    "delivered_at": "2026-04-29T10:00:00Z",
    "payload": {
        "merchant_id": "m_001_drmeera", "category_slug": "dentists",
        "identity": {
            "name": "Dr. Meera's Dental Clinic", "owner_first_name": "Meera",
            "city": "Delhi", "locality": "Lajpat Nagar", "verified": True,
            "languages": ["en", "hi"]
        },
        "performance": {
            "views": 2410, "calls": 18, "ctr": 0.021,
            "delta_7d": {"views_pct": 0.18, "calls_pct": -0.05}
        },
        "offers": [{"id": "den_001", "title": "Dental Cleaning @ \u20b9299", "status": "active"}],
        "customer_aggregate": {"high_risk_adult_count": 124, "total_unique_ytd": 540},
        "signals": ["ctr_below_peer_median", "high_risk_adult_cohort"]
    }
})
print(json.dumps(r, indent=2))

# 5. Push trigger
print("\n=== PUSH TRIGGER ===")
r = post("/v1/context", {
    "scope": "trigger", "context_id": "trg_001_research_digest_dentists", "version": 1,
    "delivered_at": "2026-04-29T10:00:00Z",
    "payload": {
        "id": "trg_001_research_digest_dentists", "scope": "merchant",
        "kind": "research_digest", "source": "external",
        "merchant_id": "m_001_drmeera", "urgency": 3,
        "suppression_key": "research:dentists:2026-W17",
        "payload": {
            "digest_id": "d_2026W17_jida_fluoride",
            "title": "JIDA Oct 2026 fluoride recall trial",
            "summary": "2,100-patient trial: 3-month fluoride recall cuts caries 38% vs 6-month in high-risk adults",
            "citation": "JIDA Oct 2026 p.14"
        }
    }
})
print(json.dumps(r, indent=2))

# 6. TICK — The big test!
print("\n=== TICK (LLM COMPOSE) ===")
r = post("/v1/tick", {
    "now": "2026-04-29T10:30:00Z",
    "available_triggers": ["trg_001_research_digest_dentists"]
})
print(json.dumps(r, indent=2))

if r.get("actions"):
    body = r["actions"][0].get("body", "")
    print(f"\n--- COMPOSED MESSAGE ---\n{body}\n")
    
    # 7. Test REPLY — merchant says "Yes, send me the abstract"
    print("\n=== REPLY TEST ===")
    r2 = post("/v1/reply", {
        "conversation_id": r["actions"][0]["conversation_id"],
        "merchant_id": "m_001_drmeera",
        "from_role": "merchant",
        "message": "Yes, send me the abstract",
        "received_at": "2026-04-29T10:45:00Z",
        "turn_number": 2
    })
    print(json.dumps(r2, indent=2))
    
    # 8. Test auto-reply detection
    print("\n=== AUTO-REPLY TEST ===")
    r3 = post("/v1/reply", {
        "conversation_id": "conv_autotest",
        "merchant_id": "m_001_drmeera",
        "from_role": "merchant",
        "message": "Thank you for contacting us. We will get back to you shortly.",
        "received_at": "2026-04-29T11:00:00Z",
        "turn_number": 1
    })
    print(json.dumps(r3, indent=2))

print("\n=== ALL TESTS COMPLETE ===")
