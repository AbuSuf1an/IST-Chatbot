import os
import uuid
import psycopg2
import json
from typing import List, Dict, Optional
from datetime import datetime
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

class SessionManager:
    """Manages chat sessions and conversation history."""
    
    def __init__(self, db_config: Optional[Dict] = None):
        if db_config is None:
            # Get configuration from environment variables
            self.db_config = {
                'host': os.getenv('DB_HOST', 'localhost'),
                'port': os.getenv('DB_PORT', '5432'),
                'database': os.getenv('DB_NAME', 'ist_data'),
                'user': os.getenv('DB_USER', 'postgres'),
                'password': os.getenv('DB_PASSWORD', '')
            }
        else:
            self.db_config = db_config
    
    def create_session(self) -> str:
        """Create a new chat session and return session ID."""
        session_id = str(uuid.uuid4())
        logger.info(f"Created new session: {session_id}")
        return session_id
    
    def save_conversation(self, session_id: str, user_message: str, bot_response: str, metadata: Optional[Dict] = None):
        """Save a conversation turn to the database."""
        try:
            conn = psycopg2.connect(**self.db_config)
            cur = conn.cursor()
            
            metadata_json = json.dumps(metadata or {})
            
            cur.execute("""
                INSERT INTO chat_sessions (session_id, user_message, bot_response, metadata)
                VALUES (%s, %s, %s, %s)
            """, (session_id, user_message, bot_response, metadata_json))
            
            conn.commit()
            cur.close()
            conn.close()
            
            logger.info(f"Saved conversation for session {session_id}")
            
        except Exception as e:
            logger.error(f"Failed to save conversation: {e}")
            raise
    
    def get_session_history(self, session_id: str, limit: int = 10) -> List[Dict]:
        """Retrieve conversation history for a session."""
        try:
            conn = psycopg2.connect(**self.db_config)
            cur = conn.cursor()
            
            cur.execute("""
                SELECT user_message, bot_response, created_at, metadata
                FROM chat_sessions 
                WHERE session_id = %s 
                ORDER BY created_at ASC 
                LIMIT %s
            """, (session_id, limit))
            
            results = cur.fetchall()
            
            history = []
            for row in results:
                history.append({
                    'user_message': row[0],
                    'bot_response': row[1],
                    'created_at': row[2],
                    'metadata': json.loads(row[3]) if row[3] else {}
                })
            
            cur.close()
            conn.close()
            
            return history
            
        except Exception as e:
            logger.error(f"Failed to get session history: {e}")
            return []
    
    def clear_session(self, session_id: str):
        """Clear conversation history for a specific session."""
        try:
            conn = psycopg2.connect(**self.db_config)
            cur = conn.cursor()
            
            cur.execute("DELETE FROM chat_sessions WHERE session_id = %s", (session_id,))
            
            conn.commit()
            cur.close()
            conn.close()
            
            logger.info(f"Cleared session {session_id}")
            
        except Exception as e:
            logger.error(f"Failed to clear session: {e}")
            raise