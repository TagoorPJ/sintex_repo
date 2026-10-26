"""LangChain tool for generating personalized festival greeting cards and sending them via WATI WhatsApp."""
from __future__ import annotations

import json
from typing import Optional
from langchain.tools import tool
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database import AsyncSessionLocal
from app.models import Asset, Conversation, Festival, Template, User
from app.utils.logger import get_logger
from app.utils.wati_client import send_session_image
from app.greetings import storage
from app.greetings.config import greeting_settings
from app.greetings.service import live_templates, render_template, template_for_festival
from greeting_renderer.festivals import match

logger = get_logger(__name__)


def _festival_emojis(fest_name: str) -> str:
    key = (fest_name or "").lower()
    if "diwali" in key:
        return "🪔✨"
    if "dussehra" in key or "dassehra" in key:
        return "🏹✨"
    if "pongal" in key or "sankranti" in key:
        return "🌾✨"
    if "ganesh" in key:
        return "🐘✨"
    return "🎉✨"


def _format_greeting_reply(
    festival_name: str,
    enterprise: str,
    name: str,
    wati_delivered: bool,
    image_url: str,
    language: str = "english",
) -> str:
    lang = (language or "english").lower().strip()

    if lang == "hindi":
        wishes = (
            f"✨ *आपको, आपके परिवार को और {enterprise} को {festival_name} की हार्दिक शुभकामनाएँ!* "
            f"यह पावन पर्व आपके और आपके व्यापार के लिए सुख, शांति, समृद्धि और अपार सफलता लेकर आए। 🪔"
        )
        options = (
            "क्या आप:\n"
            "1️⃣ *इस कार्ड को बदलना/रिफाइन करना चाहते हैं* (नाम या फर्म का नाम बदलें)\n"
            "2️⃣ *दूसरा कार्ड बनाना चाहते हैं* (किसी अन्य त्यौहार के लिए)\n\n"
            "कार्ड में बदलाव के लिए *1* भेजें, या नया कार्ड बनाने के लिए *2* अथवा त्यौहार का नाम भेजें!"
        )
        if wati_delivered:
            return (
                f"🎉 आपके लिए *{festival_name}* का खास ग्रीटिंग कार्ड तैयार है! 🪔\n\n"
                f"{wishes}\n\n"
                "अब आप इस ग्रीटिंग कार्ड को अपने ग्राहकों और दोस्तों के साथ आसानी से शेयर कर सकते हैं!\n\n"
                f"{options}"
            )
        else:
            return (
                f"🎉 आपके लिए *{festival_name}* का खास ग्रीटिंग कार्ड तैयार है! 🪔\n\n"
                f"👉 डाउनलोड और देखें: {image_url}\n\n"
                f"{wishes}\n\n"
                "आप इस ग्रीटिंग कार्ड को सेव करके अपने ग्राहकों और दोस्तों के साथ शेयर कर सकते हैं!\n\n"
                f"{options}"
            )

    elif lang == "hinglish":
        wishes = (
            f"✨ *Aapko, aapki family ko aur {enterprise} ko Happy {festival_name}!* "
            f"Yeh festive season aapke aur aapke business ke liye dher saari khushiyan, achhi sehat aur safalta lekar aaye. 🪔"
        )
        options = (
            "Kya aap:\n"
            "1️⃣ *Is card ko refine karna chahte hain* (naam ya firm name change karein)\n"
            "2️⃣ *Doosra card banana chahte hain* (kisi aur festival ke liye)\n\n"
            "Card refine karne ke liye *1* bhejein, ya naya card banane ke liye *2* ya festival ka naam bhejein!"
        )
        if wati_delivered:
            return (
                f"🎉 Aapke liye *{festival_name}* ka personalised greeting card taiyar hai! 🪔\n\n"
                f"{wishes}\n\n"
                "Aap is greeting card ko apne customers aur doston ke saath aasaani se forward aur share kar sakte hain!\n\n"
                f"{options}"
            )
        else:
            return (
                f"🎉 Aapke liye *{festival_name}* ka personalised greeting card taiyar hai! 🪔\n\n"
                f"👉 Download & View: {image_url}\n\n"
                f"{wishes}\n\n"
                "Aap is greeting card ko save karke apne customers aur doston ke saath share kar sakte hain!\n\n"
                f"{options}"
            )

    elif lang == "marathi":
        wishes = (
            f"✨ *तुम्हाला, तुमच्या कुटुंबाला आणि {enterprise} ला {festival_name} च्या मनापासून हार्दिक शुभेच्छा!* "
            f"हा सण तुमच्या आयुष्यात आणि व्यवसायात सुख, समृद्धी, उत्तम आरोग्य आणि यश घेऊन येवो. 🪔"
        )
        options = (
            "तुम्हाला:\n"
            "1️⃣ *हे कार्ड रिफाईन करायचे आहे का* (नाव किंवा फर्मचे नाव बदला)\n"
            "2️⃣ *दुसरे कार्ड बनवायचे आहे का* (दुसऱ्या सणासाठी)\n\n"
            "कार्ड बदलण्यासाठी *1* पाठवा, किंवा नवीन कार्डसाठी *2* अथवा सणाचे नाव पाठवा!"
        )
        if wati_delivered:
            return (
                f"🎉 तुमच्यासाठी *{festival_name}* चे खास पर्सनलाईज्ड ग्रीटिंग कार्ड तयार आहे! 🪔\n\n"
                f"{wishes}\n\n"
                "आता तुम्ही हे ग्रीटिंग कार्ड तुमच्या ग्राहकांसोबत आणि मित्रांसोबत सहज शेअर करू शकता!\n\n"
                f"{options}"
            )
        else:
            return (
                f"🎉 तुमच्यासाठी *{festival_name}* चे खास पर्सनलाईज्ड ग्रीटिंग कार्ड तयार आहे! 🪔\n\n"
                f"👉 डाउनलोड आणि पहा: {image_url}\n\n"
                f"{wishes}\n\n"
                "तुम्ही हे ग्रीटिंग कार्ड सेव्ह करून ग्राहकांसोबत आणि मित्रांसोबत शेअर करू शकता!\n\n"
                f"{options}"
            )

    else:  # english default
        wishes = (
            f"✨ *Wishing you, your family, and everyone at {enterprise} a very Happy and prosperous {festival_name}!* "
            f"May this festive season bring immense joy, good health, and success to you and your business. 🪔"
        )
        options = (
            "Would you like to:\n"
            "1️⃣ *Refine this card* (change your name or firm name)\n"
            "2️⃣ *Create another card* (choose another festival)\n\n"
            "Reply with *1* to refine, or *2* / the festival name to create a new card!"
        )
        if wati_delivered:
            return (
                f"🎉 Here is your personalised *{festival_name}* greeting card! 🪔\n\n"
                f"{wishes}\n\n"
                "You can now forward and share this greeting card with your customers and friends!\n\n"
                f"{options}"
            )
        else:
            return (
                f"🎉 Here is your personalised *{festival_name}* greeting card! 🪔\n\n"
                f"👉 Download & View: {image_url}\n\n"
                f"{wishes}\n\n"
                "You can save and share this greeting card with your customers and friends!\n\n"
                f"{options}"
            )


@tool("generate_festival_greeting")
async def generate_festival_greeting(
    festival: str,
    enterprise: str,
    name: str,
    number: Optional[str] = None,
    language: Optional[str] = None,
) -> str:
    """
    Creates a personalised festival greeting card image and delivers it directly to the
    user's WhatsApp chat via WATI (specifically for Dussehra, Diwali, Pongal, Ganesh Chaturthi, etc.).

    CRITICAL RULES:
    - BOTH 'enterprise' (Firm Name) and 'name' (User's Name) are STRICTLY MANDATORY.
    - NEVER call this tool until BOTH Firm Name and User's Name have been explicitly provided by the user.
    - If the user has not yet provided their Firm Name and Name, you MUST ask the user for them first before calling this tool.

    Parameters:
    - festival (string, required): Festival name (e.g. 'Dussehra', 'Diwali', 'Pongal', 'Ganesh Chaturthi').
    - enterprise (string, required): Business, shop, or firm name to print on the card (MANDATORY).
    - name (string, required): User's full name to print on the card (MANDATORY).
    - number (string, optional): Mobile number to send to and print on the card.
    - language (string, optional): Language for the response message ('english', 'hindi', 'hinglish', 'marathi').

    Returns:
    JSON string with "status": "success", "message", and details.
    """
    logger.info(f"[GREETING TOOL] festival={festival} | enterprise={enterprise} | name={name} | number={number} | language={language}")

    from greeting_renderer.layout import clean_text, to_title_camel_case
    clean_enterprise = clean_text(enterprise)
    clean_name = to_title_camel_case(name)

    if not clean_enterprise or clean_enterprise.lower() in ("none", "null", "n/a", "undefined", ""):
        return json.dumps({
            "status": "error",
            "code": "missing_firm_name",
            "message": f"To create your personalized {festival} greeting card, please tell me your Firm / Shop Name."
        })

    if not clean_name or clean_name.lower() in ("none", "null", "n/a", "undefined", ""):
        return json.dumps({
            "status": "error",
            "code": "missing_name",
            "message": f"To create your personalized {festival} greeting card, please tell me your Full Name."
        })

    async with AsyncSessionLocal() as db:
        if not number:
            user_res = await db.scalars(select(User.mobile_number).order_by(User.id.desc()))
            number = user_res.first()

        user_lang = (language or "").lower().strip()
        if not user_lang and number:
            clean_digits = "".join(c for c in str(number) if c.isdigit())
            user_stmt = select(User).where(User.mobile_number.like(f"%{clean_digits[-10:]}%")).order_by(User.id.desc())
            user_res = await db.scalars(user_stmt)
            user_obj = user_res.first()
            if user_obj:
                conv_stmt = select(Conversation).where(Conversation.user_id == user_obj.id).order_by(Conversation.id.desc())
                conv_res = await db.scalars(conv_stmt)
                conv_obj = conv_res.first()
                if conv_obj and conv_obj.language:
                    user_lang = conv_obj.language.lower().strip()

        if user_lang not in ("hindi", "hinglish", "marathi"):
            user_lang = "english"

        live = await live_templates(db)
        labels = [t.festival.label for t in live if t.festival]

        fest_res = await db.scalars(select(Festival))
        matched_festival = match(festival or "", list(fest_res.all()))

        # Smart fallback: if festival is generic (like 'fest', 'festival', 'card', 'greeting') or matching failed,
        # seamlessly default to the currently active festival template (e.g. Diwali)
        if matched_festival is None:
            clean_fest = (festival or "").lower().strip()
            if clean_fest in ("fest", "festival", "festive", "card", "greeting", "greetings", "wishes", "wish", "general", "any", ""):
                if live and live[0].festival:
                    matched_festival = live[0].festival
            if matched_festival is None and live:
                for t in live:
                    if t.festival and (clean_fest in t.festival.id.lower() or clean_fest in t.festival.label.lower()):
                        matched_festival = t.festival
                        break
            if matched_festival is None and live and live[0].festival:
                matched_festival = live[0].festival

        if matched_festival is None:
            available_str = f" Greetings are currently available for: {', '.join(labels)}." if labels else " No festival greetings are currently available."
            return json.dumps({
                "status": "error",
                "code": "festival_not_found",
                "message": f"Sorry, I couldn't find a greeting matching '{festival}'.{available_str}"
            })

        template = await template_for_festival(db, matched_festival.id)
        if template is None or not template.is_live:
            if live:
                template = live[0]
            else:
                available_str = f" Greetings are available for: {', '.join(labels)}." if labels else ""
                return json.dumps({
                    "status": "error",
                    "code": "no_active_template",
                    "message": f"There is no active greeting card template for {matched_festival.label} yet.{available_str}"
                })

        try:
            # 1. Render JPEG directly in memory
            card_bytes = render_template(template, {
                "name": clean_name,
                "number": number,
                "enterprise": clean_enterprise,
            })

            # 2. Also stash card for preview link fallback
            token = storage.stash_card(card_bytes)
            base_url = (greeting_settings.public_base_url or "http://localhost:8000").rstrip("/")
            image_url = f"{base_url}/api/cards/{token}.jpg"
            festival_name = matched_festival.label

            # 3. Direct WhatsApp dispatch via WATI sendSessionFile
            wati_delivered = False
            if number:
                fest_emojis = _festival_emojis(festival_name)
                if user_lang == "hindi":
                    caption_text = f"✨ शुभ {festival_name}! {fest_emojis}"
                elif user_lang == "marathi":
                    caption_text = f"✨ {festival_name}च्या हार्दिक शुभेच्छा! {fest_emojis}"
                else:
                    caption_text = f"✨ Happy {festival_name}! {fest_emojis}"

                wati_result = await send_session_image(
                    file_bytes=card_bytes,
                    file_name=f"{matched_festival.id}_greeting.jpg",
                    phone=number,
                    caption=caption_text,
                )
                wati_delivered = bool(wati_result.get("ok"))
                logger.info(f"[GREETING TOOL WATI] delivered={wati_delivered} | phone={number}")

            reply_message = _format_greeting_reply(
                festival_name=festival_name,
                enterprise=clean_enterprise,
                name=clean_name,
                wati_delivered=wati_delivered,
                image_url=image_url,
                language=user_lang,
            )

            return json.dumps({
                "status": "success",
                "image_url": image_url,
                "festival": festival_name,
                "template_name": template.name,
                "wati_delivered": wati_delivered,
                "message": reply_message,
            })
        except Exception as exc:
            logger.error(f"[GREETING TOOL ERROR] {str(exc)}", exc_info=True)
            return json.dumps({
                "status": "error",
                "message": "Sorry, I couldn't create your greeting card right now. Please try again in a moment."
            })
