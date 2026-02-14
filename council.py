"""
Support Council - Get multiple perspectives on a question
Each voice weighs in from their lens, informed by shared memory
"""
import json
from pathlib import Path

VOICES_DIR = Path(__file__).parent / "voices"
VOICES = ["support", "gtm", "csm", "training", "help_center"]


def load_voice(voice_name):
    """Load a voice's persona"""
    voice_file = VOICES_DIR / f"{voice_name}.md"
    if voice_file.exists():
        return voice_file.read_text()
    return None


def load_memory_context():
    """Load shared memory for context"""
    from shared_memory import load_memory, load_entities
    return {
        "memory": load_memory(),
        "entities": load_entities()
    }


def format_council_prompt(question, voice_name):
    """Create prompt for a voice to weigh in"""
    persona = load_voice(voice_name)
    context = load_memory_context()

    return f"""You are the {voice_name.upper()} voice on a cross-functional council.

{persona}

## Shared Context (what we know)
Recent incidents: {json.dumps(context['memory'].get('incidents', [])[-3:], indent=2)}
Customer patterns: {json.dumps(context['memory'].get('customer_patterns', [])[-3:], indent=2)}
Recent decisions: {json.dumps(context['memory'].get('decisions', [])[-3:], indent=2)}

## Question for the council
{question}

Respond in 2-3 sentences from your perspective. Be direct. State your view and why.
"""


def convene_council(question):
    """Get all voices to weigh in on a question"""
    print(f"\n{'='*60}")
    print(f"COUNCIL QUESTION: {question}")
    print('='*60)

    prompts = {}
    for voice in VOICES:
        prompts[voice] = format_council_prompt(question, voice)
        print(f"\n[{voice.upper()}]")
        print(f"(Prompt ready - {len(prompts[voice])} chars)")

    print(f"\n{'='*60}")
    print("To run: Send each prompt to Claude/GPT and collect responses")
    print("Then synthesize: Where do they agree? Where do they differ?")
    print('='*60)

    return prompts


def get_memory_summary():
    """Get a summary of current memory state for context."""
    context = load_memory_context()
    mem = context['memory']

    summary = []

    # Recent incidents
    incidents = mem.get('incidents', [])[-3:]
    if incidents:
        summary.append("Recent incidents:")
        for inc in incidents:
            summary.append(f"  - [{inc.get('date')}] {inc.get('summary')}")

    # Customer patterns
    patterns = mem.get('customer_patterns', [])
    at_risk = [p for p in patterns if p.get('sentiment') in ['frustrated', 'unhappy']]
    if at_risk:
        summary.append(f"\nAt-risk customers ({len(at_risk)}):")
        for p in at_risk[:3]:
            summary.append(f"  - {p.get('customer')}: {p.get('sentiment')}, {p.get('recent_tickets')} tickets")

    # Theme summary from observations
    obs = mem.get('observations', [])
    if obs:
        themes = {}
        for o in obs[-50:]:  # Last 50 observations
            for t in o.get('themes', []):
                themes[t] = themes.get(t, 0) + 1
        if themes:
            summary.append(f"\nRecent themes (last 50 observations):")
            for t, c in sorted(themes.items(), key=lambda x: -x[1])[:5]:
                summary.append(f"  - {t}: {c}")

    return "\n".join(summary) if summary else "No significant memory context."


# Example usage
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        question = "Based on recent observations, what should Support prioritize this week?"

    print("\n" + "=" * 60)
    print("CURRENT MEMORY CONTEXT")
    print("=" * 60)
    print(get_memory_summary())

    prompts = convene_council(question)

    # Save prompts for easy copy/paste
    output_file = Path(__file__).parent / "council_prompts.json"
    with open(output_file, 'w') as f:
        json.dump(prompts, f, indent=2)
    print(f"\nPrompts saved to: {output_file}")
    print("\nCopy each prompt into Claude/GPT to get perspectives.")
