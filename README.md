# Layout Aware RAG with Evidence Pins Demo

A complete demonstration of the Layout Aware RAG system with clickable evidence pins, built with Docling for PDF parsing, Neo4j for vector storage, and Chainlit for the user interface.

## Features

- **PDF Upload & Processing**: Upload PDFs and automatically parse them with Docling
- **Structure-Aware Chunking**: Uses Docling's HybridChunker with merged bounding boxes for accurate evidence linking
- **Vector Search**: Semantic search using embeddings stored in Neo4j
- **Evidence Pins**: Clickable citations that link directly to PDF regions
- **Interactive Viewer**: PDF.js-based viewer with highlighted evidence regions

## Architecture

```
PDF Upload → Docling Parse → Structure-Aware Chunking → Neo4j Storage
     ↓              ↓              ↓                    ↓
Chainlit UI ← Citations ← Vector Search ← Embeddings + Bboxes
```

**Components:**
- **Neo4j**: Containerized database (Docker)
- **Backend API**: Local Python/FastAPI process
- **Frontend UI**: Local Python/Chainlit process

## Quick Start

### Prerequisites

- Python 3.11+
- Docker (for Neo4j 5.23+)
- Docling CLI installed

### 1. Start the Demo

```bash
./scripts/start-demo.sh
```

This will:
- Start Neo4j 5.23 database (Docker)
- Create Python 3.11 virtual environments
- Install dependencies (including Docling)
- Start backend API on port 8001 (with hot reload)
- Start Chainlit frontend on port 8000 (with hot reload)
- All services run in background

### 2. Test the Demo

```bash
./scripts/test-demo.sh
```

### 3. Use the Demo

1. Open http://localhost:8000 in your browser
2. Upload a PDF document
3. Ask questions about the document
4. Click on citation links to see evidence pins in the PDF

### 4. Stop the Demo

```bash
./scripts/stop-demo.sh
```

## Data Model

The system uses a Neo4j graph with the following structure:

```
Document {
  id: string
  title: string
  source_uri: string
  family: string
}

Page {
  docId: string
  page_num: int
  width: float
  height: float
}

Chunk {
  id: string
  page_num: int
  bbox: [float, float, float, float]  # [x0, y0, x1, y1]
  headings: string[]
  text: string
  embedding: float[384]  # sentence-transformers embedding
}

# Relationships
(Document)<-[:OF]-(Page)<-[:IN_PAGE]-(Chunk)
```

## API Endpoints

- `POST /upload` - Upload and process PDF
- `POST /query` - Query documents with vector search
- `GET /documents/{doc_id}` - Serve PDF files
- `GET /viewer` - PDF viewer with evidence pins
- `GET /health` - Health check

## Project Structure

```
layout-aware-rag-demo/
├── backend/
│   ├── main.py                 # FastAPI application
│   ├── models.py               # Pydantic models
│   ├── docling_processor.py    # PDF parsing and chunking
│   ├── neo4j_handler.py        # Database operations
│   ├── citation_processor.py   # Citation linking
│   ├── docker-compose.yml      # Neo4j database setup
│   └── requirements.txt
├── frontend/
│   ├── app.py                  # Chainlit application
│   ├── viewer.html             # PDF viewer with evidence pins
│   └── requirements.txt
├── scripts/
│   ├── start-demo.sh           # Start all services
│   ├── stop-demo.sh            # Stop all services
│   └── test-demo.sh            # Test service health
├── uploads/                    # Temporary upload storage
├── documents/                  # Processed PDF storage
└── README.md
```

## Environment Variables

### Backend (.env)
```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_secure_password
UPLOAD_DIR=../uploads
DOCUMENTS_DIR=../documents
```

### Frontend (.env)
```
BACKEND_URL=http://localhost:8001
```

## Improving Answer Accuracy with LLMs

**Current Implementation**: The demo uses simple keyword-based answer generation for demonstration purposes. For production use, integrating a Large Language Model (LLM) significantly improves answer quality and accuracy.

### Recommended LLM Integration Points

1. **Query Processing**: Use an LLM to:
   - Understand user intent and rephrase ambiguous queries
   - Generate multiple query variations for better retrieval
   - Extract key concepts and entities from questions

2. **Answer Synthesis**: Replace `CitationProcessor.generate_answer_with_citations()` with:
   - LLM-powered answer generation using retrieved chunks as context
   - Coherent synthesis of information from multiple sources
   - Proper citation attribution within generated responses

### Example LLM Integration

```python
# In citation_processor.py
def generate_answer_with_citations(self, query: str, search_results: List[QueryResult]) -> str:
    # Prepare context from search results
    context = "\n\n".join([
        f"Source [{result.chunk['id']}]: {result.chunk['text']}"
        for result in search_results[:5]
    ])

    # LLM prompt with context and query
    prompt = f"""
    Based on the following document excerpts, answer the question accurately.
    Include citations [chunk_id] after relevant statements.

    Context:
    {context}

    Question: {query}

    Answer:"""

    # Call your preferred LLM API (OpenAI, Anthropic, etc.)
    answer = your_llm_client.generate(prompt)
    return answer
```

### Recommended LLM Providers

- **OpenAI GPT-4**: Excellent general knowledge and citation handling
- **Anthropic Claude**: Strong document analysis and reasoning
- **Local Models**: Use Ollama for privacy-sensitive deployments
- **Azure OpenAI**: Enterprise-grade deployment with data residency

## Development

### Running Tests

```bash
# Backend tests
cd backend
python -m pytest

# Manual testing
curl -X GET http://localhost:8001/health
```

### Adding Features

1. **LLM Integration**: Replace keyword-based answers with proper LLM synthesis (see above)
2. **Custom Embeddings**: Modify `DoclingProcessor.get_embedding()` to use different models
3. **Query Enhancement**: Add LLM-powered query understanding and expansion
4. **Multi-document Search**: Extend queries to search across multiple documents
5. **Advanced Chunking**: Implement table-aware or section-based chunking strategies

## Troubleshooting

### Common Issues

1. **Neo4j connection failed**: Run `./scripts/start-demo.sh` to start all services
2. **Vector index errors**: Neo4j 5.23+ is automatically configured with vector support
3. **PDF processing timeout**: Large PDFs take time for Docling processing
4. **Dependencies missing**: Virtual environments auto-install all dependencies

### Logs

Check application logs for detailed error information:
- Backend: FastAPI logs
- Frontend: Chainlit logs in terminal
- Neo4j: Check Neo4j logs for database issues

## Production Considerations

- Use production-grade embedding models
- Implement proper error handling and retry logic
- Add authentication and rate limiting
- Use proper secrets management
- Scale Neo4j for production workloads
- Implement caching for frequently accessed documents

## License

This demo is provided for educational purposes. Check individual component licenses:
- Docling: MIT License
- Neo4j: Commercial/GPL dual license
- Chainlit: Apache 2.0 License