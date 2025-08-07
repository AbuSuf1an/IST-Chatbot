#!/usr/bin/env python3
"""
Document Ingestion Script for IST Chatbot
Loads documents from 'data' folder, splits them into chunks, generates embeddings 
using Google Generative AI, and stores them in PostgreSQL with pgvector extension.
"""

import os
import logging
from pathlib import Path
from typing import List, Dict, Any
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# LangChain imports
from langchain_community.document_loaders import DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DocumentIngestor:
    """Handles document loading, processing, and storage in PostgreSQL with pgvector."""
    
    def __init__(self):
        """Initialize the document ingestor with database and embedding configurations."""
        # Database configuration
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432'),
            'database': os.getenv('DB_NAME', 'chatbot_db'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', 'password')
        }
        
        # Google AI API key
        self.google_api_key = os.getenv('GOOGLE_API_KEY')
        if not self.google_api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is required")
        
        # Initialize embeddings
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/embedding-001",
            google_api_key=self.google_api_key
        )
        
        # Text splitter configuration
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )
        
        # Data folder path
        self.data_folder = Path("data")
        
    def setup_database(self):
        """Create the necessary database tables and enable pgvector extension."""
        try:
            conn = psycopg2.connect(**self.db_config)
            cur = conn.cursor()
            
            # Enable pgvector extension
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            
            # Drop existing table if it exists
            cur.execute("DROP TABLE IF EXISTS documents CASCADE;")
            cur.execute("DROP TABLE IF EXISTS chat_sessions CASCADE;")
            
            # Create documents table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id SERIAL PRIMARY KEY,
                    filename VARCHAR(255) NOT NULL,
                    content TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    embedding VECTOR(768),
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Create chat sessions table for conversation history
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(255) UNIQUE NOT NULL,
                    user_message TEXT NOT NULL,
                    bot_response TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata JSONB
                );
            """)
            
            # Create index on embedding column for faster similarity search
            cur.execute("""
                CREATE INDEX IF NOT EXISTS documents_embedding_idx 
                ON documents USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
            """)
            
            # Create index on session_id for faster session queries
            cur.execute("""
                CREATE INDEX IF NOT EXISTS chat_sessions_session_id_idx 
                ON chat_sessions (session_id);
            """)
            
            # Create index on created_at for chronological ordering
            cur.execute("""
                CREATE INDEX IF NOT EXISTS chat_sessions_created_at_idx 
                ON chat_sessions (created_at);
            """)
            
            # Create additional indexes for better query performance
            cur.execute("""
                CREATE INDEX IF NOT EXISTS documents_filename_idx 
                ON documents (filename);
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS documents_created_at_idx 
                ON documents (created_at);
            """)
            
            # Create index on metadata for JSONB queries
            cur.execute("""
                CREATE INDEX IF NOT EXISTS documents_metadata_idx 
                ON documents USING GIN (metadata);
            """)
            
            conn.commit()
            cur.close()
            conn.close()
            
            logger.info("Database table and indexes created successfully")
            
        except Exception as e:
            logger.error(f"Database table creation failed: {str(e)}")
            raise
    
    def load_documents(self) -> List[Any]:
        """Load documents from the data folder."""
        if not self.data_folder.exists():
            logger.warning(f"Data folder '{self.data_folder}' does not exist. Creating it.")
            self.data_folder.mkdir(exist_ok=True)
            return []
        
        try:
            # Load documents from various file types
            loader = DirectoryLoader(
                str(self.data_folder),
                glob="**/*",
                show_progress=True,
                use_multithreading=True
            )
            
            documents = loader.load()
            logger.info(f"Loaded {len(documents)} documents from {self.data_folder}")
            
            return documents
            
        except Exception as e:
            logger.error(f"Failed to load documents: {str(e)}")
            raise
    
    def split_documents(self, documents: List[Any]) -> List[Any]:
        """Split documents into smaller chunks."""
        try:
            chunks = self.text_splitter.split_documents(documents)
            logger.info(f"Split documents into {len(chunks)} chunks")
            return chunks
            
        except Exception as e:
            logger.error(f"Failed to split documents: {str(e)}")
            raise
    
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for text chunks using Google Generative AI."""
        try:
            embeddings = self.embeddings.embed_documents(texts)
            logger.info(f"Generated embeddings for {len(texts)} text chunks")
            return embeddings
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {str(e)}")
            raise
    
    def store_in_database(self, chunks: List[Any], embeddings: List[List[float]]):
        """Store document chunks and embeddings in PostgreSQL database."""
        try:
            conn = psycopg2.connect(**self.db_config)
            cur = conn.cursor()
            
            # Prepare data for insertion
            data_to_insert = []
            
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                # Extract filename from source metadata
                filename = Path(chunk.metadata.get('source', 'unknown')).name
                
                # Prepare metadata (excluding source to avoid duplication) and convert to JSON string
                metadata = {k: v for k, v in chunk.metadata.items() if k != 'source'}
                import json
                metadata_json = json.dumps(metadata)
                
                data_to_insert.append((
                    filename,
                    chunk.page_content,
                    i,
                    embedding,
                    metadata_json
                ))
            
            # Insert data in batches
            execute_values(
                cur,
                """
                INSERT INTO documents (filename, content, chunk_index, embedding, metadata)
                VALUES %s
                """,
                data_to_insert,
                template=None,
                page_size=100
            )
            
            conn.commit()
            cur.close()
            conn.close()
            
            logger.info(f"Successfully stored {len(data_to_insert)} document chunks in database")
            
        except Exception as e:
            logger.error(f"Failed to store data in database: {str(e)}")
            raise
    
    def clear_existing_data(self):
        """Clear existing documents from the database."""
        try:
            conn = psycopg2.connect(**self.db_config)
            cur = conn.cursor()
            
            cur.execute("DELETE FROM documents;")
            conn.commit()
            
            cur.close()
            conn.close()
            
            logger.info("Cleared existing documents from database")
            
        except Exception as e:
            logger.error(f"Failed to clear existing data: {str(e)}")
            raise
    
    def drop_existing_table(self):
        """Drop the documents table if it exists."""
        try:
            conn = psycopg2.connect(**self.db_config)
            cur = conn.cursor()
            
            # Drop the documents table if it exists
            cur.execute("DROP TABLE IF EXISTS documents CASCADE;")
            
            conn.commit()
            cur.close()
            conn.close()
            
            logger.info("Existing documents table dropped successfully")
            
        except Exception as e:
            logger.error(f"Failed to drop existing table: {str(e)}")
            raise
    
    def ingest_documents(self, clear_existing: bool = False):
        """Main method to orchestrate the document ingestion process."""
        try:
            logger.info("Starting document ingestion process...")
            
            # Drop existing table if requested
            if clear_existing:
                self.drop_existing_table()
            
            # Setup database
            self.setup_database()
            
            # Clear existing data if requested
            if clear_existing:
                self.clear_existing_data()
            
            # Load documents
            documents = self.load_documents()
            
            if not documents:
                logger.warning("No documents found to process")
                return
            
            # Split documents into chunks
            chunks = self.split_documents(documents)
            
            if not chunks:
                logger.warning("No chunks created from documents")
                return
            
            # Extract text content for embedding generation
            texts = [chunk.page_content for chunk in chunks]
            
            # Generate embeddings
            embeddings = self.generate_embeddings(texts)
            
            # Store in database
            self.store_in_database(chunks, embeddings)
            
            logger.info("Document ingestion completed successfully!")
            
        except Exception as e:
            logger.error(f"Document ingestion failed: {str(e)}")
            raise

def main():
    """Main entry point for the script."""
    try:
        # Create ingestor instance
        ingestor = DocumentIngestor()
        
        # Run ingestion process
        ingestor.ingest_documents(clear_existing=True)
        
        print("✅ Document ingestion completed successfully!")
        
    except Exception as e:
        print(f"❌ Document ingestion failed: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main()
