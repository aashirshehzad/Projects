"""
Desktop Hardware AI Researcher - FastAPI Backend Server

Headless asynchronous REST & SSE API for the LangGraph multi-agent pipeline:
- Sequential Multi-Agent Flow: Researcher -> Analyst -> Writer
- Persistent Checkpointing: Neon PostgreSQL via LangGraph AsyncPostgresSaver
- Real-time Streaming: Server-Sent Events (SSE) broadcasting agent status and live Writer LLM tokens
- Thread History & Listing: State snapshot retrieval and active threads from Neon Postgres
"""

import sys
import asyncio
import json
import os
import traceback
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, Any, Dict, List

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from dotenv import load_dotenv
import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from workflow import get_async_graph, close_async_graph

load_dotenv()


# ------------------------------------------------------------------------------
# 1. FastAPI Application Initialization & Lifespan Management
# ------------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages startup and shutdown lifecycle:
    - Preheats the AsyncConnectionPool and compiles the async LangGraph workflow.
    - Gracefully closes connection pools on server termination.
    """
    try:
        print("--- Initializing LangGraph Async Workflow & Neon Postgres Connection Pool ---")
        await get_async_graph()
        print("--- LangGraph Async Workflow Initialized Successfully ---")
    except Exception as e:
        print(f"!!! Error during graph initialization: {e} !!!")
        traceback.print_exc()

    yield

    print("--- Closing Neon Postgres Async Connection Pool ---")
    await close_async_graph()


app = FastAPI(
    title="Desktop Hardware AI Researcher API",
    description="Headless FastAPI multi-agent hardware research backend with Neon Postgres persistence & SSE streaming.",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow all origins so local React dev servers (Vite/Next.js) can connect seamlessly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------------------
# 2. Pydantic Request & Response Data Models
# ------------------------------------------------------------------------------
class ChatRequest(BaseModel):
    """
    Incoming chat request payload for the multi-agent hardware pipeline.
    """
    thread_id: str = Field(..., description="Unique conversation session UUID used for Neon Postgres checkpointing.")
    query: str = Field(..., description="User prompt or hardware query.")
    budget: str = Field(default="$1,500 USD", description="Target budget ceiling or price range.")
    use_case: str = Field(default="Gaming", description="Primary workload (Gaming, Video Editing, AI/ML, etc.).")
    resolution: str = Field(default="1440p (QHD)", description="Target display resolution (1080p, 1440p, 4K).")


class MessageItem(BaseModel):
    """Structured representation of a conversational turn."""
    type: str
    role: str
    content: str


class ThreadItem(BaseModel):
    """Thread summary item for the recent chats sidebar."""
    id: str
    title: str


class ThreadHistoryResponse(BaseModel):
    """Conversation state history response from Neon Postgres."""
    thread_id: str
    exists: bool
    messages: List[MessageItem]
    final_article: str
    final_report: str
    research_data: str
    query: str
    budget: str
    use_case: str
    resolution: str


def _extract_text(content: Any) -> str:
    """Recursively and cleanly extracts text string from any chunk, list of content blocks, or dict."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                if "text" in item:
                    text_parts.append(str(item["text"]))
                elif "content" in item:
                    text_parts.append(_extract_text(item["content"]))
            elif isinstance(item, str):
                text_parts.append(item)
            elif hasattr(item, "text"):
                text_parts.append(str(item.text))
            elif hasattr(item, "content"):
                text_parts.append(_extract_text(item.content))
        return "".join(text_parts)
    if isinstance(content, dict):
        if "text" in content:
            return str(content["text"])
        if "content" in content:
            return _extract_text(content["content"])
    if hasattr(content, "text"):
        return str(content.text)
    if hasattr(content, "content"):
        return _extract_text(content.content)
    return str(content) if content is not None else ""


# ------------------------------------------------------------------------------
# 3. Server-Sent Events (SSE) Generator Function
# ------------------------------------------------------------------------------
async def event_stream(req: ChatRequest) -> AsyncGenerator[str, None]:
    """
    Asynchronously executes the LangGraph workflow using `astream_events` (v2)
    and yields SSE events for node lifecycles (Researcher, Analyst, Writer) and live LLM tokens.
    """
    input_state = {
        "messages": [HumanMessage(content=req.query.strip())],
        "query": req.query.strip(),
        "budget": req.budget.strip(),
        "use_case": req.use_case.strip(),
        "resolution": req.resolution.strip(),
        "research_data": "",
        "final_report": "",
        "final_article": "",
    }

    config = {"configurable": {"thread_id": req.thread_id}}

    try:
        graph = await get_async_graph()
        print(f"--- STARTING GRAPH EXECUTION FOR THREAD: {req.thread_id} ---")
        async for event in graph.astream_events(input_state, config=config, version="v2"):
            kind = event["event"]
            node = event.get("metadata", {}).get("langgraph_node", "").lower()
            raw_node = event.get("metadata", {}).get("langgraph_node", "")

            # 1. Capture node lifecycle transitions
            if kind == "on_chain_start" and raw_node:
                status_payload = {
                    "type": "status",
                    "node": raw_node,
                    "status": "running",
                    "message": f"Agent '{raw_node}' started execution...",
                }
                yield f"data: {json.dumps(status_payload)}\n\n"

            elif kind == "on_chain_end" and raw_node:
                status_payload = {
                    "type": "status",
                    "node": raw_node,
                    "status": "completed",
                    "message": f"Agent '{raw_node}' finished execution.",
                }
                yield f"data: {json.dumps(status_payload)}\n\n"

            # 2. Capture live streaming tokens specifically from Writer LLM
            if kind == "on_chat_model_stream" and node == "writer":
                raw_chunk = event.get("data", {}).get("chunk")
                content = getattr(raw_chunk, "content", raw_chunk)
                extracted_token = _extract_text(content)
                if extracted_token:
                    yield f"data: {json.dumps({'type': 'token', 'content': extracted_token})}\n\n"

            # 3. Extract and log token usage metadata directly from LLM completions
            elif kind == "on_chat_model_end":
                active_node = raw_node or node or "Agent"
                try:
                    usage = event["data"]["output"].usage_metadata
                    if usage:
                        in_tok = usage.get("input_tokens", 0)
                        out_tok = usage.get("output_tokens", 0)
                        print(f"[TOKEN USAGE] {active_node.capitalize()} | Input: {in_tok} | Output: {out_tok} | Total: {in_tok + out_tok}")
                except (KeyError, AttributeError):
                    pass

        # Signal successful completion of the entire multi-agent pipeline
        print("--- GRAPH EXECUTION COMPLETE ---")
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except Exception as e:
        print(f"!!! STREAM ERROR: {repr(e)} !!!")
        traceback.print_exc()
        error_payload = {
            "type": "error",
            "error": str(e) or repr(e),
        }
        yield f"data: {json.dumps(error_payload)}\n\n"


# ------------------------------------------------------------------------------
# 4. API Endpoints
# ------------------------------------------------------------------------------
@app.get("/")
@app.get("/api")
async def api_root():
    """Root endpoint providing API metadata and links to documentation."""
    return {
        "status": "ok",
        "service": "Desktop Hardware AI Researcher API",
        "docs_url": "/docs",
        "endpoints": {
            "health": "GET /health",
            "threads": "GET /api/chat/threads",
            "chat_stream": "POST /api/chat/stream",
            "chat_history": "GET /api/chat/history/{thread_id}",
        },
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for container / server monitoring."""
    return {
        "status": "ok",
        "service": "desktop-hardware-research-agent",
        "neon_configured": bool(os.environ.get("NEON_DATABASE_URL")),
    }


@app.get("/api/chat/threads", response_model=List[ThreadItem])
async def get_chat_threads():
    """
    Retrieves all conversation thread IDs from Neon Postgres checkpoints,
    ordered by latest update, with extracted titles from the first user message.
    """
    neon_uri = os.environ.get("NEON_DATABASE_URL")
    if not neon_uri:
        return []

    threads: List[ThreadItem] = []
    try:
        graph = await get_async_graph()
        async with await psycopg.AsyncConnection.connect(neon_uri) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT thread_id FROM checkpoints GROUP BY thread_id ORDER BY MAX(checkpoint->>'ts') DESC;"
                )
                rows = await cur.fetchall()
                for (tid,) in rows:
                    title = "Hardware Inquiry"
                    try:
                        state_snapshot = await graph.aget_state({"configurable": {"thread_id": tid}})
                        if state_snapshot and state_snapshot.values:
                            values = state_snapshot.values
                            raw_messages = values.get("messages", [])
                            found_user_msg = False
                            if isinstance(raw_messages, list):
                                for msg in raw_messages:
                                    msg_type = getattr(msg, "type", "")
                                    if msg_type == "human" or getattr(msg, "role", "") == "user":
                                        content = str(getattr(msg, "content", "")).strip()
                                        if content:
                                            title = content[:30]
                                            found_user_msg = True
                                            break
                            if not found_user_msg and values.get("query"):
                                title = str(values.get("query")).strip()[:30]
                    except Exception:
                        pass
                    threads.append(ThreadItem(id=tid, title=title))
        return threads
    except Exception as ex:
        print(f"Error fetching threads from Neon: {ex}")
        return []


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """
    Primary conversational streaming endpoint using Server-Sent Events (SSE).
    Streams node lifecycle updates (Researcher -> Analyst -> Writer) and real-time LLM tokens.
    """
    return StreamingResponse(
        event_stream(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/chat/history/{thread_id}", response_model=ThreadHistoryResponse)
async def get_chat_history(thread_id: str):
    """
    Retrieves full conversational history and persisted LangGraph state from Neon Postgres for a given thread_id.
    """
    try:
        graph = await get_async_graph()
        state_snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id}})
        if not state_snapshot or not state_snapshot.values:
            return ThreadHistoryResponse(
                thread_id=thread_id,
                exists=False,
                messages=[],
                final_article="",
                final_report="",
                research_data="",
                query="",
                budget="",
                use_case="",
                resolution="",
            )

        values = state_snapshot.values
        raw_messages = values.get("messages", [])

        formatted_messages: List[MessageItem] = []
        if isinstance(raw_messages, list):
            for msg in raw_messages:
                msg_type = getattr(msg, "type", "unknown")
                role = "user" if msg_type == "human" or isinstance(msg, HumanMessage) else "assistant"
                raw_content = getattr(msg, "content", "")
                content = _extract_text(raw_content)
                formatted_messages.append(
                    MessageItem(
                        type=msg_type,
                        role=role,
                        content=content,
                    )
                )

        return ThreadHistoryResponse(
            thread_id=thread_id,
            exists=True,
            messages=formatted_messages,
            final_article=str(values.get("final_article") or ""),
            final_report=str(values.get("final_report") or ""),
            research_data=str(values.get("research_data") or ""),
            query=str(values.get("query") or ""),
            budget=str(values.get("budget") or ""),
            use_case=str(values.get("use_case") or ""),
            resolution=str(values.get("resolution") or ""),
        )

    except Exception as ex:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve thread history for '{thread_id}' from Neon Postgres: {str(ex)}",
        )


@app.delete("/api/chat/threads/{thread_id}")
async def delete_chat_thread(thread_id: str):
    """
    Deletes a conversation thread and its associated checkpoint history from Neon Postgres.
    """
    neon_uri = os.environ.get("NEON_DATABASE_URL")
    if not neon_uri:
        return {"status": "success", "message": "No database configured."}

    try:
        async with await psycopg.AsyncConnection.connect(neon_uri, autocommit=True) as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM checkpoint_writes WHERE thread_id = %s;", (thread_id,))
                await cur.execute("DELETE FROM checkpoint_blobs WHERE thread_id = %s;", (thread_id,))
                await cur.execute("DELETE FROM checkpoints WHERE thread_id = %s;", (thread_id,))
        return {"status": "success", "thread_id": thread_id}
    except Exception as ex:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete thread '{thread_id}' from Neon Postgres: {str(ex)}",
        )


# ------------------------------------------------------------------------------
# 5. Local Execution Runner
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
