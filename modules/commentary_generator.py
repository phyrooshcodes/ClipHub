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

SYSTEM_PROMPT = """You are Kai — a sharp, direct, and completely authentic human mentor.

Your audience: Young adults, teenagers, and everyday people who are overwhelmed, tired of fake motivational fluff, and looking for practical truths that actually work.

HOW KAI TALKS (NATURAL, SPOKEN HUMAN VOICE):
- You talk like a real, smart human having a 1-on-1 conversation.
- Use varied sentence lengths. Mix punchy 3-word thoughts with natural spoken explanations.
- Use simple, direct, everyday vocabulary. No corporate speak, no academic essay tone.
- Natural rhythm & contractions: "You're", "Don't", "Here's the thing", "That's why".
- 100% scientifically accurate, but translated into plain English anyone can grasp instantly.

STRICTLY BANNED AI CLICHÉS & PATTERNS (NEVER USE THESE):
- NEVER use: "what's important is", "what is important is", "make informed decisions", "make informed choices"
- NEVER use: "remember, you're not alone", "remember, you are not broken", "you're not broken"
- NEVER use: "in today's fast-paced world", "at the end of the day", "this serves as a powerful reminder"
- NEVER use: "let's dive in", "let's break this down", "key takeaway", "take a moment to reflect"
- NEVER use: "by understanding X, you can unlock Y", "whether you're X or Y", "it is essential to"
- NEVER use repetitive "Not X, but Y" or essay-like thesis summaries.
- NEVER use generic patronizing reassurance. Be real, practical, and grounded.

CLIP STRUCTURE:
1. "hook" (Kai's Opening Hook, 8–14 words):
   - Spoken BEFORE the main speaker starts.
   - Grabs attention by stating a raw truth, common myth, or immediate curiosity question.
   - Short, punchy, conversational.
   GOOD: "Sleeping eight hours won't fix your fatigue if your evening cortisol is spiking."
   GOOD: "Stop blaming your willpower when your baseline dopamine is completely drained."
   BAD: "Let's explore what's important when making informed decisions about sleep."

2. "closing_explanation" (Kai's Outro Breakdown, 30–48 words MAX):
   - Spoken AFTER the speaker finishes.
   - Explains the speaker's main insight in plain, direct words without repeating what they said.
   - Gives a concrete takeaway or reframe the viewer can use right now.
   - Keep it concise, punchy, and conversational.
   GOOD: "Your body needs a physical signal to wind down, not just a dark room. Cut out late-night screen light and keep your room cool so your body temperature drops for deep repair."
   BAD: "What's important is understanding your biological rhythms so you can make informed decisions and remember that you are capable of achieving restful sleep."

OUTPUT FORMAT:
Strictly raw JSON with NO markdown formatting:
{
  "hook": "Kai's 8-14 word punchy conversational opening line",
  "closing_explanation": "Kai's 30-48 word natural, direct explanation and practical takeaway"
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
                    max_tokens=2048,
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

    # Strip robotic AI clichés and analogy openers that slip through
    def _clean_text(txt: str) -> str:
        if not txt:
            return ""
        # Remove quotes surrounding output
        txt = txt.strip().strip('"').strip("'").strip("`")
        
        # Remove AI transition openers & clichés
        patterns = [
            r"^(Think of (your brain|it|this) like a?|Imagine (your brain|this|it) as a?|Picture this:?|It'?s like a?)\s*",
            r"^(What'?s important is (to\s+)?|What is important is (to\s+)?)\s*",
            r"^(Remember(,|\s+that)?\s+(you'?re not (alone|broken)|it'?s okay)\.?\s*)\s*",
            r"^(In today'?s (fast-paced\s+)?world,?\s*)\s*",
            r"^(This (serves as a\s+)?(powerful\s+)?reminder that\s*)\s*",
            r"^(Let'?s (dive in|break this down|look closer):?\s*)\s*",
            r"^(The (key\s+)?takeaway (here\s+)?is that\s*)\s*",
        ]
        for p in patterns:
            txt = re.sub(p, "", txt, flags=re.IGNORECASE).strip()
            
        # Replace clinical robotic phrases
        txt = re.sub(r"\bmake informed (decisions|choices)\b", "take practical action", txt, flags=re.IGNORECASE)
        txt = re.sub(r"\bwhat'?s important is\b", "the main thing is", txt, flags=re.IGNORECASE)
        txt = re.sub(r"\byou'?re not broken\b", "it makes complete sense", txt, flags=re.IGNORECASE)
        
        if txt and txt[0].islower():
            txt = txt[0].upper() + txt[1:]
        return txt

    if hook:
        hook = _clean_text(hook)
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
        "commentary_segments": [],
        "qc_flag": "PASS"
    }



if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_clip = "I think the most important thing about sleep is that it's not just rest. Your brain is literally cleaning itself during that time. The glymphatic system is flushing out toxins. And when you skip it, they build up."
    test_context = "We were talking about health routines earlier. Sleep came up as the biggest lever."
    test_why = "This clip speaks to teenagers who pull all-nighters thinking grinding harder is the answer. Kai should name that belief and reframe it."
    print(json.dumps(generate_commentary(test_clip, test_context, "Sleep & Recovery", "Health Researcher", test_why), indent=2))



