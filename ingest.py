import os
import logging
from pathlib import Path
from typing import List, Any
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

from langchain_community.document_loaders import DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DocumentIngestor:    
    def __init__(self):
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432'),
            'database': os.getenv('DB_NAME', 'ist_data'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', 'password')
        }
        
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")
        
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/embedding-001",
            google_api_key=self.gemini_api_key
        )
        
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=3000,
            chunk_overlap=100,
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )
        
        self.data_folder = Path("data")
        
    def setup_database(self):
        try:
            conn = psycopg2.connect(**self.db_config)
            cur = conn.cursor()
            
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            
            cur.execute("DROP TABLE IF EXISTS documents CASCADE;")
            
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
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS documents_embedding_idx 
                ON documents USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS documents_filename_idx 
                ON documents (filename);
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS documents_created_at_idx 
                ON documents (created_at);
            """)
            
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
        if not self.data_folder.exists():
            logger.warning(f"Data folder '{self.data_folder}' does not exist. Creating it.")
            self.data_folder.mkdir(exist_ok=True)
            return []
        
        try:
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
        try:
            chunks = self.text_splitter.split_documents(documents)
            logger.info(f"Split documents into {len(chunks)} chunks")
            return chunks
            
        except Exception as e:
            logger.error(f"Failed to split documents: {str(e)}")
            raise
    
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        try:
            embeddings = self.embeddings.embed_documents(texts)
            logger.info(f"Generated embeddings for {len(texts)} text chunks")
            return embeddings
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {str(e)}")
            raise
    
    def store_in_database(self, chunks: List[Any], embeddings: List[List[float]]):
        try:
            conn = psycopg2.connect(**self.db_config)
            cur = conn.cursor()
            
            data_to_insert = []
            
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                filename = Path(chunk.metadata.get('source', 'unknown')).name
                
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
        try:
            conn = psycopg2.connect(**self.db_config)
            cur = conn.cursor()
            
            cur.execute("DROP TABLE IF EXISTS documents CASCADE;")
            
            conn.commit()
            cur.close()
            conn.close()
            
            logger.info("Existing documents table dropped successfully")
            
        except Exception as e:
            logger.error(f"Failed to drop existing table: {str(e)}")
            raise
    
    def ingest_documents(self, clear_existing: bool = False):
        try:
            logger.info("Starting document ingestion process...")
            
            if clear_existing:
                self.drop_existing_table()
            
            self.setup_database()
            
            if clear_existing:
                self.clear_existing_data()
            
            documents = self.load_documents()
            
            if not documents:
                logger.warning("No documents found to process")
                return
            
            chunks = self.split_documents(documents)
            
            if not chunks:
                logger.warning("No chunks created from documents")
                return
            
            texts = [chunk.page_content for chunk in chunks]
            
            embeddings = self.generate_embeddings(texts)
            
            self.store_in_database(chunks, embeddings)
            
            logger.info("Document ingestion completed successfully!")
            
        except Exception as e:
            logger.error(f"Document ingestion failed: {str(e)}")
            raise

def main():
    try:
        ingestor = DocumentIngestor()
        ingestor.ingest_documents(clear_existing=True)
        
        print("✅ Document ingestion completed successfully!")
        
    except Exception as e:
        print(f"❌ Document ingestion failed: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main()
