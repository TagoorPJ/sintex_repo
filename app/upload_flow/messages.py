"""
upload_flow/messages.py

All user-facing strings used by the deterministic Upload Purchase flow,
in the four supported languages:
  - english
  - hindi
  - marathi
  - hinglish

Why these are hard-coded instead of LLM-generated:
The user explicitly requires that the QR URL and the dealer_code passed to
create_claim are 100% deterministic — no LLM rewriting, no paraphrasing.
Keeping the message text static guarantees the flow text is also stable
and identical for every user, in every language.

Every helper accepts a `language` argument (case-insensitive). Unknown
languages fall back to English.
"""

from __future__ import annotations

from typing import List, Optional


SUPPORTED_LANGUAGES = ("english", "hindi", "marathi", "hinglish")


def _norm(language: str) -> str:
    lang = (language or "").strip().lower()
    return lang if lang in SUPPORTED_LANGUAGES else "english"


# ──────────────────────────────────────────────────────────────────────
# 1. UPLOAD PURCHASE SUB-MENU
# ──────────────────────────────────────────────────────────────────────

_SUBMENU = {
    "english": (
        "📦 Upload Purchase\n\n"
        "What would you like to do?\n\n"
        "1. Scan QR Code\n"
        "2. Create a Claim\n"
        "3. See Claim Status"
    ),
    "hindi": (
        "📦 खरीद अपलोड करें\n\n"
        "आप क्या करना चाहते हैं?\n\n"
        "1. QR कोड स्कैन करें\n"
        "2. क्लेम बनाएं\n"
        "3. क्लेम स्टेटस देखें"
    ),
    "marathi": (
        "📦 खरेदी अपलोड करा\n\n"
        "तुम्हाला काय करायचे आहे?\n\n"
        "1. QR कोड स्कॅन करा\n"
        "2. क्लेम तयार करा\n"
        "3. क्लेम स्टेटस पहा"
    ),
    "hinglish": (
        "📦 Purchase Upload\n\n"
        "Aap kya karna chahte hain?\n\n"
        "1. QR Code Scan karein\n"
        "2. Claim banayein\n"
        "3. Claim Status dekhein"
    ),
}


def submenu(language: str) -> str:
    return _SUBMENU[_norm(language)]


# ──────────────────────────────────────────────────────────────────────
# 2. INVALID SUBMENU SELECTION
# ──────────────────────────────────────────────────────────────────────

_INVALID_SUBMENU = {
    "english": "Please choose a valid option: 1, 2, or 3.",
    "hindi": "कृपया सही विकल्प चुनें: 1, 2 या 3।",
    "marathi": "कृपया योग्य पर्याय निवडा: 1, 2 किंवा 3.",
    "hinglish": "Please valid option chunein: 1, 2, ya 3.",
}


def invalid_submenu_choice(language: str) -> str:
    return _INVALID_SUBMENU[_norm(language)]


# ──────────────────────────────────────────────────────────────────────
# 3. ASK DEALER FIRM NAME
# ──────────────────────────────────────────────────────────────────────

_ASK_FIRM_NAME = {
    "english": "Please type your dealer firm name.",
    "hindi": "कृपया अपने डीलर का फर्म नाम टाइप करें।",
    "marathi": "कृपया तुमच्या डीलरचे फर्म नाव टाइप करा.",
    "hinglish": "Apne dealer ka firm name type karein.",
}


def ask_firm_name(language: str) -> str:
    return _ASK_FIRM_NAME[_norm(language)]


# ──────────────────────────────────────────────────────────────────────
# 4. DEALER LIST FAILURES
# ──────────────────────────────────────────────────────────────────────

_DEALER_FETCH_FAILED = {
    "english": (
        "Sorry, we couldn't load your dealer list right now. "
        "Please try again in a few minutes."
    ),
    "hindi": (
        "माफ़ कीजिये, अभी आपकी डीलर लिस्ट लोड नहीं हो पाई। "
        "कुछ मिनट बाद फिर से कोशिश करें।"
    ),
    "marathi": (
        "क्षमस्व, आत्ता तुमची डीलर यादी लोड होऊ शकली नाही. "
        "कृपया काही वेळाने पुन्हा प्रयत्न करा."
    ),
    "hinglish": (
        "Sorry, abhi aapki dealer list load nahi ho payi. "
        "Kuch der baad phir try karein."
    ),
}


def dealer_fetch_failed(language: str) -> str:
    return _DEALER_FETCH_FAILED[_norm(language)]


_NO_DEALERS_FOUND = {
    "english": "No dealer firms are linked to your account yet.",
    "hindi": "आपके खाते से अभी कोई डीलर फर्म जुड़ी नहीं है।",
    "marathi": "तुमच्या खात्याशी अद्याप कोणतीही डीलर फर्म जोडलेली नाही.",
    "hinglish": "Aapke account se abhi koi dealer firm linked nahi hai.",
}


def no_dealers_found(language: str) -> str:
    return _NO_DEALERS_FOUND[_norm(language)]


# ──────────────────────────────────────────────────────────────────────
# 5. NUMBERED MATCH LIST
# ──────────────────────────────────────────────────────────────────────

_MATCH_HEADER = {
    "english": "Found matching dealers for '{q}':",
    "hindi": "'{q}' के लिए मिलते-जुलते डीलर:",
    "marathi": "'{q}' साठी जुळणारे डीलर:",
    "hinglish": "'{q}' ke liye matching dealers:",
}

_MATCH_HEADER_MORE = {
    "english": "More matching dealers:",
    "hindi": "और मिलते-जुलते डीलर:",
    "marathi": "आणखी जुळणारे डीलर:",
    "hinglish": "Aur matching dealers:",
}

_MATCH_FOOTER = {
    "english": "Please enter the serial number of your correct dealer.",
    "hindi": "कृपया अपने सही डीलर का सीरियल नंबर डालें।",
    "marathi": "कृपया तुमच्या योग्य डीलरचा सिरीयल नंबर टाका.",
    "hinglish": "Apne sahi dealer ka serial number bhejein.",
}

_SHOW_MORE = {
    "english": "{n}. Show more options",
    "hindi": "{n}. और विकल्प देखें",
    "marathi": "{n}. आणखी पर्याय पहा",
    "hinglish": "{n}. Aur options dekhein",
}


def dealer_match_list(
    language: str,
    query: str,
    matches: List[dict],
    has_more: bool = False,
) -> str:
    """
    matches: list of {"serial": int, "firm_name": str, "dealer_code": str,
                       "city": str, "branch": str}
    has_more: when True, appends a "Show more options" entry with serial = len(matches)+1
    query: empty string on subsequent pages (header switches to "More matching dealers:")
    """
    lang = _norm(language)

    header = (
        _MATCH_HEADER_MORE[lang]
        if not query
        else _MATCH_HEADER[lang].format(q=query)
    )
    lines = [header, ""]

    for row in matches:
        city = row.get("city", "")
        branch = row.get("branch", "")
        line = f"{row['serial']}. {row['firm_name']}"
        if city:
            line += f" | City: {city}"
        if branch:
            line += f" | Branch: {branch}"
        lines.append(line)

    if has_more:
        show_more_serial = len(matches) + 1
        lines.append(_SHOW_MORE[lang].format(n=show_more_serial))

    lines.append("")
    lines.append(_MATCH_FOOTER[lang])
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────
# 6. NO FUZZY MATCH
# ──────────────────────────────────────────────────────────────────────

_NO_MATCH = {
    "english": (
        "No dealer matched '{q}'. "
        "Please check the spelling and type the firm name again."
    ),
    "hindi": (
        "'{q}' से कोई डीलर मेल नहीं खाया। "
        "कृपया वर्तनी जांचें और फर्म नाम फिर से टाइप करें।"
    ),
    "marathi": (
        "'{q}' शी जुळणारा डीलर सापडला नाही. "
        "कृपया स्पेलिंग तपासा आणि फर्म नाव पुन्हा टाइप करा."
    ),
    "hinglish": (
        "'{q}' se koi dealer match nahi hua. "
        "Spelling check karke firm name dobara type karein."
    ),
}


def no_match(language: str, query: str) -> str:
    return _NO_MATCH[_norm(language)].format(q=query)


# ──────────────────────────────────────────────────────────────────────
# 7. INVALID SERIAL
# ──────────────────────────────────────────────────────────────────────

_INVALID_SERIAL = {
    "english": "That is not a valid option. Please pick a number from the list above.",
    "hindi": "यह सही विकल्प नहीं है। कृपया ऊपर दी गई लिस्ट में से नंबर चुनें।",
    "marathi": "हा वैध पर्याय नाही. कृपया वरील यादीतील क्रमांक निवडा.",
    "hinglish": "Ye valid option nahi hai. Upar di gayi list me se number chunein.",
}

_INVALID_SERIAL_WITH_MORE = {
    "english": "That is not a valid option. Pick a number from the list, or choose the 'Show more' option.",
    "hindi": "यह सही विकल्प नहीं है। लिस्ट में से नंबर चुनें या 'और विकल्प देखें' चुनें।",
    "marathi": "हा वैध पर्याय नाही. यादीतून क्रमांक निवडा किंवा 'आणखी पर्याय पहा' निवडा.",
    "hinglish": "Ye valid option nahi hai. List me se number chunein ya 'Aur options dekhein' chunein.",
}


def invalid_serial(language: str, show_more: bool = False) -> str:
    lang = _norm(language)
    if show_more:
        return _INVALID_SERIAL_WITH_MORE[lang]
    return _INVALID_SERIAL[lang]


# ──────────────────────────────────────────────────────────────────────
# 8. QR LINK READY
# ──────────────────────────────────────────────────────────────────────

_QR_LINK = {
    "english": (
        "✅ Dealer selected: {firm}\n\n"
        "Open this link to scan your QR code:\n{url}"
    ),
    "hindi": (
        "✅ डीलर चुना गया: {firm}\n\n"
        "QR कोड स्कैन करने के लिए यह लिंक खोलें:\n{url}"
    ),
    "marathi": (
        "✅ डीलर निवडला: {firm}\n\n"
        "QR कोड स्कॅन करण्यासाठी हा लिंक उघडा:\n{url}"
    ),
    "hinglish": (
        "✅ Dealer selected: {firm}\n\n"
        "QR code scan karne ke liye yeh link open karein:\n{url}"
    ),
}


def qr_link_ready(language: str, firm_name: str, url: str) -> str:
    return _QR_LINK[_norm(language)].format(firm=firm_name, url=url)


# ──────────────────────────────────────────────────────────────────────
# 9. CREATE CLAIM — ASK PURCHASE AMOUNT
# ──────────────────────────────────────────────────────────────────────

_ASK_AMOUNT = {
    "english": (
        "✅ Dealer selected: {firm}\n\n"
        "Please enter the purchase amount in rupees."
    ),
    "hindi": (
        "✅ डीलर चुना गया: {firm}\n\n"
        "कृपया खरीद की राशि (रुपये में) डालें।"
    ),
    "marathi": (
        "✅ डीलर निवडला: {firm}\n\n"
        "कृपया खरेदीची रक्कम (रुपयांमध्ये) टाका."
    ),
    "hinglish": (
        "✅ Dealer selected: {firm}\n\n"
        "Purchase amount (rupees mein) enter karein."
    ),
}


def ask_purchase_amount(language: str, firm_name: str) -> str:
    return _ASK_AMOUNT[_norm(language)].format(firm=firm_name)


_INVALID_AMOUNT = {
    "english": "Please enter a valid amount in rupees (numbers only).",
    "hindi": "कृपया रुपये में सही राशि डालें (केवल संख्या)।",
    "marathi": "कृपया रुपयांमध्ये योग्य रक्कम टाका (फक्त आकडे).",
    "hinglish": "Please valid amount enter karein (sirf number).",
}


def invalid_amount(language: str) -> str:
    return _INVALID_AMOUNT[_norm(language)]


# ──────────────────────────────────────────────────────────────────────
# 10. CREATE CLAIM — RESULTS
# ──────────────────────────────────────────────────────────────────────

_CLAIM_SUCCESS = {
    "english": (
        "✅ Claim created successfully.\n"
        "{server_message}"
    ),
    "hindi": (
        "✅ क्लेम सफलतापूर्वक बनाया गया।\n"
        "{server_message}"
    ),
    "marathi": (
        "✅ क्लेम यशस्वीरीत्या तयार झाला.\n"
        "{server_message}"
    ),
    "hinglish": (
        "✅ Claim successfully ban gaya.\n"
        "{server_message}"
    ),
}


def claim_success(language: str, server_message: str = "") -> str:
    return _CLAIM_SUCCESS[_norm(language)].format(server_message=server_message or "")


_CLAIM_FAILED = {
    "english": (
        "❌ Sorry, we couldn't create your claim right now.\n"
        "{server_message}"
    ),
    "hindi": (
        "❌ माफ़ कीजिये, अभी आपका क्लेम नहीं बन सका।\n"
        "{server_message}"
    ),
    "marathi": (
        "❌ क्षमस्व, आत्ता तुमचा क्लेम तयार होऊ शकला नाही.\n"
        "{server_message}"
    ),
    "hinglish": (
        "❌ Sorry, abhi aapka claim nahi ban paya.\n"
        "{server_message}"
    ),
}


def claim_failed(language: str, server_message: str = "") -> str:
    return _CLAIM_FAILED[_norm(language)].format(server_message=server_message or "")


# ──────────────────────────────────────────────────────────────────────
# 11. CANCEL / EXIT
# ──────────────────────────────────────────────────────────────────────

_CANCELLED = {
    "english": "Upload Purchase cancelled. Type 'menu' to see the main menu.",
    "hindi": "खरीद अपलोड रद्द कर दी गई। मुख्य मेनू देखने के लिए 'menu' टाइप करें।",
    "marathi": "खरेदी अपलोड रद्द केली. मुख्य मेनू पाहण्यासाठी 'menu' टाइप करा.",
    "hinglish": "Upload Purchase cancel ho gaya. Main menu dekhne ke liye 'menu' type karein.",
}


def cancelled(language: str) -> str:
    return _CANCELLED[_norm(language)]
