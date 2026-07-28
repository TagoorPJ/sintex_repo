from app.prompt_library.prompt_english import SYSTEM_PROMPT_EN
from app.prompt_library.prompt_hindi import SYSTEM_PROMPT_HI
from app.prompt_library.prompt_marathi import SYSTEM_PROMPT_MR
from app.prompt_library.prompt_hinglish import SYSTEM_PROMPT_HINGLISH


PROMPT_MAP = {
    "english": SYSTEM_PROMPT_EN,
    "hindi": SYSTEM_PROMPT_HI,
    "marathi": SYSTEM_PROMPT_MR,
    "hinglish": SYSTEM_PROMPT_HINGLISH,
}


def get_system_prompt(language: str) -> str:
    return PROMPT_MAP.get(language.lower(), SYSTEM_PROMPT_EN)