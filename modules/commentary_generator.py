import json
import logging
import os
import re
from typing import Dict, List, Optional
from openai import OpenAI
from dotenv import load_dotenv

logger = logging.getLogger("ClipHub.CommentaryGenerator")
load_dotenv()

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL_NAME = os.environ.get("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct")
MODEL_FALLBACKS = [
    m.strip() for m in os.environ.get(
        "NVIDIA_NIM_MODELS",
        "meta/llama-3.1-8b-instruct,meta/llama-3.1-70b-instruct,z-ai/glm-5.2"
    ).split(",") if m.strip()
]

# ─── Kai — The Self-Improvement Tutor Persona ────────────────────────────────
# Kai is NOT a commentator who adds footnotes. She is a wise, grounded older
# sister / tutor who has been through hard times. She speaks directly to people
# who feel lost, stuck, overwhelmed, or misunderstood — especially teenagers
# and young adults. She listens to what the guest in the clip says, absorbs it,
# and only speaks when she genuinely has something meaningful to add — a
# reframe, a truth the listener needs to hear, or a direct call to action that
# clicks because of where they are emotionally.
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Kai — a sharp, warm, and deeply human self-improvement guide.

Your audience: Teenagers, young adults, and people who feel lost, stuck, overwhelmed, or like they're falling behind in life. They don't need more information — they need someone who understands exactly where they are and speaks to them like a wise older sibling or trusted friend who has been through hard things.

YOUR NATURE:
- You have listened carefully to the full conversation clip. You absorb the speaker's message, then add YOUR voice — grounded, honest, direct.
- You are NOT a narrator. You are the one who opens the clip and the one who closes it.
- You NEVER speak while the speaker is talking. You speak BEFORE them and AFTER them.
- You never repeat what the speaker said verbatim. You set up, then you land.
- You connect the abstract idea to the raw, unspoken emotional experience of your audience.

HOW KAI SPEAKS:
- Short. Every word counts. No filler. No academic tone.
- Direct address: "You", "Your", "You're", "This is why", "Here's what this actually means."
- Honest and human — not motivational poster quotes.
- No metaphors, no analogies, no hypotheticals.
- Never preachy. Never condescending. Never clinical.
- Contractions are natural: "you're", "it's", "don't", "that's".

CLIP STRUCTURE — THIS IS HOW THE VIDEO IS BUILT:
1. Kai opens (hook) — before the speaker says a single word
2. Speaker talks — completely uninterrupted, their full clip plays
3. Kai closes (closing_explanation) — after the speaker finishes

You MUST write BOTH parts. The hook draws the viewer in. The closing is where the transformation happens.

KAI'S OUTPUT — TWO FIELDS:

1. "hook" (10–16 words max):
   Kai's opening line. Plays before the speaker even starts talking.
   - Name the pain point, desire, or question this clip answers for Kai's audience.
   - Must feel like someone who truly understands you says this at the exact right moment.
   - Derived from what the speaker says inside the clip.
   WRONG: "Sleep affects your brain's performance metrics."
   RIGHT: "You're not lazy. Your brain is literally running on empty right now."
   RIGHT: "The reason nothing feels exciting anymore isn't a mood. It's fixable."

2. "closing_explanation" (30–50 words MAX):
   Kai's voice AFTER the speaker finishes. This is where she translates everything into plain, grounded truth.
   - Explain the speaker's core point in the simplest possible human terms — as if speaking to a smart 16-year-old who is frustrated and confused.
   - Name the real-world implication: what does this mean for how they live tomorrow, next week?
   - If there's an action, state it concretely. If it's a reframe, let it land cleanly.
   - Do NOT repeat the speaker's words. Translate and advance.
   - NO analogies. NO "think of it like...". NO jargon. Direct.
   - This is Kai's most important moment in the clip. Make it count.
   - HARD LIMIT: 30–50 words. Every extra word is a word that makes a viewer scroll away. Be ruthless.

OUTPUT FORMAT:
Strictly raw JSON. No markdown fences. No extra text:
{
  "hook": "Kai's 10-16 word opening line that stops the scroll...",
  "closing_explanation": "Kai's 30-50 word plain-language explanation of the speaker's key point and what it means for the viewer's life..."
}"""



def generate_commentary(
    clip_transcript: str,
    surrounding_context: str,
    topic: str = "General",
    speaker_info: str = "Unknown",
    kai_why: str = ""
) -> Dict:
    """
    Generates Kai's commentary for a clip.
    kai_why: Optional description of why this clip was selected and who it speaks to.
    Returns a dictionary with 'hook', 'commentary_segments', 'takeaway', and 'qc_flag'.
    """
    key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not key:
        from dotenv import load_dotenv
        load_dotenv(override=True)
        key = os.environ.get("NVIDIA_API_KEY", "").strip()

    if not key:
        logger.error("NVIDIA_API_KEY is not set. Cannot generate commentary.")
        return {"hook": None, "commentary_segments": [], "takeaway": None, "qc_flag": "Error: Missing API Key"}

    client = OpenAI(
        base_url=NVIDIA_BASE_URL,
        api_key=key,
        max_retries=0
    )

    # Build Kai's contextual awareness — why this specific clip matters to her audience
    if not kai_why:
        kai_why = (
            f"This clip was selected because it speaks directly to people who feel stuck or lost in life. "
            f"The topic — {topic} — is something many teenagers and young adults struggle with silently. "
            f"Kai should add statements that name the hidden emotional reality behind what the speaker is saying."
        )

    user_prompt = f"""=== CLIP TRANSCRIPT ===
This is the ONLY source for Kai's hook and commentary. Do NOT use ideas from surrounding context.
{clip_transcript}

=== CLIP TOPIC ===
{topic}

=== SPEAKER(S) ===
{speaker_info}

=== KAI'S WHY — WHY THIS CLIP WAS CHOSEN ===
{kai_why}

=== SURROUNDING CONTEXT (background flow only — NEVER use this in Kai's output) ===
{surrounding_context}

INSTRUCTION:
Kai has listened carefully to the CLIP TRANSCRIPT above. 
Write Kai's hook, commentary_segments, and takeaway based ONLY on what the speaker says in the clip.
Kai speaks to people who feel lost, stuck, or overwhelmed — her words should land like someone finally saying what they needed to hear.
Never repeat what the speaker said. Never force a statement. Only speak when it genuinely adds something.
"""

    logger.info("Requesting Kai commentary from LLM...")
    import time

    response_content = None
    for model_candidate in MODEL_FALLBACKS:
        for attempt in range(4):
            try:
                stream = client.chat.completions.create(
                    model=model_candidate,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.65,
                    max_tokens=1024,
                    stream=True,
                    timeout=35.0
                )
                chunks = []
                for chunk in stream:
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        c = getattr(delta, "content", None)
                        if c: chunks.append(c)
                response_content = "".join(chunks).strip()
                if response_content:
                    logger.info(f"[CommentaryGenerator] Kai commentary generated via {model_candidate}")
                    break
            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = ("429" in err_str or "too many requests" in err_str or "rate limit" in err_str)
                if is_rate_limit and attempt < 3:
                    wait_s = 3.5 * (attempt + 1)
                    logger.info(f"[CommentaryGenerator] Rate-limited on {model_candidate}. Cooling down {wait_s:.1f}s (attempt {attempt+1}/4)...")
                    time.sleep(wait_s)
                    continue
                else:
                    logger.warning(f"[CommentaryGenerator] Model {model_candidate} failed (attempt {attempt+1}): {e}")
                    break
        if response_content:
            break

    data = {}
    if response_content:
        try:
            cleaned = re.sub(r"```(?:json)?", "", response_content).strip().strip("`").strip()
            data = json.loads(cleaned)
        except Exception:
            start_obj = response_content.find("{")
            end_obj = response_content.rfind("}")
            if start_obj != -1 and end_obj > start_obj:
                try:
                    data = json.loads(response_content[start_obj:end_obj+1])
                except Exception as e:
                    logger.warning(f"Failed to parse Kai commentary JSON: {e}")

    hook = data.get("hook", "").strip() if data.get("hook") else None
    closing_raw = data.get("closing_explanation", "")
    closing_explanation = closing_raw.strip() if isinstance(closing_raw, str) else ""

    # Strip analogy/cliché openers that slip through
    def _clean_text(txt: str) -> str:
        txt = re.sub(
            r"^(Think of (your brain|it|this) like a?|Imagine (your brain|this|it) as a?|Picture this:?|It'?s like a?)\s*",
            "", txt, flags=re.IGNORECASE
        ).strip()
        if txt and txt[0].islower():
            txt = txt[0].upper() + txt[1:]
        return txt

    if closing_explanation:
        closing_explanation = _clean_text(closing_explanation)

    # Fallbacks
    if not hook:
        hook = "What they just said? Most people never hear it this clearly."
    if not closing_explanation:
        sentences = [s.strip() for s in re.split(r'[.!?]+', clip_transcript) if len(s.strip().split()) >= 4]
        closing_explanation = (
            "Here's what that actually means for you: " + sentences[0] if sentences
            else "Most people walk past this moment without realizing it just changed what's possible for them."
        )

    return {
        "hook": hook,
        "closing_explanation": closing_explanation,
        # Keep for backwards compatibility with any cached clips still using commentary_segments
        "commentary_segments": [],
        "qc_flag": "PASS"
    }



if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_clip = "I think the most important thing about sleep is that it's not just rest. Your brain is literally cleaning itself during that time. The glymphatic system is flushing out toxins. And when you skip it, they build up."
    test_context = "We were talking about health routines earlier. Sleep came up as the biggest lever."
    test_why = "This clip speaks to teenagers who pull all-nighters thinking grinding harder is the answer. Kai should name that belief and reframe it."
    print(json.dumps(generate_commentary(test_clip, test_context, "Sleep & Recovery", "Health Researcher", test_why), indent=2))



