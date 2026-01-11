"""API endpoints for Calendar Club discovery chat."""

import json
import os
from collections.abc import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()

app = FastAPI()

# CORS configuration from environment
ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:3000,http://localhost:3001"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_openai_client() -> OpenAI:
    """Lazy-initialize OpenAI client to allow server boot without API key."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")
    return OpenAI(api_key=api_key)


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""

    message: str
    conversation_id: str | None = None


class ConversationMessage(BaseModel):
    """A message in the conversation history."""

    role: str
    content: str


class ChatStreamRequest(BaseModel):
    """Request body for streaming chat endpoint."""

    message: str
    history: list[ConversationMessage] = []


def sse_event(event_type: str, data: dict) -> str:
    """Format a Server-Sent Event with type included in payload."""
    # Include type in the JSON payload so frontend can access it
    payload = {"type": event_type, **data}
    return f"data: {json.dumps(payload)}\n\n"


async def stream_chat_response(
    message: str, history: list[ConversationMessage]
) -> AsyncGenerator[str, None]:
    """Stream chat response using the clarifying agent."""
    try:
        from agents import Runner

        from api.agents import clarifying_agent
        from api.agents.search import search_events

        # Build conversation history for the agent
        messages = []
        for msg in history:
            messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": message})

        # Run the agent with streaming
        result = await Runner.run(
            clarifying_agent,
            messages,
        )

        # Debug logging for search handoff
        if result.final_output:
            output = result.final_output
            print(f"[DEBUG] ready_to_search: {output.ready_to_search}")
            print(f"[DEBUG] search_profile: {output.search_profile}")
            print(f"[DEBUG] full output: {output.model_dump_json(indent=2)}")

        # Stream the message content
        if result.final_output:
            output = result.final_output
            # Stream the message in chunks for responsiveness
            message_text = output.message
            for i in range(0, len(message_text), 10):
                chunk = message_text[i : i + 10]
                yield sse_event("content", {"content": chunk})

            # Send quick picks if any
            if output.quick_picks:
                quick_picks_data = [
                    {"label": qp.label, "value": qp.value} for qp in output.quick_picks
                ]
                yield sse_event("quick_picks", {"quick_picks": quick_picks_data})

            # If ready to search, actually perform the search
            if output.ready_to_search and output.search_profile:
                # Emit searching state so frontend can show searching UI
                yield sse_event("searching", {})

                # Perform the actual search
                search_result = search_events(output.search_profile)

                # Convert to frontend event format and emit
                if search_result.events:
                    events_data = [
                        {
                            "id": evt.id,
                            "title": evt.title,
                            "startTime": evt.date,
                            "location": evt.location,
                            "categories": [evt.category],
                            "url": evt.url,
                            "source": search_result.source,
                        }
                        for evt in search_result.events
                    ]
                    yield sse_event("events", {"events": events_data})

        yield sse_event("done", {})

    except Exception as e:
        yield sse_event("error", {"message": str(e)})
        yield sse_event("done", {})


@app.get("/")
def root():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/api/chat")
def chat(request: ChatRequest):
    """Non-streaming chat endpoint (legacy)."""
    client = get_openai_client()
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a friendly event discovery assistant.",
                },
                {"role": "user", "content": request.message},
            ],
        )
        return {"reply": response.choices[0].message.content}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error calling OpenAI API: {str(e)}"
        ) from e


@app.post("/api/chat/stream")
async def chat_stream(request: ChatStreamRequest):
    """Streaming chat endpoint using Server-Sent Events with LLM-orchestrated quick picks."""
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")

    return StreamingResponse(
        stream_chat_response(request.message, request.history),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
