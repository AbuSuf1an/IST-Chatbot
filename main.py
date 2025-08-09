#!/usr/bin/env python3
"""
FastAPI Chatbot Backend for IST Chatbot
Serves as the backend API for the WordPress chatbot integration.
"""

import os
import logging
import threading
import time
from typing import List, Dict, Any, Optional
import json
import psycopg2
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import numpy as np
from datetime import datetime, timedelta
import hashlib

from langchain_google_genai import GoogleGenerativeAIEmbeddings, GoogleGenerativeAI

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

embeddings_model = None
generative_model = None

# ====================
# SESSION MEMORY MANAGEMENT
# ====================

# In-memory storage for conversation history per session
# Structure: {session_id: {"history": [...], "last_activity": datetime, "message_count": int}}
session_memory = {}

# Thread lock for safe concurrent access to session memory
memory_lock = threading.RLock()

# Configuration for session management
MAX_HISTORY_LENGTH = 10  # Maximum number of exchanges to keep per session
SESSION_TIMEOUT = 3600   # Session timeout in seconds (1 hour)
CLEANUP_INTERVAL = 600   # Clean up expired sessions every 10 minutes
last_cleanup_time = time.time()

def generate_session_id(request: Request) -> str:
    """
    Generate a unique session ID based on client IP and User-Agent.
    This provides a simple way to identify returning users without requiring explicit session tokens.
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    
    # Create a hash from IP and User-Agent for session identification
    session_data = f"{client_ip}:{user_agent}"
    session_id = hashlib.md5(session_data.encode()).hexdigest()
    
    logger.debug(f"Generated session ID: {session_id} for IP: {client_ip}")
    return session_id

def cleanup_expired_sessions():
    """
    Remove expired sessions from memory to prevent memory leaks.
    This runs periodically to clean up old, inactive sessions.
    """
    global last_cleanup_time
    current_time = time.time()
    
    # Only run cleanup if enough time has passed
    if current_time - last_cleanup_time < CLEANUP_INTERVAL:
        return
    
    with memory_lock:
        current_datetime = datetime.now()
        expired_sessions = []
        
        for session_id, session_data in session_memory.items():
            last_activity = session_data.get("last_activity", current_datetime)
            if (current_datetime - last_activity).total_seconds() > SESSION_TIMEOUT:
                expired_sessions.append(session_id)
        
        # Remove expired sessions
        for session_id in expired_sessions:
            del session_memory[session_id]
            logger.debug(f"Cleaned up expired session: {session_id}")
        
        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions. Active sessions: {len(session_memory)}")
        
        last_cleanup_time = current_time

def get_session_history(session_id: str) -> List[Dict[str, str]]:
    """
    Retrieve conversation history for a specific session.
    Returns empty list if session doesn't exist or has no history.
    """
    cleanup_expired_sessions()  # Clean up expired sessions when accessing memory
    
    with memory_lock:
        if session_id not in session_memory:
            logger.debug(f"No existing history found for session: {session_id}")
            return []
        
        history = session_memory[session_id].get("history", [])
        logger.debug(f"Retrieved {len(history)} exchanges from session: {session_id}")
        return history.copy()  # Return a copy to prevent external modification

def update_session_history(session_id: str, user_message: str, bot_response: str):
    """
    Update the conversation history for a session with new user message and bot response.
    Maintains a rolling window of the most recent exchanges.
    """
    with memory_lock:
        current_datetime = datetime.now()
        
        # Initialize session if it doesn't exist
        if session_id not in session_memory:
            session_memory[session_id] = {
                "history": [],
                "last_activity": current_datetime,
                "message_count": 0
            }
            logger.debug(f"Created new session: {session_id}")
        
        # Get current session data
        session_data = session_memory[session_id]
        
        # Add new exchange to history
        new_exchange = {
            "user": user_message,
            "bot": bot_response,
            "timestamp": current_datetime.isoformat()
        }
        
        session_data["history"].append(new_exchange)
        session_data["last_activity"] = current_datetime
        session_data["message_count"] += 1
        
        # Trim history to maintain maximum length (keep only recent exchanges)
        if len(session_data["history"]) > MAX_HISTORY_LENGTH:
            # Remove oldest exchanges, keep the most recent ones
            session_data["history"] = session_data["history"][-MAX_HISTORY_LENGTH:]
            logger.debug(f"Trimmed session history to {MAX_HISTORY_LENGTH} exchanges for session: {session_id}")
        
        logger.info(f"Updated session {session_id}: {len(session_data['history'])} exchanges, {session_data['message_count']} total messages")

def merge_histories(stored_history: List[Dict[str, str]], frontend_history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Merge stored session history with history sent from frontend.
    Frontend history takes precedence for the current conversation flow.
    This handles cases where frontend might have more recent context.
    """
    if not frontend_history:
        return stored_history
    
    if not stored_history:
        return frontend_history
    
    # Use frontend history if it's longer (more recent exchanges)
    # This handles cases where the frontend has been maintaining state
    if len(frontend_history) >= len(stored_history):
        logger.debug("Using frontend history as it's more complete")
        return frontend_history
    
    # Otherwise, use stored history (backend has more complete picture)
    logger.debug("Using stored session history")
    return stored_history

# ====================
# DATABASE AND MODEL CONFIGURATION
# ====================

db_config = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'database': os.getenv('DB_NAME', 'ist_data'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', '')
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        initialize_models()
        
        # Test database connection
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM documents;")
        doc_count = cur.fetchone()[0]
        cur.close()
        conn.close()
        
        logger.info(f"Database connection successful. Found {doc_count} documents in database.")
        logger.info("Session memory management initialized")
        yield
        
    except Exception as e:
        logger.error(f"Startup failed: {str(e)}")
        raise

# Initialize FastAPI app
app = FastAPI(
    title="IST Chatbot API",
    description="AI-powered chatbot backend for IST queries with session memory",
    version="1.1.0",  # Updated version to reflect session management
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this to your WordPress domain in production
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    history: List[Dict[str, str]] = []  # Still accept frontend history for compatibility

class ChatResponse(BaseModel):
    response: str
    context_sources: List[str] = []
    timestamp: str = None
    session_id: Optional[str] = None  # Include session ID in response for debugging

def initialize_models():
    global embeddings_model, generative_model
    
    # Get Gemini API key
    gemini_api_key = os.getenv('GEMINI_API_KEY')
    if not gemini_api_key:
        raise ValueError("GEMINI_API_KEY environment variable is required")

    # Initialize embeddings model
    embeddings_model = GoogleGenerativeAIEmbeddings(
        model="models/embedding-001",
        google_api_key=gemini_api_key
    )
    
    # Initialize generative model
    generative_model = GoogleGenerativeAI(
        model="models/gemini-1.5-pro",
        google_api_key=gemini_api_key,
        temperature=0.7,  # Slightly lower for more consistent responses
    )
    
    logger.info("Models initialized successfully")

def get_embedding(text: str) -> List[float]:
    try:
        embedding = embeddings_model.embed_query(text)
        return embedding
    except Exception as e:
        logger.error(f"Failed to generate embedding: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate embedding")

def search_similar_documents(query_embedding: List[float], top_k: int = 5, min_similarity: float = 0.75) -> List[Dict[str, Any]]:
    """Search for similar documents in the database using cosine similarity."""
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()
        
        # Convert embedding to string format for PostgreSQL
        embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
        
        # Perform similarity search using cosine similarity with minimum similarity filter
        query = """
        SELECT filename, content, metadata, 
               (embedding <=> %s::vector) as distance,
               (1 - (embedding <=> %s::vector)) as similarity
        FROM documents
        WHERE (1 - (embedding <=> %s::vector)) >= %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s;
        """
        
        cur.execute(query, (embedding_str, embedding_str, embedding_str, min_similarity, embedding_str, top_k))
        results = cur.fetchall()
        
        documents = []
        for row in results:
            filename, content, metadata, distance, similarity = row
            # Parse metadata JSON
            try:
                metadata_dict = json.loads(metadata) if metadata else {}
            except json.JSONDecodeError:
                metadata_dict = {}
            
            documents.append({
                'filename': filename,
                'content': content,
                'metadata': metadata_dict,
                'similarity_score': similarity
            })
        
        cur.close()
        conn.close()
        
        logger.info(f"Found {len(documents)} similar documents (min_similarity: {min_similarity})")
        return documents
        
    except Exception as e:
        logger.error(f"Database search failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Database search failed")

def construct_prompt(user_message: str, context_documents: List[Dict[str, Any]], chat_history: List[Dict[str, str]] = None) -> str:
    """
    Construct a prompt for the generative model using user message, context, and chat history.
    Now prioritizes recent context over older contradictory information.
    """
    
    # Build conversation memory section with recency bias
    conversation_context = ""
    if chat_history:
        # Limit history to last 5 exchanges for token management
        recent_history = chat_history[-5:] if len(chat_history) > 5 else chat_history
        
        if recent_history:
            conversation_context = "CONVERSATION MEMORY:\n"
            conversation_context += "Recent discussion context (prioritize most recent information):\n\n"
            
            # Reverse the order to show most recent first, with emphasis
            for i, exchange in enumerate(reversed(recent_history), 1):
                user_msg = exchange.get('user', exchange.get('message', ''))
                bot_msg = exchange.get('bot', exchange.get('response', ''))
                
                # Calculate actual position (1 = most recent, 5 = oldest)
                actual_position = len(recent_history) - i + 1
                
                if user_msg:
                    user_summary = user_msg if len(user_msg) <= 100 else user_msg[:97] + "..."
                    # Mark most recent exchanges with emphasis
                    if i <= 2:  # Most recent 2 exchanges get priority
                        conversation_context += f"RECENT {actual_position}. User: {user_summary}\n"
                    else:
                        conversation_context += f"Earlier {actual_position}. User: {user_summary}\n"
                
                if bot_msg:
                    sentences = bot_msg.split('. ')
                    if len(sentences) >= 1 and len(sentences[0]) > 0:
                        bot_summary = sentences[0] + '.'
                        if len(bot_summary) > 120:
                            bot_summary = bot_summary[:117] + '...'
                    else:
                        bot_summary = bot_msg[:120] + "..." if len(bot_msg) > 120 else bot_msg
                    
                    if i <= 2:  # Most recent 2 exchanges get priority
                        conversation_context += f"RECENT Bot: {bot_summary}\n"
                    else:
                        conversation_context += f"Earlier Bot: {bot_summary}\n"
            
            conversation_context += "\n"
    
    # Build document context section
    context_text = ""
    if context_documents:
        context_text = "RETRIEVED DOCUMENTATION:\n"
        context_text += "Relevant information from IST official documents:\n\n"
        
        for i, doc in enumerate(context_documents, 1):
            similarity_score = doc.get('similarity_score', 0)
            context_text += f"Document {i} (from {doc['filename']}, relevance: {similarity_score:.2f}):\n"
            context_text += f"{doc['content']}\n\n"
    
    # Enhanced prompt with recency prioritization
    prompt = f"""PRIORITY INSTRUCTIONS - FOLLOW THESE RULES STRICTLY:
1. Adopt a friendly and helpful tone, similar to a university academic advisor.
2. Be conversational and avoid overly formal language.
3. Start the response with the most relevant information available.
4. Avoid using phrases like "According to the documents," "The provided information," or "This question cannot be answered definitively."
5. If information is not fully detailed, gently state what is available and what is missing.
6. Keep responses concise and to the point.
7. When "IST" is mentioned, it ALWAYS refers to "Institute of Science and Technology, Dhaka."
8. Use BOTH conversation memory and retrieved documentation to provide comprehensive answers.
9. If the answer cannot be found in either source, respond with: "I don't have that specific information in my current knowledge base."
10. Do NOT ask for clarification about acronyms - assume IST means Institute of Science and Technology, Dhaka.
11. Use conversation context to understand follow-up questions and maintain continuity.
12. **CRITICAL: When there's conflicting information in conversation history, ALWAYS prioritize the MOST RECENT context over older information.**
13. **CRITICAL: If the user switches topics (e.g., from CSE to EEE), follow-up questions should relate to the MOST RECENT topic discussed.**
14. Do NOT start your response with greetings like "Hi", "Hello", "Hey" or similar words.
15. Start directly with the answer to the question - no introductory pleasantries needed.
16. This is a continuing conversation, so respond naturally without repetitive greetings.

You are a friendly AI assistant for Institute of Science and Technology (IST), Dhaka. Act like a helpful university academic advisor who is already engaged in conversation.

{conversation_context}{context_text}Based on the conversation memory and retrieved documentation above, please answer the following question. **Pay special attention to RECENT exchanges in the conversation memory as they represent the current context:**

Question: {user_message}

Answer:"""
    
    return prompt

def rephrase_query(user_message: str, chat_history: List[Dict[str, str]]) -> str:
    """
    Rephrase the user's query to be more specific using chat history and IST context.
    Now prioritizes most recent conversation context over older exchanges.
    """
    try:
        # If no history, return original message
        if not chat_history:
            logger.debug("No chat history available for query rephrasing")
            return user_message
        
        # Build chat history context from session memory - prioritize recent exchanges
        history_context = ""
        recent_history = chat_history[-3:] if len(chat_history) > 3 else chat_history  # Last 3 exchanges
        
        if recent_history:
            history_context = "Previous conversation (most recent first):\n"
            # Reverse to show most recent first
            for i, exchange in enumerate(reversed(recent_history), 1):
                user_msg = exchange.get('user', exchange.get('message', ''))
                bot_msg = exchange.get('bot', exchange.get('response', ''))
                
                if user_msg and bot_msg:
                    # Truncate for context efficiency
                    user_summary = user_msg if len(user_msg) <= 80 else user_msg[:77] + "..."
                    bot_summary = bot_msg.split('.')[0] + '.' if '.' in bot_msg else bot_msg[:100] + "..."
                    
                    # Mark the most recent exchange
                    if i == 1:
                        history_context += f"MOST RECENT - User: {user_summary}\n   Bot: {bot_summary}\n"
                    else:
                        history_context += f"Earlier {i} - User: {user_summary}\n   Bot: {bot_summary}\n"
            history_context += "\n"
        
        if not history_context:
            return user_message
        
        rephrase_prompt = f"""Given the chat history below and knowing that this chatbot is specifically about the Institute of Science and Technology (IST), Dhaka, please rephrase the user's current question to be more specific and contextual.

{history_context}Current user question: {user_message}

Instructions:
- If the question mentions "IST" or refers to "the institution/organization/university", assume it's about Institute of Science and Technology, Dhaka
- Make the question more specific by adding context from the conversation history
- **PRIORITIZE the MOST RECENT exchange when determining context - if there are conflicting topics, use the most recent one**
- If the question is vague (like "tell me more", "what about admission", "how much does it cost"), add specific context from the MOST RECENT topic
- Your output should ONLY be the rephrased question, nothing else
- If the question is already specific and clear, you may return it unchanged

Rephrased question:"""
        
        rephrased = generative_model.invoke(rephrase_prompt).strip()
        
        # Clean up the response
        lines = rephrased.split('\n')
        rephrased = lines[0].strip()
        
        # Remove any quotes
        if rephrased.startswith('"') and rephrased.endswith('"'):
            rephrased = rephrased[1:-1]
        if rephrased.startswith("'") and rephrased.endswith("'"):
            rephrased = rephrased[1:-1]
        
        # Log the rephrasing for debugging
        logger.info(f"Original query: {user_message}")
        logger.info(f"Rephrased query: {rephrased}")
        
        return rephrased
        
    except Exception as e:
        logger.warning(f"Failed to rephrase query: {str(e)}. Using original message.")
        return user_message

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "message": "IST Chatbot API is running", 
        "status": "healthy",
        "session_memory": {
            "active_sessions": len(session_memory),
            "max_history_length": MAX_HISTORY_LENGTH
        }
    }

@app.get("/health")
async def health_check():
    """Detailed health check endpoint."""
    try:
        # Test database connection
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM documents;")
        doc_count = cur.fetchone()[0]
        cur.close()
        conn.close()
        
        # Get memory statistics
        with memory_lock:
            memory_stats = {
                "active_sessions": len(session_memory),
                "total_exchanges": sum(len(session["history"]) for session in session_memory.values()),
                "total_messages": sum(session.get("message_count", 0) for session in session_memory.values())
            }
        
        return {
            "status": "healthy",
            "database": "connected",
            "documents_count": doc_count,
            "models": "initialized",
            "session_memory": memory_stats
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, http_request: Request):
    """
    Main chat endpoint with session-based conversation memory.
    Now maintains conversation context across requests using session identification.
    """
    try:
        user_message = request.message.strip()
        
        if not user_message:
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        
        # Generate session ID for this user
        session_id = generate_session_id(http_request)
        logger.info(f"Processing chat request for session {session_id}: {user_message[:100]}...")
        
        # Get stored conversation history for this session
        stored_history = get_session_history(session_id)
        
        # Merge stored history with any frontend history (frontend takes precedence if more complete)
        merged_history = merge_histories(stored_history, request.history)
        
        logger.debug(f"Using conversation history with {len(merged_history)} exchanges for session {session_id}")
        
        # Rephrase the query using the merged conversation history
        rephrased_query = rephrase_query(user_message, merged_history)
        
        # Use the rephrased query for embedding generation
        query_embedding = get_embedding(rephrased_query)
        
        # Search for similar documents
        similar_docs = search_similar_documents(query_embedding, top_k=7, min_similarity=0.6)
        
        # Construct prompt using merged history for context
        prompt = construct_prompt(user_message, similar_docs, merged_history)
        
        # Generate AI response
        try:
            ai_response = generative_model.invoke(prompt)
        except Exception as e:
            logger.error(f"Gemini API call failed: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to generate AI response")
        
        # Update session memory with the new exchange
        update_session_history(session_id, user_message, ai_response)
        
        context_sources = [doc['filename'] for doc in similar_docs] if similar_docs else []
        
        logger.info(f"Generated response for session {session_id}. Context sources: {context_sources}")
        
        return ChatResponse(
            response=ai_response,
            context_sources=context_sources,
            timestamp=datetime.now().isoformat(),
            session_id=session_id  # Include session ID for debugging
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat endpoint error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

# ====================
# SESSION MANAGEMENT ENDPOINTS (Optional - for debugging and administration)
# ====================

@app.get("/api/sessions")
async def get_active_sessions():
    """Debug endpoint to view active sessions (remove in production)."""
    with memory_lock:
        session_info = {}
        for session_id, session_data in session_memory.items():
            session_info[session_id] = {
                "history_length": len(session_data["history"]),
                "message_count": session_data.get("message_count", 0),
                "last_activity": session_data["last_activity"].isoformat()
            }
        
        return {
            "active_sessions": len(session_memory),
            "sessions": session_info
        }

@app.delete("/api/sessions/{session_id}")
async def clear_session(session_id: str):
    """Clear conversation history for a specific session."""
    with memory_lock:
        if session_id in session_memory:
            del session_memory[session_id]
            logger.info(f"Cleared session: {session_id}")
            return {"message": f"Session {session_id} cleared successfully"}
        else:
            raise HTTPException(status_code=404, detail="Session not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)