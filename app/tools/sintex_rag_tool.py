from __future__ import annotations

import os
import json
import httpx
from dotenv import load_dotenv
from langchain.tools import tool

from app.analytics.feature_usage_tracker import record_feature_result
from app.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

RAG_API_URL = os.getenv("RAG_API_URL", "").strip()
RAG_TIMEOUT = float(os.getenv("RAG_TIMEOUT", "20"))
RAG_MAX_CHUNKS = int(os.getenv("RAG_MAX_CHUNKS", "5"))


def _json_response(status: str, message: str, data: dict | None = None) -> str:
    payload = {"status": status, "message": message}
    if data:
        payload.update(data)
    return json.dumps(payload, ensure_ascii=False)


@tool("sintex_rag_tool")
async def sintex_rag_tool(question: str) -> str:
    """
    Tool Name: sintex_rag_tool

    Purpose:
    Look up product information from official Sintex documents (FAQs,
    brochures, datasheets) to answer the user's product question.

    Use this tool whenever the user asks about:
    - Sintex products (water tanks, pipes, fittings — UPVC / CPVC / PVC / PEX)
    - Product specifications, sizes, capacities, materials
    - Installation, maintenance, compatibility, warranty
    - Which Sintex product fits a use case (hot water, drainage, drinking water, etc.)
    - Anything that sounds like a "Product Help" question (option 3 in main menu)

    Do NOT use this tool for:
    - Registration, rewards, claims, dealer search, QR scan — those have their own tools.
    - General chitchat or off-topic queries.
    - The bare main-menu pick ("3", "product help", "Product Help", "help") with no actual
      product question. In that case, FIRST ask the user what they want help with, then call
      this tool only after they reply with a real question.

    Input:
    - question (string, required): the user's question, in any language. The
      backend retriever handles language-neutral matching but works best in English.
      If the user wrote in Hindi/Marathi/Hinglish, pass the question through as-is.

    Output:
    JSON string of the form:
      {
        "status": "success",
        "message": "<concatenated relevant chunks the LLM should ground its answer on>",
        "sources": ["Sintex_Pipes_FAQ.txt", ...]
      }
    On failure:
      {"status": "error", "message": "<reason>"}

    Mandatory behavior after calling this tool:
    - The "message" field contains raw document chunks, NOT a finished reply.
    - You MUST read those chunks and write a short, friendly answer in the user's
      language, grounded ONLY in the chunks. Do not invent specs.
    - If the chunks do not contain the answer, say so honestly.
    - Keep the reply concise (3-5 lines) and end with a follow-up offer like
      "Need anything else about Sintex products?"
    """

    q = (question or "").strip()
    if not q or q.casefold() in {"1", "2", "3", "4", "product help", "help", "my rewards"}:
        return _json_response("error", "Question is required.")

    if not RAG_API_URL:
        logger.error("[sintex_rag_tool] RAG_API_URL is not configured in .env")
        return _json_response("error", "Knowledge base is not configured.")

    logger.info(f"[sintex_rag_tool] question={q!r} url={RAG_API_URL}")

    try:
        async with httpx.AsyncClient(timeout=RAG_TIMEOUT) as client:
            resp = await client.post(
                RAG_API_URL,
                json={"question": q},
                headers={"Content-Type": "application/json"},
            )
    except httpx.TimeoutException:
        logger.error("[sintex_rag_tool] timeout")
        await record_feature_result(
            "product_help.rag_search", success=False, reason="Knowledge base timed out"
        )
        return _json_response("error", "Knowledge base timed out. Please try again.")
    except Exception:
        logger.exception("[sintex_rag_tool] request failed")
        await record_feature_result(
            "product_help.rag_search", success=False, reason="Knowledge base request failed"
        )
        return _json_response("error", "Could not reach the knowledge base.")

    if resp.status_code != 200:
        logger.error(f"[sintex_rag_tool] non-200: {resp.status_code} | {resp.text[:300]}")
        await record_feature_result(
            "product_help.rag_search",
            success=False,
            reason=f"Knowledge base HTTP {resp.status_code}",
        )
        return _json_response("error", "Knowledge base returned an error.")

    try:
        data = resp.json()
    except Exception:
        logger.exception("[sintex_rag_tool] invalid JSON from RAG")
        await record_feature_result(
            "product_help.rag_search", success=False, reason="Invalid knowledge base response"
        )
        return _json_response("error", "Knowledge base returned invalid data.")

    if not isinstance(data, dict) or data.get("status") in {"error", "failed", "failure"} or data.get("success") is False:
        await record_feature_result(
            "product_help.rag_search",
            success=False,
            reason=str(data.get("message") if isinstance(data, dict) else "Invalid response"),
        )
        return _json_response("error", "Knowledge base returned an error.")

    chunks = data.get("chunks") or []
    if not isinstance(chunks, list) or any(not isinstance(chunk, dict) for chunk in chunks):
        await record_feature_result(
            "product_help.rag_search", success=False, reason="Invalid knowledge base chunks"
        )
        return _json_response("error", "Knowledge base returned invalid data.")
    if not chunks:
        # A completed search counts even when there are no matching documents.
        await record_feature_result("product_help.rag_search", success=True)
        return _json_response(
            "success",
            "No matching content found in Sintex documents.",
            {"sources": []},
        )

    chunks = chunks[:RAG_MAX_CHUNKS]

    blocks = []
    sources: list[str] = []
    for i, c in enumerate(chunks, start=1):
        text = (c.get("text") or "").strip()
        source = (c.get("source") or "").strip()
        if not text:
            continue
        blocks.append(f"[chunk {i} | source: {source}]\n{text}")
        if source and source not in sources:
            sources.append(source)

    merged = "\n\n".join(blocks)
    logger.info(
        f"[sintex_rag_tool] returned {len(blocks)} chunks | sources={sources}"
    )

    await record_feature_result("product_help.rag_search", success=True)
    return _json_response(
        "success",
        merged,
        {"sources": sources},
    )
