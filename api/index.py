from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from openai import OpenAI
import os
import json
from dotenv import load_dotenv

from api.services import CalendarEvent, create_ics_event, create_ics_multiple

load_dotenv()

app = FastAPI()

# CORS so the frontend can talk to backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

def get_openai_client() -> OpenAI:
    """Lazy-initialize OpenAI client to allow server boot without API key."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")
    return OpenAI(api_key=api_key)


class ChatRequest(BaseModel):
    message: str


class ChatStreamRequest(BaseModel):
    session_id: str
    message: str


@app.get("/")
def root():
    return {"status": "ok"}


@app.post("/api/chat")
def chat(request: ChatRequest):
    client = get_openai_client()
    try:
        user_message = request.message
        response = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": "You are a supportive mental coach."},
                {"role": "user", "content": user_message}
            ]
        )
        return {"reply": response.choices[0].message.content}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calling OpenAI API: {str(e)}")


def generate_stream(session_id: str, message: str):
    """Generator for SSE stream from OpenAI."""
    try:
        client = get_openai_client()
        stream = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful event discovery assistant for Calendar Club. "
                        "Help users find local events based on their interests, "
                        "preferred times, and location. Be concise and friendly."
                    ),
                },
                {"role": "user", "content": message},
            ],
            stream=True,
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                data = {
                    "type": "content",
                    "content": chunk.choices[0].delta.content,
                    "session_id": session_id,
                }
                yield f"data: {json.dumps(data)}\n\n"

        # Send completion signal
        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"

    except Exception as e:
        error_data = {"type": "error", "error": str(e), "session_id": session_id}
        yield f"data: {json.dumps(error_data)}\n\n"


@app.post("/api/chat/stream")
def chat_stream(request: ChatStreamRequest):
    """SSE streaming endpoint for chat."""
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")

    return StreamingResponse(
        generate_stream(request.session_id, request.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class ExportEventsRequest(BaseModel):
    events: list[CalendarEvent]


@app.post("/api/calendar/export")
def export_calendar(event: CalendarEvent):
    """Export a single event as ICS file."""
    ics_content = create_ics_event(event)
    filename = f"{event.title.replace(' ', '-').lower()}.ics"

    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/calendar/export-multiple")
def export_calendar_multiple(request: ExportEventsRequest):
    """Export multiple events as a single ICS file."""
    if not request.events:
        raise HTTPException(status_code=400, detail="No events provided")

    ics_content = create_ics_multiple(request.events)

    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="calendar-club-events.ics"'},
    )
