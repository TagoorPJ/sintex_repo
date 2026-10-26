from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import AzureChatOpenAI
from langchain_community.callbacks.manager import get_openai_callback
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode, create_react_agent, tools_condition
from openai import BadRequestError
from typing_extensions import TypedDict

# from app.prompt_library.prompt import SYSTEM_PROMPT
from app.tools.user_info_tool import submit_user_registration
from app.utils.helpers import truncate_messages, get_current_time_str
from app.utils.logger import get_logger
from app.utils.token_tracker import TokenUsage, log_token_usage
from app.tools.rewards_tool import rewards_tool
from app.tools.reward_statement_tool import reward_statement_tool
from app.tools.find_dealer_tool import find_dealer_tool
from app.tools.create_claim_tool import create_claim_tool
from app.tools.claim_status_tool import claim_status_tool
from app.tools.support_ticket_tool import support_ticket_tool
from app.tools.sintex_rag_tool import sintex_rag_tool
from app.tools.greeting_tool import generate_festival_greeting
from app.prompt_library.prompt_selector import get_system_prompt

load_dotenv()
logger = get_logger(__name__)


# ───────────────────────────────────────────────────────────────
# LANGUAGE CONFIG
# ───────────────────────────────────────────────────────────────

LANGUAGE_INSTRUCTIONS = {
    "hindi": (
        "हिंदी में जवाब दें। "
        "सरल, बोलचाल की हिंदी इस्तेमाल करें जैसे WhatsApp पर बात होती है। "
        "संस्कृत या किताबी शब्द मत इस्तेमाल करें।"
    ),
    "marathi": (
        "मराठीत उत्तर द्या। "
        "सोपी, बोलण्याची मराठी वापरा जसे WhatsApp वर बोलतात। "
        "अवघड किंवा साहित्यिक शब्द टाळा।"
    ),
    "hinglish": (
        "Hinglish mein jawab do — natural Hindi aur English ka mix, "
        "jaise WhatsApp pe baat karte hain."
    ),
    "english": (
        "Respond in English only."
    ),
}


def _build_language_enforcement_block(preferred_language: str) -> str:
    lang = preferred_language.lower().strip()
    lang_instruction = LANGUAGE_INSTRUCTIONS.get(lang, "Respond in English only.")

    return f"""ABSOLUTE LANGUAGE RULE — HIGHEST PRIORITY:

The user's chosen language is: {lang.upper()}

YOU MUST RESPOND ONLY IN {lang.upper()}.
This rule overrides everything — including the language the user typed in.
Even if the user writes in English or any other language, your reply MUST be in {lang.upper()} only.
Do NOT write even a single word in any other language.

{lang_instruction}"""


def _build_dealer_flow_instruction(dealer_flow_stage: str) -> str:
    if dealer_flow_stage == "awaiting_dealer_name":
        return """
╔══════════════════════════════════════════════════════════════╗
║          DEALER FLOW STATE: AWAITING DEALER NAME             ║
╠══════════════════════════════════════════════════════════════╣
║  find_dealer_tool MODE 1 has already been called.            ║
║  The dealer list is cached in memory.                        ║
║                                                              ║
║  YOUR ONLY JOB RIGHT NOW:                                    ║
║  Ask the user to type their dealer firm name.                ║
║                                                              ║
║  ❌ Do NOT call any tool yet.                                ║
║  ❌ Do NOT call MODE 2 yet.                                  ║
║  ❌ Do NOT ask for anything else.                            ║
║  ✅ Wait for the user to send their dealer name text.        ║
╚══════════════════════════════════════════════════════════════╝
"""

    elif dealer_flow_stage == "awaiting_serial_selection":
        return """
╔══════════════════════════════════════════════════════════════╗
║       DEALER FLOW STATE: AWAITING SERIAL SELECTION           ║
╠══════════════════════════════════════════════════════════════╣
║  find_dealer_tool MODE 2 has already been called.            ║
║  A numbered dealer list has already been shown to the user.  ║
║                                                              ║
║  CRITICAL RULES — MUST FOLLOW:                               ║
║  ✅ The user's NEXT reply IS their serial number choice.     ║
║  ✅ Call find_dealer_tool with selected_serial = user reply. ║
║                                                              ║
║  ❌ Do NOT ask for dealer name again.                        ║
║  ❌ Do NOT call MODE 2 (search_name) again.                  ║
║  ❌ Do NOT re-show the dealer list.                          ║
║  ❌ Do NOT treat the user's number as a main menu selection. ║
║  ❌ Do NOT treat the user's number as a submenu selection.   ║
╚══════════════════════════════════════════════════════════════╝
"""

    elif dealer_flow_stage == "dealer_selected":
        return """
╔══════════════════════════════════════════════════════════════╗
║            DEALER FLOW STATE: DEALER SELECTED                ║
╠══════════════════════════════════════════════════════════════╣
║  Dealer has been confirmed. dealer_code is available.        ║
║                                                              ║
║  ✅ Proceed to the next step (QR link or create claim).      ║
║  ❌ Do NOT ask for dealer name again.                        ║
║  ❌ Do NOT call MODE 1 or MODE 2 again.                      ║
╚══════════════════════════════════════════════════════════════╝
"""

    return ""


# ───────────────────────────────────────────────────────────────
# STATE
# ───────────────────────────────────────────────────────────────

class ChatState(TypedDict, total=False):
    messages: List[Any]
    conversation_id: str
    token_usage: Dict[str, int]
    flow: str
    collected_data: Dict[str, Any]
    user_id_evolve: Optional[int]


# ───────────────────────────────────────────────────────────────
# ORCHESTRATOR
# ───────────────────────────────────────────────────────────────

class ChatbotOrchestrator:

    def __init__(self) -> None:
        logger.info("Initializing ChatbotOrchestrator...")

        self.api_key = os.getenv("AZURE_OPENAI_API_KEY")
        self.base_url = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.azure_model = os.getenv("AZURE_OPENAI_MODEL")
        self.api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.3"))

        self.llm = self._load_llm()

        self.tools = [
            submit_user_registration,
            rewards_tool,
            reward_statement_tool,
            find_dealer_tool,
            create_claim_tool,
            claim_status_tool,
            support_ticket_tool,
            sintex_rag_tool,
            generate_festival_greeting,
        ]

        self.checkpointer = MemorySaver()
        self.graph = None

        logger.info("ChatbotOrchestrator initialized.")

    def _load_llm(self) -> AzureChatOpenAI:
        return AzureChatOpenAI(
            api_key=self.api_key,
            azure_endpoint=self.base_url,
            azure_deployment=self.azure_model,
            api_version=self.api_version,
            temperature=self.temperature,
            streaming=False,
        )

    def _build_graph(self):
        self.agent = create_react_agent(self.llm, self.tools)
        tool_node = ToolNode(tools=self.tools)

        graph = StateGraph(ChatState)

        graph.add_node("agent", self._agent_node)
        graph.add_node("tools", tool_node)

        graph.add_edge(START, "agent")
        graph.add_conditional_edges("agent", tools_condition)
        graph.add_conditional_edges("tools", lambda state: "agent", {"agent": "agent"})

        return graph.compile(checkpointer=self.checkpointer)

    # ───────────────────────────────────────────────────────────
    # AGENT NODE
    # ───────────────────────────────────────────────────────────

    async def _agent_node(self, state: ChatState) -> Dict[str, Any]:

        conv_id = state.get("conversation_id", "UNKNOWN")
        messages = state.get("messages", [])

        flow = state.get("flow", "default")
        collected_data = state.get("collected_data", {}) or {}

        current_time = get_current_time_str()

        preferred_language = (collected_data.get("language") or "english").lower().strip()
        is_registered = collected_data.get("is_registered", False)
        conversation_stage = collected_data.get("conversation_stage", "UNKNOWN")
        is_session_resumed = collected_data.get("is_session_resumed", False)
        dealer_flow_stage = collected_data.get("dealer_flow_stage", "")

        attachment_val = collected_data.get("attachment")
        logger.info(
            f"[AGENT NODE] conv={conv_id} | language={preferred_language} | "
            f"registered={is_registered} | stage={conversation_stage} | "
            f"dealer_flow_stage={dealer_flow_stage} | attachment={attachment_val!r}"
        )

        # ── RESUME INSTRUCTION ───────────────────────────────────────────────
        resume_instruction = ""

        if is_session_resumed:
            if conversation_stage == "registration_flow":
                resume_instruction = """
SESSION RESUMED:
User is returning after inactivity.
They are in the middle of registration.
You MUST:
- Start with "Welcome back!" (in the preferred language)
- Continue registration from where it left off
- Do NOT restart
"""
            elif is_registered:
                resume_instruction = """
SESSION RESUMED:
User is returning after inactivity.
You MUST:
- Ignore previous conversation context
- Immediately show MAIN MENU (in the preferred language)
- Do NOT continue previous discussion
"""

        # ── DEALER FLOW STATE INSTRUCTION ────────────────────────────────────
        dealer_flow_instruction = _build_dealer_flow_instruction(dealer_flow_stage)
        base_prompt = get_system_prompt(preferred_language)

        system_message = SystemMessage(
            content=base_prompt + f"""

[CURRENT_DATETIME]: {current_time}

[FLOW]: {flow}
[COLLECTED_DATA]: {json.dumps(collected_data)}

IMPORTANT CONTEXT:
- Preferred Language: {preferred_language}
- User Registered: {is_registered}
- Conversation Stage: {conversation_stage}
- Dealer Flow Stage: {dealer_flow_stage}

{resume_instruction}

{dealer_flow_instruction}
"""
        )

        language_enforcement_message = SystemMessage(
            content=_build_language_enforcement_block(preferred_language)
        )

        force_menu = collected_data.get("force_menu", False)
        force_registration_resume = collected_data.get("force_registration_resume", False)

        # ── BUILD FINAL MESSAGE LIST ─────────────────────────────────────────
        # Language enforcement goes at the END so it is the last instruction
        # the LLM reads before generating — prevents it from mirroring the
        # user's input language when the user writes in a different language.
        if force_menu:
            final_messages = [system_message, language_enforcement_message]
        elif force_registration_resume:
            final_messages = [system_message] + messages + [language_enforcement_message]
        else:
            final_messages = [system_message] + messages + [language_enforcement_message]

        state["messages"] = final_messages

        history_count = len(messages) if not force_menu else 0
        user_turns = sum(1 for m in messages if isinstance(m, HumanMessage)) if not force_menu else 0
        ai_turns = sum(1 for m in messages if isinstance(m, AIMessage)) if not force_menu else 0
        tool_turns = sum(1 for m in messages if isinstance(m, ToolMessage)) if not force_menu else 0
        logger.info(
            f"[LLM CONTEXT] conv={conv_id} | passing {history_count} history turns "
            f"(user={user_turns}, assistant={ai_turns}, tool={tool_turns}) | "
            f"total_messages={len(final_messages)} (including system instructions)"
        )

        try:
            with get_openai_callback() as cb:
                result = await self.agent.ainvoke({"messages": state["messages"]})

            state["token_usage"] = {
                "prompt": cb.prompt_tokens,
                "completion": cb.completion_tokens,
                "total": cb.total_tokens,
            }
            log_token_usage(conv_id, TokenUsage(
                prompt=cb.prompt_tokens,
                completion=cb.completion_tokens,
                total=cb.total_tokens,
            ))

        except BadRequestError:
            return {
                "messages": [AIMessage(content="⚠️ Request blocked. Please rephrase.")]
            }

        except Exception as e:
            logger.error(f"Agent error: {str(e)}")
            raise

        return {
            "messages": result.get("messages", []),
            "token_usage": state.get("token_usage", {})
        }

    # ───────────────────────────────────────────────────────────
    # TOOL TRACE EXTRACTION
    # ───────────────────────────────────────────────────────────

    def _extract_tool_traces(self, messages: List[Any]) -> List[Dict[str, Any]]:
        """
        Extracts tool call/result pairs from the message list.
        Resolves tool_name on ToolMessage via tool_call_id lookup from
        AIMessage.tool_calls — reliable because LangChain does not always
        populate ToolMessage.name.
        """
        # Build tool_call_id → tool_name map from AIMessage tool_calls
        tool_call_id_to_name: Dict[str, str] = {}
        for msg in messages:
            if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                for tool_call in msg.tool_calls:
                    call_id = tool_call.get("id", "")
                    name = tool_call.get("name", "")
                    if call_id:
                        tool_call_id_to_name[call_id] = name

        traces = []

        for msg in messages:
            if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                for tool_call in msg.tool_calls:
                    traces.append({
                        "type": "tool_call",
                        "tool_name": tool_call.get("name"),
                        "input": tool_call.get("args"),
                    })

            if isinstance(msg, ToolMessage):
                # Resolve tool_name via tool_call_id — always correct
                tool_call_id = getattr(msg, "tool_call_id", "") or ""
                resolved_tool_name = (
                    tool_call_id_to_name.get(tool_call_id, "")
                    or getattr(msg, "name", "")
                )

                try:
                    parsed = json.loads(msg.content)
                except Exception:
                    parsed = msg.content

                traces.append({
                    "type": "tool_result",
                    "tool_name": resolved_tool_name,
                    "output": parsed,
                })

        return traces

    # ───────────────────────────────────────────────────────────
    # PUBLIC API
    # ───────────────────────────────────────────────────────────

    async def stream_response(
        self,
        conversation_id: int,
        user_message: str,
        history: List[Dict[str, str]],
        flow: str = "default",
        prefill: Dict[str, Any] = None,
    ) -> Dict[str, Any]:

        logger.info("stream_response called")

        if not self.graph:
            self.graph = self._build_graph()

        lc_messages = _build_langchain_messages(history)
        lc_messages.append(HumanMessage(content=user_message))
        lc_messages = truncate_messages(lc_messages, max_count=25)

        # ── Attachment notification (informational only) ─────────────────
        # Let the LLM know an attachment is present via COLLECTED_DATA.
        # The support ticket prompt handles this in STEP 4 — the LLM checks
        # COLLECTED_DATA["attachment"] only AFTER the photo question has been
        # asked and the user has replied. We do NOT force an immediate tool
        # call here; doing so caused the tool to fire with stale history data
        # before the category and description steps were completed.
        attachment = (prefill or {}).get("attachment") or ""
        if attachment:
            lc_messages.append(SystemMessage(
                content=(
                    f"[ATTACHMENT PRESENT IN THIS REQUEST]: {attachment}\n\n"
                    "This value is also in COLLECTED_DATA[\"attachment\"].\n"
                    "Follow the Support Ticket Flow steps in order. Only use this "
                    "attachment when you reach STEP 4 (after the photo question has "
                    "been asked and the user has responded). Do NOT skip steps."
                )
            ))

        initial_state: ChatState = {
            "messages": lc_messages,
            "conversation_id": str(conversation_id),
            "token_usage": {},
            "flow": flow,
            "collected_data": prefill or {},
        }

        try:
            final_state = await self.graph.ainvoke(
                initial_state,
                config={"configurable": {"thread_id": str(conversation_id)}}
            )

        except Exception:
            logger.error("Graph failed", exc_info=True)
            return {
                "response": "⚠️ Something went wrong.",
                "tool_traces": [],
                "is_complete": False,
            }

        all_messages = final_state.get("messages", [])

        response_text = _extract_last_ai_message(all_messages)
        is_complete = _detect_completion(all_messages)

        tool_traces = self._extract_tool_traces(all_messages)

        if tool_traces:
            for trace in tool_traces:
                if trace["type"] == "tool_call":
                    logger.info(
                        f"[TOOL CALL] {trace['tool_name']} | input={trace['input']}"
                    )
                elif trace["type"] == "tool_result":
                    logger.info(
                        f"[TOOL RESULT] tool={trace['tool_name']} | output={trace['output']}"
                    )

        token_usage = final_state.get("token_usage", {}) or {}

        return {
            "response": response_text,
            "tool_traces": tool_traces,
            "is_complete": is_complete,
            "token_usage": {
                "prompt": token_usage.get("prompt", 0),
                "completion": token_usage.get("completion", 0),
                "total": token_usage.get("total", 0),
            },
        }


# ───────────────────────────────────────────────────────────────
# HELPERS
# ───────────────────────────────────────────────────────────────

def _build_langchain_messages(history: List[Dict[str, str]]) -> List[BaseMessage]:
    messages = []
    for item in history:
        if item["sender"] == "user":
            messages.append(HumanMessage(content=item["message"]))
        elif item["sender"] == "assistant":
            messages.append(AIMessage(content=item["message"]))
        elif item["sender"] == "tool":
            messages.append(ToolMessage(content=item["message"], tool_call_id="history"))
    return messages


def _extract_last_ai_message(messages: List[Any]) -> str:
    """
    Priority Response Selector:

    1. find_dealer_tool MODE 2 result (dealer list) — show directly so the
       numbered list is never swallowed/summarised by the LLM.
    2. reward_statement_tool result — show directly.
    3. Final AI text response (no tool_calls pending).
    4. Fallback: any tool output.
    """

    # Tools whose message field must be shown directly to the user,
    # bypassing the LLM's tendency to paraphrase or summarise.
    DIRECT_TOOL_RESPONSE_TOOLS = {"reward_statement_tool", "generate_festival_greeting"}

    # ── Build tool_call_id → tool_name map so we can identify ToolMessages ──
    tool_call_id_to_name: Dict[str, str] = {}
    for msg in messages:
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                if tc.get("id"):
                    tool_call_id_to_name[tc["id"]] = tc.get("name", "")

    # ── STEP 1: find_dealer_tool MODE 2 — always show the numbered list directly ──
    # Walk in reverse to find the most recent find_dealer_tool result whose
    # dealer_flow_stage is "awaiting_serial_selection" (i.e. MODE 2 output).
    for msg in reversed(messages):
        if not isinstance(msg, ToolMessage):
            continue

        tool_call_id = getattr(msg, "tool_call_id", "") or ""
        tool_name = (
            tool_call_id_to_name.get(tool_call_id, "")
            or getattr(msg, "name", "")
        )

        if tool_name != "find_dealer_tool":
            continue

        try:
            data = json.loads(msg.content)
        except Exception:
            continue

        if not isinstance(data, dict):
            continue

        # Only intercept MODE 2 output (the numbered dealer list)
        if data.get("dealer_flow_stage") == "awaiting_serial_selection":
            direct_message = data.get("message", "")
            if direct_message:
                logger.info(
                    f"[FIND DEALER MODE 2 DIRECT RESPONSE] Showing dealer list directly"
                )
                return direct_message

    # ── STEP 2: Other direct-response tools (e.g. reward_statement_tool) ────
    for msg in reversed(messages):
        if not isinstance(msg, ToolMessage):
            continue

        tool_call_id = getattr(msg, "tool_call_id", "") or ""
        tool_name = (
            tool_call_id_to_name.get(tool_call_id, "")
            or getattr(msg, "name", "")
        )

        if tool_name in DIRECT_TOOL_RESPONSE_TOOLS:
            try:
                data = json.loads(msg.content)
                if isinstance(data, dict):
                    message = data.get("message", msg.content)
                    logger.info(f"[TOOL DIRECT RESPONSE] {tool_name}: {message}")
                    return message
            except Exception:
                return msg.content

    # ── STEP 3: Final AI text response ──────────────────────────────────────
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            if getattr(msg, "tool_calls", None):
                continue
            if msg.content:
                try:
                    data = json.loads(msg.content)
                    if isinstance(data, dict):
                        return data.get("message", msg.content)
                except Exception:
                    return msg.content

    # ── STEP 4: Fallback to any tool output ─────────────────────────────────
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            try:
                data = json.loads(msg.content)
                if isinstance(data, dict):
                    return data.get("message", msg.content)
            except Exception:
                return msg.content

    return "Something went wrong."


def _detect_completion(messages: List[Any]) -> bool:
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            try:
                data = json.loads(msg.content)
                if data.get("status") == "success":
                    return True
            except Exception:
                pass
    return False


# ───────────────────────────────────────────────────────────────

chatbot_orchestrator = ChatbotOrchestrator()
