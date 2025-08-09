#!/usr/bin/env python3
"""
FastAPI Chatbot Backend for IST Chatbot
Serves as the backend API for the WordPress chatbot integration.
"""

import os
import logging
from typing import List, Dict, Any
import json
import psycopg2
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import numpy as np
from datetime import datetime

from langchain_google_genai import GoogleGenerativeAIEmbeddings, GoogleGenerativeAI

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

embeddings_model = None
generative_model = None

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
        yield
        
    except Exception as e:
        logger.error(f"Startup failed: {str(e)}")
        raise

# Initialize FastAPI app
app = FastAPI(
    title="IST Chatbot API",
    description="AI-powered chatbot backend for IST queries",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Have to configure this to your WordPress domain in production
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    history: List[Dict[str, str]] = []

class ChatResponse(BaseModel):
    response: str
    context_sources: List[str] = []
    timestamp: str = None

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
        temperature=1,
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
                'similarity_score': similarity  # Use the calculated similarity score
            })
        
        cur.close()
        conn.close()
        
        logger.info(f"Found {len(documents)} similar documents (min_similarity: {min_similarity})")
        return documents
        
    except Exception as e:
        logger.error(f"Database search failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Database search failed")

def construct_prompt(user_message: str, context_documents: List[Dict[str, Any]]) -> str:
    """Construct a prompt for the generative model using user message and context."""
    context_text = ""
    
    if context_documents:
        context_text = "Here is some relevant context from IST documentation:\n\n"
        for i, doc in enumerate(context_documents, 1):
            context_text += f"Document {i} (from {doc['filename']}):\n"
            context_text += f"{doc['content']}\n\n"
    
    prompt = f"""PRIORITY INSTRUCTIONS - FOLLOW THESE RULES STRICTLY:
1. When "IST" is mentioned, it ALWAYS refers to "Institute of Science and Technology, Dhaka" from the provided documents.
2. Answer questions ONLY using information found in the provided context below.
3. If the answer cannot be found in the provided context, respond with: "The information you are looking for is not available in our documents."
4. Do NOT use your general knowledge or ask for clarification about acronyms.
5. Do NOT ask which "IST" the user is referring to - assume it's always Institute of Science and Technology, Dhaka.
6. The user question may be contextually enhanced based on conversation history - answer it as presented.

You are an AI assistant for Institute of Science and Technology (IST), Dhaka. Your role is to help students, faculty, and staff with questions about IST using only the provided documentation.

{context_text}

Based strictly on the context above, please answer the following question. Remember: if the information is not in the provided context, say "The information you are looking for is not available in our documents."

Question: {user_message}

Answer:"""
    
    return prompt

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"message": "IST Chatbot API is running", "status": "healthy"}

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
        
        return {
            "status": "healthy",
            "database": "connected",
            "documents_count": doc_count,
            "models": "initialized"
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    try:
        user_message = request.message.strip()
        
        if not user_message:
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        
        logger.info(f"Received chat request: {user_message[:100]}...")
        
        # Rephrase the query to be more specific using chat history
        rephrased_query = rephrase_query(user_message, request.history)
        
        # Use the rephrased query for embedding generation
        query_embedding = get_embedding(rephrased_query)
        
        similar_docs = search_similar_documents(query_embedding, top_k=7, min_similarity=0.6)
        
        # Use the rephrased query (not original message) for better context understanding
        prompt = construct_prompt(rephrased_query, similar_docs)
        
        try:
            ai_response = generative_model.invoke(prompt)
        except Exception as e:
            logger.error(f"Gemini API call failed: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to generate AI response")
        
        context_sources = [doc['filename'] for doc in similar_docs] if similar_docs else []
        
        logger.info(f"Generated response successfully. Context sources: {context_sources}")
        
        return ChatResponse(
            response=ai_response,
            context_sources=context_sources,
            timestamp=datetime.now().isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat endpoint error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

def rephrase_query(user_message: str, chat_history: List[Dict[str, str]]) -> str:
    """Rephrase the user's query to be more specific using chat history and IST context."""
    try:
        # Build chat history context
        history_context = ""
        if chat_history:
            history_context = "Previous conversation:\n"
            for i, exchange in enumerate(chat_history[-3:], 1):  # Only use last 3 exchanges
                user_msg = exchange.get('user', exchange.get('message', ''))
                bot_msg = exchange.get('bot', exchange.get('response', ''))
                history_context += f"{i}. User: {user_msg}\n   Bot: {bot_msg}\n"
            history_context += "\n"
        
        rephrase_prompt = f"""Given the chat history below and knowing that this chatbot is specifically about the Institute of Science and Technology (IST), Dhaka, please rephrase the user's current question to be more specific and contextual.

{history_context}Current user question: {user_message}

Instructions:
- If the question mentions "IST" or refers to "the institution/organization/university", assume it's about Institute of Science and Technology, Dhaka
- Make the question more specific by adding context from the conversation history
- If the question is vague (like "tell me more", "what about admission", "how much does it cost"), add specific context
- Your output should ONLY be the rephrased question, nothing else
- If the question is already specific and clear, you may return it unchanged

Rephrased question:"""
        
        rephrased = generative_model.invoke(rephrase_prompt).strip()
        
        # Log the rephrasing for debugging
        logger.info(f"Original query: {user_message}")
        logger.info(f"Rephrased query: {rephrased}")
        
        return rephrased
        
    except Exception as e:
        logger.warning(f"Failed to rephrase query: {str(e)}. Using original message.")
        return user_message

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
