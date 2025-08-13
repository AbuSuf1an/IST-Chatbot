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
from datetime import datetime 
import hashlib
import re
from typing import Set, Tuple

from langchain_google_genai import GoogleGenerativeAIEmbeddings, GoogleGenerativeAI

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

embeddings_model = None
generative_model = None

session_memory = {}

# Thread lock for safe concurrent access to session memory
memory_lock = threading.RLock()

# Configuration for session management
MAX_HISTORY_LENGTH = 10
SESSION_TIMEOUT = 3600
CLEANUP_INTERVAL = 600
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
            
            # Handle different metadata formats (string or dict)
            try:
                if isinstance(metadata, dict):
                    # Metadata is already a dict
                    metadata_dict = metadata
                elif isinstance(metadata, str):
                    # Metadata is a JSON string
                    metadata_dict = json.loads(metadata)
                else:
                    # Metadata is None or other type
                    metadata_dict = {}
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse metadata for {filename}: {str(e)}")
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
        # Check if the message is a greeting - don't rephrase greetings
        greeting_words = [
            'hi', 'hello', 'hey', 'hola', 'howdy',
            'good morning', 'good afternoon', 'good evening', 'good night',
            'assalamu alaikum', 'walaikum assalam', 'salam', 'salaam',
            'thanks', 'thank you', 'thanks a lot', 'thank you so much', 
            'bye', 'goodbye', 'see you', 'take care', 'farewell',
            'nice to meet you', 'pleasure to meet you',
            'how are you', 'how do you do', 'what\'s up', 'whats up'
        ]
        
        # Additional greeting patterns
        greeting_patterns = [
            'good day', 'good to see you', 'nice talking to you',
            'have a good day', 'have a great day', 'have a nice day'
        ]
        
        user_message_lower = user_message.lower().strip()
        
        # Check for exact matches in greeting words
        if user_message_lower in greeting_words:
            logger.debug(f"Detected exact greeting: '{user_message}' - skipping rephrasing")
            return user_message
        
        # Check for greeting patterns (partial matches)
        for pattern in greeting_patterns:
            if pattern in user_message_lower:
                logger.debug(f"Detected greeting pattern '{pattern}' in message: '{user_message}' - skipping rephrasing")
                return user_message
        
        # Check if it's a short phrase containing greeting words (2-4 words)
        message_words = user_message.strip().split()
        if len(message_words) <= 4:
            for greeting in greeting_words:
                if greeting in user_message_lower:
                    logger.debug(f"Detected greeting in short phrase: '{user_message}' - skipping rephrasing")
                    return user_message
        
        # Check for common greeting-like expressions
        greeting_expressions = [
            'peace be upon you', 'peace be with you', 'blessings',
            'hope you are well', 'hope all is well'
        ]
        
        for expression in greeting_expressions:
            if expression in user_message_lower:
                logger.debug(f"Detected greeting expression: '{user_message}' - skipping rephrasing")
                return user_message
        
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

def extract_topics_from_text(text: str) -> Set[str]:
    """
    Extract relevant topics/subjects from text that could be referenced later.
    """
    # Define patterns for different types of topics
    topic_patterns = {
        'departments': r'\b(?:Department of |Dept\. of |)(?:Computer Science|CSE|ECE|Electronics|Communication|Engineering|Business Administration|BBA|MBA|ICT|Information Technology)\b',
        'programs': r'\b(?:Bachelor|Master|B\.Sc|M\.Sc|PhD|Undergraduate|Graduate|Diploma)\s+(?:in\s+|of\s+)?(?:Computer Science|CSE|ECE|Electronics|Communication|Engineering|Business Administration|BBA|MBA|ICT|Information Technology)\b',
        'courses': r'\b(?:course|subject|class)\s+(?:in\s+|of\s+)?(?:Computer Science|CSE|ECE|Electronics|Communication|Engineering|Business Administration|BBA|MBA|ICT|Information Technology|Programming|Database|Network|Software)\b',
        'facilities': r'\b(?:lab|laboratory|library|cafeteria|hostel|dormitory|computer lab|electronics lab|networking lab)\b',
        'people': r'\b(?:Professor|Dr\.|Mr\.|Ms\.|Lecturer|Assistant Professor|Associate Professor|Head of|Director)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b',
        'locations': r'\b(?:campus|building|room|hall|auditorium|ground|field)\b',
        'services': r'\b(?:admission|fee|tuition|scholarship|waiver|result|exam|routine|schedule)\b'
    }
    
    topics = set()
    text_lower = text.lower()
    
    for category, pattern in topic_patterns.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            if isinstance(match, str) and len(match.strip()) > 2:
                topics.add(match.strip())
    
    # Add some specific IST-related topics
    ist_topics = {
        'CSE': ['computer science', 'cse', 'computer science and engineering'],
        'ECE': ['electronics', 'ece', 'electronics and communication engineering'],
        'BBA': ['business administration', 'bba', 'business'],
        'MBA': ['master of business administration', 'mba'],
        'ICT': ['information technology', 'ict', 'information and communication technology']
    }
    
    for abbrev, full_names in ist_topics.items():
        for name in full_names:
            if name in text_lower:
                topics.add(abbrev)
                topics.add(name)
                break
    
    return topics

def resolve_ambiguous_query(user_query: str, history: List[Dict[str, str]]) -> str:
    """
    Replaces vague references in user_query with the most relevant topic from history.
    Example: If previous query was about 'cost of studying CSE', then
    'Who is the head of this department?' becomes
    'Who is the head of the CSE department at IST?'
    """
    if not history:
        return user_query
    
    # Check if query contains ambiguous references
    ambiguous_patterns = [
        r'\bthis\s+(?:department|program|course|lab|facility|building|service)\b',
        r'\bthat\s+(?:department|program|course|lab|facility|building|service)\b',
        r'\bthe\s+(?:department|program|course|lab|facility|building|service)\b(?!\s+(?:of|at|in)\s+\w+)',
        r'\bit\b(?!\s+(?:is|was|has|does|can))',  # "it" not followed by verbs
        r'\bthey\b',
        r'\bthem\b',
        r'\bhere\b',
        r'\bthere\b'
    ]
    
    has_ambiguous_ref = any(re.search(pattern, user_query, re.IGNORECASE) for pattern in ambiguous_patterns)
    
    if not has_ambiguous_ref:
        return user_query
    
    logger.info(f"Detected ambiguous reference in: {user_query}")
    
    # Extract topics from recent conversation history (prioritize most recent)
    recent_topics = set()
    recent_context = ""
    
    # Look at last 3 exchanges, with most recent having highest priority
    for i, exchange in enumerate(reversed(history[-3:]), 1):
        user_msg = exchange.get('user', exchange.get('message', ''))
        bot_msg = exchange.get('bot', exchange.get('response', ''))
        
        # Extract topics from both user and bot messages
        if user_msg:
            user_topics = extract_topics_from_text(user_msg)
            recent_topics.update(user_topics)
            if i == 1:  # Most recent exchange
                recent_context += f"Recent topic: {user_msg} "
        
        if bot_msg:
            bot_topics = extract_topics_from_text(bot_msg)
            recent_topics.update(bot_topics)
            if i == 1:  # Most recent exchange
                recent_context += f"Context: {bot_msg[:100]}... "
    
    if not recent_topics:
        logger.info("No topics found in recent history")
        return user_query
    
    logger.info(f"Found topics in history: {recent_topics}")
    
    # Map common ambiguous terms to their likely referents
    resolved_query = user_query
    
    # Department references
    dept_topics = [t for t in recent_topics if any(keyword in t.lower() for keyword in ['cse', 'computer science', 'ece', 'electronics', 'bba', 'business', 'mba', 'ict'])]
    if dept_topics:
        primary_dept = dept_topics[0]  # Use most relevant department
        
        # Replace ambiguous department references
        resolved_query = re.sub(r'\bthis\s+department\b', f'the {primary_dept} department', resolved_query, flags=re.IGNORECASE)
        resolved_query = re.sub(r'\bthat\s+department\b', f'the {primary_dept} department', resolved_query, flags=re.IGNORECASE)
        resolved_query = re.sub(r'\bthe\s+department\b(?!\s+(?:of|at|in)\s+\w+)', f'the {primary_dept} department', resolved_query, flags=re.IGNORECASE)
        
        # Replace program references
        resolved_query = re.sub(r'\bthis\s+program\b', f'the {primary_dept} program', resolved_query, flags=re.IGNORECASE)
        resolved_query = re.sub(r'\bthat\s+program\b', f'the {primary_dept} program', resolved_query, flags=re.IGNORECASE)
    
    # Course references
    course_topics = [t for t in recent_topics if 'course' in t.lower() or 'subject' in t.lower()]
    if course_topics:
        primary_course = course_topics[0]
        resolved_query = re.sub(r'\bthis\s+course\b', primary_course, resolved_query, flags=re.IGNORECASE)
        resolved_query = re.sub(r'\bthat\s+course\b', primary_course, resolved_query, flags=re.IGNORECASE)
    
    # Facility references
    facility_topics = [t for t in recent_topics if any(keyword in t.lower() for keyword in ['lab', 'library', 'cafeteria', 'hostel', 'building'])]
    if facility_topics:
        primary_facility = facility_topics[0]
        resolved_query = re.sub(r'\bthis\s+(?:lab|facility|building)\b', primary_facility, resolved_query, flags=re.IGNORECASE)
        resolved_query = re.sub(r'\bthat\s+(?:lab|facility|building)\b', primary_facility, resolved_query, flags=re.IGNORECASE)
    
    # General "it" references - replace with most relevant topic
    if re.search(r'\bit\b(?!\s+(?:is|was|has|does|can))', resolved_query, re.IGNORECASE):
        if recent_topics:
            # Use the most specific topic available
            specific_topics = [t for t in recent_topics if len(t.split()) > 1]  # Multi-word topics are usually more specific
            if specific_topics:
                primary_topic = specific_topics[0]
            else:
                primary_topic = list(recent_topics)[0]
            
            resolved_query = re.sub(r'\bit\b(?!\s+(?:is|was|has|does|can))', primary_topic, resolved_query, flags=re.IGNORECASE)
    
    # Add IST context if not present
    if 'ist' not in resolved_query.lower() and 'institute of science and technology' not in resolved_query.lower():
        resolved_query += ' at IST'
    
    if resolved_query != user_query:
        logger.info(f"Resolved ambiguous query: '{user_query}' -> '{resolved_query}'")
    
    return resolved_query

def generate_query_variants(query: str) -> List[str]:
    """
    Generate alternative paraphrases of the query for multi-query expansion.
    """
    try:
        variants_prompt = f"""Generate 2 alternative paraphrases of this query about Institute of Science and Technology (IST), Dhaka:

Original: {query}

Requirements:
- Keep the same meaning but use different wording
- Focus on IST university context
- Make queries more specific if possible
- Output only the 2 paraphrases, one per line
- No numbering, no extra text

Paraphrases:"""
        
        response = generative_model.invoke(variants_prompt).strip()
        variants = [line.strip() for line in response.split('\n') if line.strip() and not line.strip().startswith(('1.', '2.', '-', '*'))]
        
        # Clean up any remaining formatting
        clean_variants = []
        for variant in variants[:2]:  # Limit to 2 variants
            variant = variant.strip().strip('"\'')
            if variant and variant != query:
                clean_variants.append(variant)
        
        logger.info(f"Generated {len(clean_variants)} query variants")
        return clean_variants
        
    except Exception as e:
        logger.warning(f"Failed to generate query variants: {str(e)}")
        return []

def enhanced_rephrase_query(user_message: str, chat_history: List[Dict[str, str]]) -> str:
    """
    Enhanced query rephrasing that first resolves ambiguous references, then rephrases for context.
    """
    try:
        # First, resolve ambiguous references
        resolved_query = resolve_ambiguous_query(user_message, chat_history)
        
        # Then apply the existing rephrasing logic
        return rephrase_query(resolved_query, chat_history)
        
    except Exception as e:
        logger.warning(f"Failed to enhance query rephrasing: {str(e)}. Using original message.")
        return user_message

# Enhanced search with fallback for better retrieval
def enhanced_search_similar_documents(query_embedding: List[float], user_query: str, top_k: int = 10, min_similarity: float = 0.5) -> List[Dict[str, Any]]:
    """
    Enhanced document search with fallback strategies to reduce "I don't know" responses.
    """
    # Primary search with lowered threshold
    documents = search_similar_documents(query_embedding, top_k, min_similarity)
    
    # If we have enough relevant documents, return them
    if len(documents) >= 3 and all(doc['similarity_score'] >= 0.6 for doc in documents[:3]):
        return documents
    
    logger.info(f"Primary search returned {len(documents)} documents, trying enhanced retrieval...")
    
    # Fallback 1: Lower similarity threshold
    if len(documents) < 3:
        fallback_docs = search_similar_documents(query_embedding, top_k=15, min_similarity=0.3)
        logger.info(f"Fallback search with lower threshold found {len(fallback_docs)} documents")
        if len(fallback_docs) > len(documents):
            documents = fallback_docs
    
    # Fallback 2: Keyword-based search for specific terms
    if len(documents) < 5:
        keyword_docs = keyword_search_fallback(user_query)
        if keyword_docs:
            # Merge and deduplicate
            existing_filenames = {doc['filename'] for doc in documents}
            for kdoc in keyword_docs:
                if kdoc['filename'] not in existing_filenames:
                    documents.append(kdoc)
            
            logger.info(f"Added {len(keyword_docs)} documents from keyword search")
    
    return documents[:top_k]  # Limit to requested number

def multi_query_retrieval(query: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """
    Perform retrieval using multiple query variants and merge results.
    """
    all_documents = []
    seen_content = set()
    
    # Original query
    try:
        original_embedding = get_embedding(query)
        original_docs = enhanced_search_similar_documents(original_embedding, query, top_k)
        
        for doc in original_docs:
            content_hash = hashlib.md5(doc['content'].encode()).hexdigest()
            if content_hash not in seen_content:
                all_documents.append(doc)
                seen_content.add(content_hash)
        
        logger.info(f"Original query retrieved {len(original_docs)} documents")
    except Exception as e:
        logger.warning(f"Original query retrieval failed: {str(e)}")
    
    # Query variants
    variants = generate_query_variants(query)
    for i, variant in enumerate(variants, 1):
        try:
            variant_embedding = get_embedding(variant)
            variant_docs = enhanced_search_similar_documents(variant_embedding, variant, top_k//2)
            
            variant_added = 0
            for doc in variant_docs:
                content_hash = hashlib.md5(doc['content'].encode()).hexdigest()
                if content_hash not in seen_content:
                    all_documents.append(doc)
                    seen_content.add(content_hash)
                    variant_added += 1
            
            logger.info(f"Query variant {i} added {variant_added} new documents")
            
        except Exception as e:
            logger.warning(f"Variant query {i} retrieval failed: {str(e)}")
    
    # Sort by similarity score and return top results
    all_documents.sort(key=lambda x: x['similarity_score'], reverse=True)
    final_docs = all_documents[:top_k]
    
    logger.info(f"Multi-query retrieval: {len(final_docs)} unique documents from {len(variants)+1} queries")
    return final_docs

def keyword_search_fallback(user_query: str) -> List[Dict[str, Any]]:
    """
    Fallback keyword search for cases where semantic search doesn't find enough results.
    """
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()
        
        # Extract keywords from query
        keywords = extract_search_keywords(user_query)
        
        if not keywords:
            return []
        
        # Build keyword search query
        keyword_conditions = []
        params = []
        
        for keyword in keywords:
            keyword_conditions.append("(LOWER(content) LIKE %s OR LOWER(filename) LIKE %s)")
            params.extend([f"%{keyword.lower()}%", f"%{keyword.lower()}%"])
        
        query = f"""
        SELECT filename, content, metadata, 0.4 as similarity_score
        FROM documents
        WHERE {' OR '.join(keyword_conditions)}
        LIMIT 10;
        """
        
        cur.execute(query, params)
        results = cur.fetchall()
        
        documents = []
        for row in results:
            filename, content, metadata, similarity = row
            
            try:
                metadata_dict = json.loads(metadata) if metadata else {}
            except:
                metadata_dict = {}
            
            documents.append({
                'filename': filename,
                'content': content,
                'metadata': metadata_dict,
                'similarity_score': similarity
            })
        
        cur.close()
        conn.close()
        
        return documents
        
    except Exception as e:
        logger.error(f"Keyword search fallback failed: {str(e)}")
        return []

def extract_search_keywords(user_query: str) -> List[str]:
    """
    Extract relevant keywords from user query for fallback search.
    """
    # Important IST-related terms
    important_terms = {
        'faculty', 'teacher', 'professor', 'lecturer', 'instructor', 'head', 'director',
        'cse', 'computer science', 'ece', 'electronics', 'communication', 'bba', 'business', 'mba', 'ict',
        'admission', 'fee', 'tuition', 'cost', 'price', 'scholarship', 'waiver',
        'course', 'subject', 'program', 'degree', 'bachelor', 'master', 'phd',
        'lab', 'laboratory', 'library', 'facility', 'hostel', 'cafeteria',
        'result', 'exam', 'routine', 'schedule', 'semester', 'year',
        'contact', 'phone', 'email', 'address', 'location'
    }
    
    query_lower = user_query.lower()
    found_keywords = []
    
    # Find matching terms
    for term in important_terms:
        if term in query_lower:
            found_keywords.append(term)
    
    # Add names (capitalized words that might be person names)
    words = user_query.split()
    for word in words:
        if word[0].isupper() and len(word) > 3 and word.lower() not in ['what', 'who', 'where', 'when', 'how', 'the', 'and', 'are', 'for', 'ist']:
            found_keywords.append(word.lower())
    
    return found_keywords

# Update the main chat endpoint to use enhanced functions
@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, http_request: Request):
    """
    Main chat endpoint with enhanced ambiguous reference resolution and retrieval.
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
        
        # Merge stored history with any frontend history
        merged_history = merge_histories(stored_history, request.history)
        
        logger.debug(f"Using conversation history with {len(merged_history)} exchanges for session {session_id}")
        
        # Enhanced query processing: resolve ambiguous references, then rephrase for context
        enhanced_query = enhanced_rephrase_query(user_message, merged_history)
        
        # Multi-query retrieval with enhanced fallback strategies
        similar_docs = multi_query_retrieval(enhanced_query, top_k=10)
        
        # Construct prompt using merged history for context
        prompt = construct_enhanced_prompt(user_message, enhanced_query, similar_docs, merged_history)
        
        # Generate AI response
        try:
            ai_response = generative_model.invoke(prompt)
        except Exception as e:
            logger.error(f"Gemini API call failed: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to generate AI response")
        
        # Update session memory with the new exchange
        update_session_history(session_id, user_message, ai_response)
        
        context_sources = [doc['filename'] for doc in similar_docs] if similar_docs else []
        
        logger.info(f"Generated response for session {session_id}. Context sources: {len(context_sources)} documents")
        
        return ChatResponse(
            response=ai_response,
            context_sources=context_sources,
            timestamp=datetime.now().isoformat(),
            session_id=session_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat endpoint error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

def construct_enhanced_prompt(original_query: str, enhanced_query: str, context_documents: List[Dict[str, Any]], chat_history: List[Dict[str, str]] = None) -> str:
    """
    Enhanced prompt construction that provides more context for better responses.
    """
    # Build conversation memory section with recency bias
    conversation_context = ""
    if chat_history:
        recent_history = chat_history[-5:] if len(chat_history) > 5 else chat_history
        
        if recent_history:
            conversation_context = "CONVERSATION MEMORY:\n"
            conversation_context += "Recent discussion context (prioritize most recent information):\n\n"
            
            for i, exchange in enumerate(reversed(recent_history), 1):
                user_msg = exchange.get('user', exchange.get('message', ''))
                bot_msg = exchange.get('bot', exchange.get('response', ''))
                
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
        context_text += "Available information from IST official documents and data:\n\n"
        
        for i, doc in enumerate(context_documents, 1):
            similarity_score = doc.get('similarity_score', 0)
            context_text += f"Document {i} (from {doc['filename']}, relevance: {similarity_score:.2f}):\n"
            context_text += f"{doc['content']}\n\n"
    
    # Enhanced prompt with better synthesis instructions
    query_context = f"Original question: {original_query}\n"
    if enhanced_query != original_query:
        query_context += f"Enhanced/resolved question: {enhanced_query}\n"
    
    prompt = f"""ENHANCED PRIORITY INSTRUCTIONS - FOLLOW THESE RULES STRICTLY:

    CORE BEHAVIOR:
    1. You are a friendly academic advisor for Institute of Science and Technology (IST), Dhaka
    2. When "IST" is mentioned, it ALWAYS refers to "Institute of Science and Technology, Dhaka"
    3. Never start with greetings like "Hi", "Hello" - start directly with the answer
    4. Be conversational and avoid overly formal language

    INFORMATION SYNTHESIS RULES:
    5. **CRITICAL**: Use ALL available information to provide comprehensive answers
    6. **CRITICAL**: Combine information from multiple documents when relevant
    7. **CRITICAL**: If you don't find direct answers, use related information to provide helpful responses
    8. **CRITICAL**: Extract specific details like names, numbers, dates, requirements from the documents
    9. **CRITICAL**: Only say "I don't have that specific information" if NO relevant information exists in any document

    CONVERSATION HANDLING:
    10. Use BOTH conversation memory and retrieved documentation
    11. **CRITICAL**: When there's conflicting information, ALWAYS prioritize the MOST RECENT context
    12. Use conversation context to understand follow-up questions and maintain continuity
    13. If the user switches topics, follow-up questions should relate to the MOST RECENT topic discussed

    RESPONSE GUIDELINES:
    14. Start responses with the most relevant information available
    15. Be specific - provide names, numbers, requirements, procedures when available
    16. If information is incomplete, state what is available and acknowledge what might be missing
    17. Use the enhanced query context to understand what the user is really asking about

    {conversation_context}{context_text}

    QUERY CONTEXT:
    {query_context}

    Based on the conversation memory and retrieved documentation above, please provide a comprehensive answer by analyzing and synthesizing ALL available information. **Pay special attention to RECENT exchanges in the conversation memory as they represent the current context.**

    Answer:"""
    
    return prompt

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)