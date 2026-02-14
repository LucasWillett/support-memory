"""
Shared memory for support agents
Import this in any bot to read/write shared context
"""
import json
from datetime import datetime
from pathlib import Path

MEMORY_DIR = Path(__file__).parent
MEMORY_FILE = MEMORY_DIR / "memory.json"
ENTITIES_FILE = MEMORY_DIR / "entities.json"


def load_memory():
    """Load shared memory"""
    with open(MEMORY_FILE) as f:
        return json.load(f)


def save_memory(data):
    """Save shared memory"""
    with open(MEMORY_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def load_entities():
    """Load entity tracking"""
    with open(ENTITIES_FILE) as f:
        return json.load(f)


def save_entities(data):
    """Save entity tracking"""
    with open(ENTITIES_FILE, 'w') as f:
        json.dump(data, f, indent=2)


# === Quick helpers ===

def log_incident(incident_id, summary, affected_customers=None, resolution=None):
    """Log a new incident"""
    mem = load_memory()
    mem["incidents"].append({
        "id": incident_id,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "summary": summary,
        "affected_customers": affected_customers or [],
        "resolution": resolution,
        "lessons": None
    })
    save_memory(mem)


def log_decision(topic, decision, rationale=None):
    """Log a decision made"""
    mem = load_memory()
    mem["decisions"].append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "topic": topic,
        "decision": decision,
        "rationale": rationale
    })
    save_memory(mem)


def update_customer(customer_id, **kwargs):
    """Update customer tracking"""
    ent = load_entities()
    if customer_id not in ent["customers"]:
        ent["customers"][customer_id] = {"name": customer_id}
    ent["customers"][customer_id].update(kwargs)
    ent["customers"][customer_id]["last_contact"] = datetime.now().strftime("%Y-%m-%d")
    save_entities(ent)


def get_customer_context(customer_name):
    """Get all context about a customer across memory"""
    mem = load_memory()
    ent = load_entities()

    context = {
        "entity": None,
        "incidents": [],
        "patterns": []
    }

    # Find in entities
    for cid, cust in ent.get("customers", {}).items():
        if customer_name.lower() in cust.get("name", "").lower():
            context["entity"] = cust
            break

    # Find in incidents
    for inc in mem.get("incidents", []):
        if customer_name.lower() in str(inc.get("affected_customers", [])).lower():
            context["incidents"].append(inc)

    # Find in patterns
    for pat in mem.get("customer_patterns", []):
        if customer_name.lower() in pat.get("customer", "").lower():
            context["patterns"].append(pat)

    return context


# === Example usage ===
if __name__ == "__main__":
    # Test: get context about a customer
    ctx = get_customer_context("Acme")
    print(json.dumps(ctx, indent=2))
