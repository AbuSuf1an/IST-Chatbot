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

# LangChain imports
from langchain_google_genai import GoogleGenerativeAIEmbeddings, GoogleGenerativeAI

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global variables for models and database config
embeddings_model = None
generative_model = None
db_config = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize models and database connection on startup."""
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
    allow_origins=["*"],  # Configure this to your WordPress domain in production
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Pydantic models for request/response
class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str
    context_sources: List[str] = []

# Global variables for models and database config
embeddings_model = None
generative_model = None
db_config = None

def initialize_models():
    """Initialize the AI models and database configuration."""
    global embeddings_model, generative_model, db_config
    
    # Get Google AI API key
    google_api_key = os.getenv('GOOGLE_API_KEY')
    if not google_api_key:
        raise ValueError("GOOGLE_API_KEY environment variable is required")
    
    # Initialize embeddings model
    embeddings_model = GoogleGenerativeAIEmbeddings(
        model="models/embedding-001",
        google_api_key=google_api_key
    )
    
    # Initialize generative model
    generative_model = GoogleGenerativeAI(
        model="models/gemini-1.5-pro",
        google_api_key=google_api_key,
        temperature=1
    )
    
    # Database configuration
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': os.getenv('DB_PORT', '5432'),
        'database': os.getenv('DB_NAME', 'ist_data'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', '')
    }
    
    logger.info("Models and database configuration initialized successfully")

def get_embedding(text: str) -> List[float]:
    """Generate embedding for a given text."""
    try:
        embedding = embeddings_model.embed_query(text)
        return embedding
    except Exception as e:
        logger.error(f"Failed to generate embedding: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate embedding")

def search_similar_documents(query_embedding: List[float], top_k: int = 3) -> List[Dict[str, Any]]:
    """Search for similar documents in the database using cosine similarity."""
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()
        
        # Convert embedding to string format for PostgreSQL
        embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
        
        # Perform similarity search using cosine similarity
        query = """
        SELECT filename, content, metadata, 
               (embedding <=> %s::vector) as distance
        FROM documents
        ORDER BY embedding <=> %s::vector
        LIMIT %s;
        """
        
        cur.execute(query, (embedding_str, embedding_str, top_k))
        results = cur.fetchall()
        
        documents = []
        for row in results:
            filename, content, metadata, distance = row
            # Parse metadata JSON
            try:
                metadata_dict = json.loads(metadata) if metadata else {}
            except json.JSONDecodeError:
                metadata_dict = {}
            
            documents.append({
                'filename': filename,
                'content': content,
                'metadata': metadata_dict,
                'similarity_score': 1 - distance  # Convert distance to similarity
            })
        
        cur.close()
        conn.close()
        
        logger.info(f"Found {len(documents)} similar documents")
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
    
    prompt = f"""You are an AI assistant for Institute of Science and Technology (IST) website. Your role is to help students, faculty, and staff with questions about IST.

{context_text}

Based on the context above (if provided) and your knowledge about IST, please answer the following question. If the context doesn't contain relevant information, you can still provide helpful information about IST based on your general knowledge, but mention that you're using general information.

Question: {user_message}

Please provide a helpful, accurate, and friendly response. If you're not sure about something specific to IST, it's better to say so rather than guess.

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
    """
    Main chat endpoint that processes user messages and returns AI responses.
    """
    try:
        user_message = request.message.strip()
        
        if not user_message:
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        
        logger.info(f"Received chat request: {user_message[:100]}...")
        
        # 1. Generate embedding for user message
        query_embedding = get_embedding(user_message)
        
        # 2. Search for similar documents
        similar_docs = search_similar_documents(query_embedding, top_k=3)
        
        # 3. Construct prompt with context
        prompt = construct_prompt(user_message, similar_docs)
        
        # 4. Generate response using Gemini
        try:
            ai_response = generative_model.invoke(prompt)
        except Exception as e:
            logger.error(f"Gemini API call failed: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to generate AI response")
        
        # 5. Extract source filenames for context
        context_sources = [doc['filename'] for doc in similar_docs] if similar_docs else []
        
        logger.info(f"Generated response successfully. Context sources: {context_sources}")
        
        return ChatResponse(
            response=ai_response,
            context_sources=context_sources
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat endpoint error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
