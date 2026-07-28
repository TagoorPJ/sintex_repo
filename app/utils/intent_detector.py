# app/utils/intent_detector.py

from langchain_core.messages import HumanMessage, SystemMessage
import json
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def classify_correction_intent(llm, user_message: str) -> bool:
    """
    Detect if a blocked (non-plumber) user is trying to correct their answer.
    Returns True if they want to change to plumber, False otherwise.
    """
    messages = [
        SystemMessage(content="""You are an intent classifier.
The user previously said they are NOT a plumber / plumbing contractor and was blocked from the service.
Now they sent a new message. Decide if they are trying to CORRECT their earlier answer
(i.e. they actually ARE a plumber / plumbing contractor and selected wrong by mistake).

Examples of CORRECTION:
"I made a mistake", "I am a plumber", "I am a plumbing contractor",
"galti ho gayi", "main plumber hoon", "main plumbing contractor hoon",
"mujhe change karna hai", "actually yes", "haan main plumber hoon",
"mera jawab galat tha", "change kar do", "correction", "I selected wrong",
"wrong answer", "actually I am a plumber", "actually I am a plumbing contractor",
"1", "yes", "haan", "ha", "bilkul",
"plumber hun", "plumbing contractor hun", "ji haan"

Examples of NOT a correction (general chat):
"hello", "hi", "what is sintex", "help me", "kya hai ye"

Return STRICT JSON only:
{"is_correction": true | false}"""),
        HumanMessage(content=user_message),
    ]
    try:
        response = await llm.ainvoke(messages)
        result = json.loads(response.content.strip())
        is_correction = bool(result.get("is_correction", False))
        logger.info(f"[CORRECTION CLASSIFY] msg={user_message!r} → is_correction={is_correction}")
        return is_correction
    except Exception:
        logger.exception("[classify_correction_intent] Failed")
        return False


async def classify_plumber_reply(llm, user_message: str) -> bool | None:
    """
    Classify whether the user said yes (is a plumber) or no (is not a plumber).
    Handles any language, phrasing, slang, or typos.
    Returns: True = plumber, False = not plumber, None = unclear (re-ask).
    """
    messages = [
        SystemMessage(content="""You are a yes/no classifier.
The user was asked: "Are you a plumber / plumbing contractor?" (in their language).
Classify their reply as yes, no, or unclear.

User can reply in English, Hindi, Marathi, Hinglish, or any mix.
Examples of YES: yes, haan, ha, haa, bilkul, ji haan, ho, hoye, correct, right, plumber hun, main plumber hoon, plumbing contractor hun, main plumbing contractor hoon, 1, y
Examples of NO: no, nahi, nope, na, nai, nahi hoon, main plumber nahi, main plumbing contractor nahi, 2, n, nahin
Examples of UNCLEAR: maybe, don't know, what, who, anything unrelated

Return STRICT JSON only:
{"answer": "yes" | "no" | "unclear"}"""),
        HumanMessage(content=user_message),
    ]
    try:
        response = await llm.ainvoke(messages)
        result = json.loads(response.content.strip())
        answer = result.get("answer", "unclear")
        logger.info(f"[PLUMBER CLASSIFY] msg={user_message!r} → answer={answer}")
        if answer == "yes":
            return True
        if answer == "no":
            return False
        return None
    except Exception:
        logger.exception("[classify_plumber_reply] Failed")
        return None


async def detect_intent_and_language_change_llm(
    llm,
    user_message: str,
    context: list = None
):
    """
    Detect:
    1. intent => allow | block
    2. language change request

    All domain flows (upload purchase, QR scan, claim creation,
    claim status, rewards) are handled entirely by the agent.
    This guard only blocks clearly off-topic messages.

    Supports: English, Hindi, Marathi, Hinglish, Roman Hindi/Marathi
    """

    messages = [
        SystemMessage(
            content=f"""
Return STRICT JSON only.

You are an intent guard for Sintex chatbot.
Your ONLY job is to decide: allow or block.
All Sintex domain flows are handled by the main agent — never block them here.

==================================================
RECENT CONVERSATION CONTEXT
==================================================
{json.dumps(context or [], ensure_ascii=False)}

Use context carefully.
If user message is a continuation of any previous flow, ALWAYS allow.

Flow continuation examples (ALWAYS allow):
- yes / no / ok / sure / continue / haan / nahi
- 1 / 2 / 3 / 4 (menu selections)
- any number (pincode, amount, employees, sites, volume)
- invoice IDs like ABCD123456
- names, pincodes, brand selections
- upload purchase / scan qr / create claim / claim status
- any Sintex-related query in any language

==================================================
INTENT TYPES
==================================================

Return ONLY one of:
1. allow  — everything Sintex-related or ambiguous
2. block  — clearly off-topic, has nothing to do with Sintex

==================================================
BLOCK ONLY WHEN CLEARLY IRRELEVANT
==================================================

Block examples:
- write python code / write a program
- tell me a joke / funny story
- who is the prime minister / president
- recipe for biryani / how to cook
- cricket score / sports news
- write an essay / poem

NEVER block:
- Anything about registration, rewards, claims, purchases, QR, dealers
- Any numeric input (could be menu choice, pincode, amount, etc.)
- Simple confirmations or continuations
- Messages in Hindi / Marathi / Hinglish about Sintex topics
- Anything ambiguous — if unsure, ALWAYS allow

==================================================
LANGUAGE CHANGE DETECTION (MULTILINGUAL)
==================================================

Supported languages: english | hindi | marathi | hinglish

Detect language change ONLY if user clearly wants to switch.

CASE 1 — Explicit switch with target language:
- change language to hindi / switch to english / speak in marathi
- hindi me bolo / marathi madhye bola / hinglish me bolo
→ language_change_requested=true, target_language=<detected>

CASE 2 — Wants to switch but no language specified:
- change language / language badlo / bhasha badla / switch language
- i want to change language / mujhe language change karni hai / bhasha badalni ahe
- language change karo / please change language / language switch karo
→ language_change_requested=true, target_language=null

CASE 3 — Context-based language selection:
If previous assistant message asked user to choose a language,
then single words (hindi / english / marathi / hinglish / 1 / 2 / 3 / 4)
can mean language selection.
Otherwise, single words alone are NOT language change signals.

==================================================
SAFETY RULES
==================================================

- Numeric replies 1/2/3/4 are almost always flow continuation => allow
- If uncertain => allow
- Never block Sintex domain messages
- Never introduce new intent types

==================================================
OUTPUT STRICT JSON ONLY — NO OTHER TEXT
==================================================

{{
  "intent": "allow" | "block",
  "language_change_requested": true | false,
  "target_language": "english" | "hindi" | "marathi" | "hinglish" | null
}}
"""
        ),
        HumanMessage(content=user_message)
    ]

    logger.info(f" Input message: {user_message}")

    try:
        response = await llm.ainvoke(messages)
        raw_content = response.content.strip()

        logger.info(f"[LANG DETECT RAW] {raw_content}")

        result = json.loads(raw_content)

        logger.info(
            f"[INTENT DETECT RESULT] "
            f"intent={result.get('intent')} | "
            f"change_requested={result.get('language_change_requested')} | "
            f"target_language={result.get('target_language')}"
        )

        return result

    except Exception:
        logger.exception("[intent_detector] Failed")

        return {
            "intent": "allow",
            "language_change_requested": False,
            "target_language": None
        }