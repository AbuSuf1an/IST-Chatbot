# IST Chatbot Backend

A FastAPI-based chatbot backend that provides AI-powered responses to questions about Institute of Science and Technology (IST) using document retrieval and Google's Gemini AI model.

## Features

- **Document Ingestion**: Process and store PDF documents with embeddings in PostgreSQL
- **Semantic Search**: Find relevant documents using vector similarity search
- **AI Responses**: Generate contextual responses using Google's Gemini model
- **FastAPI Backend**: RESTful API with automatic documentation
- **CORS Support**: Ready for integration with WordPress sites
- **Health Monitoring**: Built-in health check endpoints

## Setup Instructions

### 1. Prerequisites

- Python 3.8+
- PostgreSQL with pgvector extension
- Google AI API key
- System dependencies: `poppler`, `tesseract`

### 2. Environment Setup

```bash
# Clone/navigate to the project directory
cd ist-chatbot

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install Python dependencies
pip install fastapi uvicorn pydantic psycopg2-binary python-dotenv
pip install langchain-google-genai langchain-community langchain-text-splitters
pip install "unstructured[pdf]" pypdf pymupdf nltk beautifulsoup4

# Install system dependencies (macOS)
brew install poppler tesseract

# Download NLTK data
python -c "import ssl; import nltk; ssl._create_default_https_context = ssl._create_unverified_context; nltk.download('punkt_tab'); nltk.download('averaged_perceptron_tagger_eng')"
```

### 3. Environment Variables

Create a `.env` file in the project root:

```env
# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=ist_data
DB_USER=postgres
DB_PASSWORD=your_db_password

# Google AI API Key
gemini_api_key=your_gemini_api_key
```

### 4. Database Setup

Ensure PostgreSQL is running with the pgvector extension:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 5. Document Ingestion

Place your PDF documents in the `data/` folder and run:

```bash
python ingest.py
```

This will:
- Process PDF documents
- Generate embeddings
- Store chunks in PostgreSQL

### 6. Start the API Server

```bash
python main.py
```

The server will start on `http://localhost:8001`

## API Documentation

### Endpoints

#### Health Check
- **GET** `/` - Basic health check
- **GET** `/health` - Detailed health information

#### Chat
- **POST** `/api/chat` - Main chat endpoint

### Chat API Usage

**Request:**
```json
{
  "message": "What is IST?"
}
```

**Response:**
```json
{
  "response": "Institute of Science and Technology (IST) is...",
  "context_sources": ["ist-info-from-website.pdf"]
}
```

### Example Usage

#### cURL
```bash
curl -X POST "http://localhost:8001/api/chat" \
     -H "Content-Type: application/json" \
     -d '{"message": "What courses does IST offer?"}'
```

#### JavaScript (for WordPress integration)
```javascript
async function sendMessage(message) {
    const response = await fetch('http://localhost:8001/api/chat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: message })
    });
    
    const data = await response.json();
    return data.response;
}
```

## WordPress Integration

### 1. CORS Configuration

The API includes CORS middleware that allows requests from any origin. For production, update the `allow_origins` in `main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-wordpress-site.com"],  # Specify your domain
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

### 2. WordPress Plugin/Theme Integration

Add the following JavaScript to your WordPress theme or create a custom plugin:

```javascript
// Add to your theme's functions.php or create a plugin
function enqueue_chatbot_script() {
    wp_enqueue_script('chatbot', get_template_directory_uri() . '/js/chatbot.js', array('jquery'), '1.0.0', true);
    wp_localize_script('chatbot', 'chatbot_ajax', array(
        'api_url' => 'http://localhost:8001/api/chat'
    ));
}
add_action('wp_enqueue_scripts', 'enqueue_chatbot_script');
```

### 3. Frontend Implementation

Use the provided `test_chatbot.html` as a reference for implementing the chat interface in WordPress.

## Project Structure

```
ist-chatbot/
├── main.py              # FastAPI application
├── ingest.py            # Document ingestion script
├── .env                 # Environment variables
├── test_chatbot.html    # Test interface
├── data/                # PDF documents
│   └── ist-info-from-website.pdf
└── README.md           # This file
```

## Troubleshooting

### Common Issues

1. **Database Connection Error**
   - Ensure PostgreSQL is running
   - Check database credentials in `.env`
   - Verify pgvector extension is installed

2. **PDF Processing Error**
   - Install system dependencies: `brew install poppler tesseract`
   - Download NLTK data as shown in setup

3. **Gemini API Error**
   - Verify `gemini_api_key` is correct
   - Check API quotas and limits

4. **CORS Issues**
   - Update `allow_origins` in CORS middleware
   - Ensure proper headers are sent from frontend

### Logging

The application logs all important events. Check the console output for detailed error messages.

### Development Mode

For development, you can enable auto-reload:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

## Production Deployment

For production deployment:

1. Use a proper WSGI server (e.g., Gunicorn with Uvicorn workers)
2. Set up a reverse proxy (Nginx)
3. Use environment-specific configuration
4. Enable HTTPS
5. Configure proper CORS origins
6. Set up monitoring and logging

Example production command:
```bash
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8001
```

## License

This project is provided as-is for educational and development purposes.
