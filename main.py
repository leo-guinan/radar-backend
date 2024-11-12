from urllib.request import Request
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from uuid import UUID, uuid4
from datetime import datetime
import os
import asyncpg
from dotenv import load_dotenv
import re
from bs4 import BeautifulSoup
import requests
import ell
from urllib.parse import urlparse
import json
import logging

load_dotenv()

app = FastAPI()
@app.middleware("http")
async def debug_middleware(request: Request, call_next):
    print(f"Request headers: {request.headers}")
    response = await call_next(request)
    print(f"Response headers: {response.headers}")
    return response

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Change this to False if using wildcard
    allow_methods=["*"],
    allow_headers=["*"],
)
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database connection pool
async def get_db_pool():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL not set")
        raise HTTPException(status_code=500, detail="Database configuration error")
    logger.info(f"Connecting to database at: {db_url.split('@')[-1]}")  # Log host/port, not credentials
    return await asyncpg.create_pool(db_url)

# Models
class AnalyzeRequest(BaseModel):
    url: str
    initialThought: str

class ShareRequest(BaseModel):
    conversationId: UUID

class Message(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    timestamp: datetime

class ShareResponse(BaseModel):
    shareUrl: str

# Structured Output Models
class WorldModel(BaseModel):
    context: Optional[Dict[str, str]] = Field(default_factory=dict, description="Key concepts and their current understanding")
    topics: List[str] = Field(default_factory=list, description="Main topics being discussed")
    questions: List[str] = Field(default_factory=list, description="Open questions to explore")
    summary: str = Field(description="Current summary of the discussion")

class AnalysisResponse(BaseModel):
    world_model: WorldModel = Field(description="The current state of understanding")
    response: str = Field(description="The response to the user")
    follow_up: str = Field(description="A follow-up question to continue the conversation")

class ConversationUpdate(BaseModel):
    updated_world_model: WorldModel = Field(description="The updated state of understanding")
    response: str = Field(description="The response to the user")
    follow_up: str = Field(description="A follow-up question to continue the conversation")
    referenced_content: Optional[str] = Field(description="Any new content that was referenced")

# Initialize ell
if os.getenv("ENV") != "prod":
    ell.init(store='./ell_store', autocommit=True)

JINA_READER_URL = "https://r.jina.ai/"
# Media processing functions
def is_youtube_url(url: str) -> bool:
    youtube_regex = r'(youtube\.com|youtu\.be)'
    return bool(re.search(youtube_regex, url))

def is_podcast_url(url: str) -> bool:
    return urlparse(url).path.lower().endswith('.mp3')

async def process_webpage(url: str) -> str:
    try:
        response = requests.get(JINA_READER_URL + url,)
        soup = BeautifulSoup(response.text, 'html.parser')
        return soup.get_text(strip=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process webpage: {str(e)}")

async def process_youtube(url: str) -> str:
    # TODO: Implement actual YouTube transcription
    return f"Placeholder: YouTube video transcript for {url}"

async def process_podcast(url: str) -> str:
    # TODO: Implement actual podcast transcription
    return f"Placeholder: Podcast transcript for {url}"

async def process_media(url: str) -> dict:
    if is_youtube_url(url):
        content = await process_youtube(url)
        media_type = "video"
    elif is_podcast_url(url):
        content = await process_podcast(url)
        media_type = "podcast"
    else:
        content = await process_webpage(url)
        media_type = "webpage"
        
    return {"type": media_type, "content": content}

# LLM integration using ell
@ell.complex(model="gpt-4o-mini", response_format=AnalysisResponse)
def analyze_content(content: str, initial_thought: str) -> AnalysisResponse:
    """You are an expert analyst. Your task is to:
    1. Analyze the provided content
    2. Consider the user's initial thought
    3. Create a comprehensive world model that tracks:
       - Key concepts and their current understanding
       - Main topics being discussed
       - Open questions to explore
       - Current summary of the discussion
    4. Provide an engaging response that shows understanding
    5. Ask a relevant follow-up question
    """
    return [
        ell.system("You are an expert analyst creating a structured analysis from content and user insights."),
        ell.user([
            "Content:", content,
            "\nUser's Initial Thought:", initial_thought,
            "\nCreate a structured analysis with world model, response, and follow-up question."
        ])
    ]

@ell.complex(model="gpt-4o-mini", response_format=ConversationUpdate)
def continue_conversation(
    current_world_model: WorldModel,
    message_history: list,
    new_content: Optional[str] = None
) -> ConversationUpdate:
    """You are an expert analyst continuing a conversation about analyzed content.
    1. Use the world model as context
    2. Update the world model based on new insights
    3. If new content is provided, incorporate it into your analysis
    4. Provide an engaging response that builds on previous context
    5. Ask a relevant follow-up question
    """
    prompt = [
        ell.system("You are an expert analyst continuing a structured conversation."),
        ell.user([
            "Current World Model:", json.dumps(current_world_model.dict(), indent=2),
            "\nMessage History:\n" + "\n".join([
                f"{msg['role']}: {msg['content']}" for msg in message_history
            ])
        ])
    ]
    
    if new_content:
        prompt.append(ell.user(f"New content to analyze:\n{new_content}"))
    
    return prompt

@app.post("/api/analyze")
async def analyze_media(request: AnalyzeRequest):
    logger.info(f"Starting analysis for URL: {request.url}")
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            # Process media
            logger.info("Processing media content...")
            processed_content = await process_media(request.url)
            logger.info(f"Media processed. Type: {processed_content['type']}")
            
            # Get AI analysis using ell
            logger.info("Getting AI analysis...")
            analysis_response = analyze_content(processed_content["content"], request.initialThought)
            
            # Extract structured response
            analysis_data = analysis_response.parsed
            logger.info("AI analysis completed with structured output")
            
            # Create conversation
            conversation_id = uuid4()
            logger.info(f"Creating conversation with ID: {conversation_id}")
            
            # Store the world model and conversation data
            await conn.execute('''
                INSERT INTO conversations (id, url, media_type, user_insight, ai_analysis, world_model)
                VALUES ($1, $2, $3, $4, $5, $6)
            ''', conversation_id, request.url, processed_content["type"], 
                request.initialThought, analysis_data.response, 
                json.dumps(analysis_data.world_model.dict()))
            
            # Create initial messages
            logger.info("Creating initial messages...")
            await conn.execute('''
                INSERT INTO messages (id, conversation_id, role, content)
                VALUES ($1, $2, $3, $4)
            ''', uuid4(), conversation_id, "user", request.initialThought)
            
            # Combine response and follow-up
            ai_message = f"{analysis_data.response}\n\n{analysis_data.follow_up}"
            await conn.execute('''
                INSERT INTO messages (id, conversation_id, role, content)
                VALUES ($1, $2, $3, $4)
            ''', uuid4(), conversation_id, "assistant", ai_message)
            
            return str(conversation_id)
        except Exception as e:
            logger.error(f"Error during analysis: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: UUID):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        messages = await conn.fetch('''
            SELECT id, conversation_id, role, content, timestamp
            FROM messages
            WHERE conversation_id = $1
            ORDER BY timestamp ASC
        ''', conversation_id)
        
        return [dict(msg) for msg in messages]

@app.post("/api/share")
async def share_conversation(request: ShareRequest):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Check if conversation exists
        conversation = await conn.fetchrow('''
            SELECT id FROM conversations WHERE id = $1
        ''', request.conversationId)
        
        if not conversation:
            raise HTTPException(status_code=404, message="Conversation not found")
        
        # Generate share URL (you might want to implement a more sophisticated system)
        share_url = f"/share/{request.conversationId}"
        
        return ShareResponse(shareUrl=share_url)

# Webhook handling
@app.post("/api/webhooks")
async def create_webhook(url: str, events: List[str], secret: str):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        webhook_id = uuid4()
        await conn.execute('''
            INSERT INTO webhooks (id, url, secret, events)
            VALUES ($1, $2, $3, $4)
        ''', webhook_id, url, secret, events)
        return {"id": webhook_id}

async def dispatch_webhook(event: str, payload: dict):
    # TODO: Implement webhook dispatching with retry logic
    pass

# Add endpoint for continuing conversation
@app.post("/api/conversations/{conversation_id}/messages")
async def add_message(conversation_id: UUID, message: str, url: Optional[str] = None):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Get existing conversation and messages
        conversation = await conn.fetchrow('''
            SELECT * FROM conversations WHERE id = $1
        ''', conversation_id)
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
            
        messages = await conn.fetch('''
            SELECT * FROM messages 
            WHERE conversation_id = $1 
            ORDER BY timestamp ASC
        ''', conversation_id)
        
        # Process new content if URL provided
        new_content = None
        if url:
            processed = await process_media(url)
            new_content = processed["content"]
        
        # Continue conversation using ell
        current_world_model = WorldModel(**json.loads(conversation["world_model"]))
        response = continue_conversation(
            current_world_model,
            [{"role": m["role"], "content": m["content"]} for m in messages],
            new_content
        )
        
        # Extract structured response
        update_data = response.parsed
        
        # Update the world model in the conversation
        await conn.execute('''
            UPDATE conversations 
            SET world_model = $1 
            WHERE id = $2
        ''', json.dumps(update_data.updated_world_model.dict()), conversation_id)
        
        # Save new messages
        msg_id = uuid4()
        await conn.execute('''
            INSERT INTO messages (id, conversation_id, role, content)
            VALUES ($1, $2, $3, $4)
        ''', msg_id, conversation_id, "user", message)
        
        # Combine response and follow-up
        ai_message = f"{update_data.response}\n\n{update_data.follow_up}"
        ai_msg_id = uuid4()
        await conn.execute('''
            INSERT INTO messages (id, conversation_id, role, content)
            VALUES ($1, $2, $3, $4)
        ''', ai_msg_id, conversation_id, "assistant", ai_message)
        
        return {
            "messages": [
                {"id": str(msg_id), "role": "user", "content": message},
                {"id": str(ai_msg_id), "role": "assistant", "content": ai_message}
            ]
        }
    
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        }
    )
    
@app.get("/api/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3001)
