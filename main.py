#FastAPI Chatbot Backend API for the WordPress chatbot integration.

import os
import logging
import threading
import time
from typing import List, Dict, Any, Optional, Set
import json
import psycopg2
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime 
import hashlib
import re

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
memory_lock = threading.RLock()

MAX_HISTORY_LENGTH = 50
SESSION_TIMEOUT = 3600
CLEANUP_INTERVAL = 1800
last_cleanup_time = time.time()

def generate_session_id(request: Request) -> str:
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    session_data = f"{client_ip}:{user_agent}"
    return hashlib.md5(session_data.encode()).hexdigest()

def cleanup_expired_sessions():
    global last_cleanup_time
    current_time = time.time()
    if current_time - last_cleanup_time < CLEANUP_INTERVAL:
        return
    with memory_lock:
        current_datetime = datetime.now()
        expired_sessions = [
            sid for sid, sdata in session_memory.items()
            if (current_datetime - sdata.get("last_activity", current_datetime)).total_seconds() > SESSION_TIMEOUT
        ]
        for sid in expired_sessions:
            del session_memory[sid]
        last_cleanup_time = current_time

def get_session_history(session_id: str) -> List[Dict[str, str]]:
    cleanup_expired_sessions()
    with memory_lock:
        return session_memory.get(session_id, {}).get("history", []).copy()

def update_session_history(session_id: str, user_message: str, bot_response: str):
    with memory_lock:
        current_datetime = datetime.now()
        if session_id not in session_memory:
            session_memory[session_id] = {"history": [], "last_activity": current_datetime, "message_count": 0}
        session_data = session_memory[session_id]
        session_data["history"].append({
            "user": user_message,
            "bot": bot_response,
            "timestamp": current_datetime.isoformat()
        })
        session_data["last_activity"] = current_datetime
        session_data["message_count"] += 1
        if len(session_data["history"]) > MAX_HISTORY_LENGTH:
            session_data["history"] = session_data["history"][-MAX_HISTORY_LENGTH:]

def merge_histories(stored_history: List[Dict[str, str]], frontend_history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    if not frontend_history:
        return stored_history
    if not stored_history:
        return frontend_history
    return frontend_history if len(frontend_history) >= len(stored_history) else stored_history

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

app = FastAPI(
    title="IST Chatbot API",
    description="AI-powered chatbot backend for IST queries with session memory",
    version="1.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    session_id: Optional[str] = None

def initialize_models():
    global embeddings_model, generative_model
    gemini_api_key = os.getenv('GEMINI_API_KEY')
    if not gemini_api_key:
        raise ValueError("GEMINI_API_KEY environment variable is required")
    embeddings_model = GoogleGenerativeAIEmbeddings(
        model="models/embedding-001",
        google_api_key=gemini_api_key
    )
    generative_model = GoogleGenerativeAI(
        model="models/gemini-1.5-pro",
        google_api_key=gemini_api_key,
        temperature=0.7,
    )

def get_embedding(text: str) -> List[float]:
    return embeddings_model.embed_query(text)

def search_similar_documents(query_embedding: List[float], top_k: int = 5, min_similarity: float = 0.75) -> List[Dict[str, Any]]:
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()
    embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
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
        try:
            metadata_dict = json.loads(metadata) if isinstance(metadata, str) else metadata or {}
        except Exception:
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

def construct_enhanced_prompt(original_query: str, enhanced_query: str, context_documents: List[Dict[str, Any]], chat_history: List[Dict[str, str]] = None) -> str:
    conversation_context = ""
    if chat_history:
        recent_history = chat_history[-5:] if len(chat_history) > 5 else chat_history
        if recent_history:
            conversation_context = "CONVERSATION MEMORY:\nRecent discussion context (prioritize most recent information):\n\n"
            for i, exchange in enumerate(reversed(recent_history), 1):
                user_msg = exchange.get('user', exchange.get('message', ''))
                bot_msg = exchange.get('bot', exchange.get('response', ''))
                actual_position = len(recent_history) - i + 1
                if user_msg:
                    user_summary = user_msg if len(user_msg) <= 100 else user_msg[:97] + "..."
                    conversation_context += f"{'RECENT' if i <= 2 else 'Earlier'} {actual_position}. User: {user_summary}\n"
                if bot_msg:
                    sentences = bot_msg.split('. ')
                    bot_summary = sentences[0] + '.' if sentences else bot_msg[:120]
                    if len(bot_summary) > 120:
                        bot_summary = bot_summary[:117] + '...'
                    conversation_context += f"{'RECENT' if i <= 2 else 'Earlier'} Bot: {bot_summary}\n"
            conversation_context += "\n"
    context_text = ""
    if context_documents:
        context_text = "RETRIEVED DOCUMENTATION:\nAvailable information from IST official documents and data:\n\n"
        for i, doc in enumerate(context_documents, 1):
            similarity_score = doc.get('similarity_score', 0)
            context_text += f"Document {i} (from {doc['filename']}, relevance: {similarity_score:.2f}):\n{doc['content']}\n\n"
    query_context = f"Original question: {original_query}\n"
    if enhanced_query != original_query:
        query_context += f"Enhanced/resolved question: {enhanced_query}\n"
    prompt = f"""ENHANCED PRIORITY INSTRUCTIONS - FOLLOW THESE RULES STRICTLY:

    CORE BEHAVIOR:
    1. You are a friendly academic advisor for Institute of Science and Technology (IST), Dhaka
    2. When "IST" is mentioned, it ALWAYS refers to "Institute of Science and Technology, Dhaka"
    3. Never start with greetings like "Hi", "Hello" - start directly with the answer
    4. Be conversational and avoid overly formal language
    5. When referring to IST, always use first-person language ("our", "we", "us", "our address", etc.) as if you are part of IST.

    INFORMATION SYNTHESIS RULES:
    6. Give exactly the information requested, using the most relevant documents
    7. Give only the most relevant information, do not include unnecessary details
    8. If you don't find direct answers, use related information to provide helpful responses
    9. Extract specific details like names, numbers, dates, requirements from the documents
    10. Only say "I don't have that specific information in my knowledge" if NO relevant information exists in ANY document, and ONLY after thoroughly checking ALL available sources for a direct answer. Do NOT mention documentation or sources in your reply.

    CONVERSATION HANDLING:
    11. Use BOTH conversation memory and retrieved documentation
    12. When there's conflicting information, ALWAYS prioritize the MOST RECENT context
    13. Use conversation context to understand follow-up questions and maintain continuity
    14. If the user switches topics, follow-up questions should relate to the MOST RECENT topic discussed

    RESPONSE GUIDELINES:
    15. Start responses with the most relevant information available
    16. Be specific - provide names, numbers, requirements, procedures when available
    17. If information is incomplete, state what is available and acknowledge what might be missing
    18. Use the enhanced query context to understand what the user is really asking about
    19. Keep answers concise and focused. Summarize information in 1-2 sentences unless user asks for detailed information.
    20. Only include the most relevant details unless the user asks for more.
    21. If the user asks about a person, reply with their current role/title and department only, unless the user requests more details.

    IMPORTANT:
    22. If contact information (email, phone) asked and is present in ANY retrieved document, include it in your reply. Do NOT say "not available" if it exists in the provided context.
    23. Only answer what is specifically asked in the user's question. Do NOT provide additional related information, context, or details unless the user requests it. Avoid combining multiple answers in one reply.
    24. If the user's question is general knowledge (such as today's date, time, weather, etc.) and the answer is not found in IST documents, reply: "I'm an IST academic assistant and can only answer questions related to IST."
    25. Never use HTML tags (such as <em>, <strong>, etc.) or placeholder words (such as "what", "something", "topic", etc.) in your reply. Always use clear, natural language. If the user's question is unclear, politely ask for clarification using plain text only.
    
    {conversation_context}{context_text}
    QUERY CONTEXT:
    {query_context}
    Based on the conversation memory and retrieved documentation above, please provide a comprehensive answer by analyzing and synthesizing ALL available information. Pay special attention to RECENT exchanges in the conversation memory as they represent the current context.

    Answer:"""
    return prompt

def extract_topics_from_text(text: str) -> Set[str]:
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
    
    recent_topics = set()
    recent_context = ""
    
    for i, exchange in enumerate(reversed(history[-3:]), 1):
        user_msg = exchange.get('user', exchange.get('message', ''))
        bot_msg = exchange.get('bot', exchange.get('response', ''))
        
        if user_msg:
            user_topics = extract_topics_from_text(user_msg)
            recent_topics.update(user_topics)
            if i == 1:
                recent_context += f"Recent topic: {user_msg} "
        
        if bot_msg:
            bot_topics = extract_topics_from_text(bot_msg)
            recent_topics.update(bot_topics)
            if i == 1:
                recent_context += f"Context: {bot_msg[:100]}... "
    
    if not recent_topics:
        logger.info("No topics found in recent history")
        return user_query
    
    logger.info(f"Found topics in history: {recent_topics}")
    
    resolved_query = user_query
    
    dept_topics = [t for t in recent_topics if any(keyword in t.lower() for keyword in ['cse', 'computer science', 'ece', 'electronics', 'bba', 'business', 'mba', 'ict'])]
    if dept_topics:
        primary_dept = dept_topics[0]
        
        resolved_query = re.sub(r'\bthis\s+department\b', f'the {primary_dept} department', resolved_query, flags=re.IGNORECASE)
        resolved_query = re.sub(r'\bthat\s+department\b', f'the {primary_dept} department', resolved_query, flags=re.IGNORECASE)
        resolved_query = re.sub(r'\bthe\s+department\b(?!\s+(?:of|at|in)\s+\w+)', f'the {primary_dept} department', resolved_query, flags=re.IGNORECASE)
        
        resolved_query = re.sub(r'\bthis\s+program\b', f'the {primary_dept} program', resolved_query, flags=re.IGNORECASE)
        resolved_query = re.sub(r'\bthat\s+program\b', f'the {primary_dept} program', resolved_query, flags=re.IGNORECASE)
    
    course_topics = [t for t in recent_topics if 'course' in t.lower() or 'subject' in t.lower()]
    if course_topics:
        primary_course = course_topics[0]
        resolved_query = re.sub(r'\bthis\s+course\b', primary_course, resolved_query, flags=re.IGNORECASE)
        resolved_query = re.sub(r'\bthat\s+course\b', primary_course, resolved_query, flags=re.IGNORECASE)
    
    facility_topics = [t for t in recent_topics if any(keyword in t.lower() for keyword in ['lab', 'library', 'cafeteria', 'hostel', 'building'])]
    if facility_topics:
        primary_facility = facility_topics[0]
        resolved_query = re.sub(r'\bthis\s+(?:lab|facility|building)\b', primary_facility, resolved_query, flags=re.IGNORECASE)
        resolved_query = re.sub(r'\bthat\s+(?:lab|facility|building)\b', primary_facility, resolved_query, flags=re.IGNORECASE)
    
    if re.search(r'\bit\b(?!\s+(?:is|was|has|does|can))', resolved_query, re.IGNORECASE):
        if recent_topics:
            specific_topics = [t for t in recent_topics if len(t.split()) > 1]  # Multi-word topics are usually more specific
            if specific_topics:
                primary_topic = specific_topics[0]
            else:
                primary_topic = list(recent_topics)[0]
            
            resolved_query = re.sub(r'\bit\b(?!\s+(?:is|was|has|does|can))', primary_topic, resolved_query, flags=re.IGNORECASE)
    
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
        
        clean_variants = []
        for variant in variants[:2]:
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
        resolved_query = resolve_ambiguous_query(user_message, chat_history)
        return resolved_query
        
    except Exception as e:
        logger.warning(f"Failed to enhance query rephrasing: {str(e)}. Using original message.")
        return user_message

def enhanced_search_similar_documents(query_embedding: List[float], user_query: str, top_k: int = 10, min_similarity: float = 0.5) -> List[Dict[str, Any]]:
    """
    Enhanced document search with fallback strategies to reduce "I don't know" responses.
    """
    documents = search_similar_documents(query_embedding, top_k, min_similarity)
    
    if len(documents) >= 3 and all(doc['similarity_score'] >= 0.6 for doc in documents[:3]):
        return documents
    
    logger.info(f"Primary search returned {len(documents)} documents, trying enhanced retrieval...")
    
    if len(documents) < 3:
        fallback_docs = search_similar_documents(query_embedding, top_k=15, min_similarity=0.3)
        logger.info(f"Fallback search with lower threshold found {len(fallback_docs)} documents")
        if len(fallback_docs) > len(documents):
            documents = fallback_docs
    
    if len(documents) < 5:
        keyword_docs = keyword_search_fallback(user_query)
        if keyword_docs:
            existing_filenames = {doc['filename'] for doc in documents}
            for kdoc in keyword_docs:
                if kdoc['filename'] not in existing_filenames:
                    documents.append(kdoc)
            
            logger.info(f"Added {len(keyword_docs)} documents from keyword search")
    
    return documents[:top_k]

def multi_query_retrieval(query: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """
    Perform retrieval using multiple query variants and merge results.
    """
    all_documents = []
    seen_content = set()
    
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
        
        keywords = extract_search_keywords(user_query)
        
        if not keywords:
            return []
        
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
    
    for term in important_terms:
        if term in query_lower:
            found_keywords.append(term)
    
    words = user_query.split()
    for word in words:
        if word[0].isupper() and len(word) > 3 and word.lower() not in ['what', 'who', 'where', 'when', 'how', 'the', 'and', 'are', 'for', 'ist']:
            found_keywords.append(word.lower())
    
    return found_keywords

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, http_request: Request):
    try:
        user_message = request.message.strip()
        if not user_message:
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        if is_greeting(user_message):
            return ChatResponse(
                response="Hello! How can I assist you today?",
                context_sources=[],
                timestamp=datetime.now().isoformat(),
                session_id=generate_session_id(http_request)
            )
        session_id = generate_session_id(http_request)
        stored_history = get_session_history(session_id)
        merged_history = merge_histories(stored_history, request.history)
        enhanced_query = enhanced_rephrase_query(user_message, merged_history)
        similar_docs = multi_query_retrieval(enhanced_query, top_k=10)
        prompt = construct_enhanced_prompt(user_message, enhanced_query, similar_docs, merged_history)
        ai_response = generative_model.invoke(prompt)
        update_session_history(session_id, user_message, ai_response)
        context_sources = [doc['filename'] for doc in similar_docs] if similar_docs else []
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

def is_greeting(message: str) -> bool:
    message = message.strip().lower()
    message = re.sub(r'[!,.?]', '', message)
    greetings = {
        "hi", "hello", "hey", "greetings", "good morning", "good afternoon", "good evening",
        "thanks", "thank you", "ok", "okay", "yo", "sup", "howdy", "what's up", "how are you", "how's it going",
        "what's new", "how have you been", "nice to meet you", "pleased to meet you", "good to see you", "long time no see", "welcome"
    }
    if message in greetings:
        return True
    for greet in greetings:
        if message.startswith(greet) and len(message.split()) <= 3:
            return True
    return False

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)