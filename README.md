# IST Chatbot Document Ingestion

This script loads documents from a 'data' folder, splits them into chunks, generates embeddings using Google Generative AI, and stores them in a PostgreSQL database with pgvector extension.

## Prerequisites

1. **PostgreSQL with pgvector extension**: Make sure you have PostgreSQL installed with the pgvector extension enabled.
2. **Google AI API Key**: You need a Google AI API key to generate embeddings.

## Setup

1. **Install dependencies** (already done if you used the install command):
   ```bash
   pip install langchain langchain-community langchain-google-genai psycopg2-binary python-dotenv pgvector
   ```

2. **Configure environment variables**:
   - Copy `.env.example` to `.env`
   - Update the database connection details
   - Add your Google AI API key

3. **Prepare your documents**:
   - Place your documents (PDF, TXT, DOCX, etc.) in the `data/` folder
   - The script supports various document formats through LangChain loaders

## Database Setup

The script will automatically:
- Enable the pgvector extension
- Create the `documents` table with the following schema:
  - `id`: Primary key
  - `filename`: Source document filename
  - `content`: Text content of the chunk
  - `chunk_index`: Index of the chunk within the document
  - `embedding`: Vector embedding (768 dimensions for Google's embedding model)
  - `metadata`: Additional metadata from the document
  - `created_at`: Timestamp when the record was created

## Usage

Run the ingestion script:

```bash
python ingest.py
```

The script will:
1. Set up the database tables
2. Load documents from the `data/` folder
3. Split documents into manageable chunks (1000 characters with 200 character overlap)
4. Generate embeddings using Google's embedding model
5. Store everything in PostgreSQL

## Features

- **Automatic chunking**: Documents are split into optimal sizes for embedding
- **Batch processing**: Embeddings are generated and stored efficiently
- **Metadata preservation**: Document metadata is preserved in JSONB format
- **Vector indexing**: Automatic creation of IVFFLAT index for fast similarity search
- **Error handling**: Comprehensive logging and error handling
- **Flexible configuration**: Easy to customize chunk sizes and database settings

## Configuration Options

You can modify the following in the `DocumentIngestor` class:

- **Chunk size**: Default 1000 characters
- **Chunk overlap**: Default 200 characters
- **Embedding model**: Default "models/embedding-001"
- **Database table name**: Default "documents"

## Troubleshooting

1. **Database connection issues**: Verify your PostgreSQL is running and connection details are correct
2. **pgvector extension**: Make sure pgvector is installed in your PostgreSQL instance
3. **Google API key**: Ensure your API key is valid and has the necessary permissions
4. **Document loading**: Check that your documents are in supported formats and accessible
