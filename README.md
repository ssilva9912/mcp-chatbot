# MCP Chatbot v1.0

An intelligent conversational AI system built with FastAPI, Streamlit, and Google Gemini, featuring Redis-based memory, smart routing, and extensible MCP (Model Context Protocol) tool integration.

---

## Features

- Redis Memory System – Persistent conversation history across sessions  
- Intelligent Query Routing – Automatic tool selection based on user intent  
- MCP Tool Integration – Extensible protocol for adding custom tools  
- Note Management – Add, search, and organize personal notes  
- Documentation Search – Search official docs from multiple libraries  
- Math Calculations – Safe mathematical expression evaluation  
- Natural Conversations – Direct Gemini integration for general chat  
- Modern Web UI – Clean Streamlit interface with real-time updates  
- Production Ready – Comprehensive error handling and monitoring  

---

## Quick Start

### Prerequisites

- Python 3.8+
- Redis server
- Google Gemini API key
- (Optional) Serper API key for documentation search

---

### Installation

```bash
# Clone the repository
git clone https://github.com/ssilva9912/mcp-chatbot.git
cd mcp-chatbot

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

### Environment Configuration

Create a `.env` file in the root directory:

```env
# REQUIRED: Gemini AI API
GEMINI_API_KEY=your_gemini_api_key_here

# REQUIRED: Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0

# OPTIONAL: Documentation Search
SERPER_API_KEY=your_serper_api_key_here

# OPTIONAL: Advanced Routing
USE_SIMPLE_ROUTER=true
```

---

### Launch the Application

**Terminal 1 – Start MCP Server:**

```bash
cd server
python server.py
```

**Terminal 2 – Start FastAPI Backend:**

```bash
cd api
python main.py
```

**Terminal 3 – Start Streamlit Frontend:**

```bash
streamlit run main.py
```

---

## Access the Application

- Frontend: http://localhost:8501  
- API Documentation: http://localhost:8000/docs  
- Health Check: http://localhost:8000/health  

---

## Project Structure

```
mcp-client/
├── api/
│   ├── main.py
│   ├── mcp_client.py
|   ├── .env
|   ├── utils/
|       └── __init__.py
|       └── simple_router.py
|       └── logger.py
│   └── memory/
│       └── redis_memory.py
|       └── Redis_test.py
|       └── sqlite_memory.py
|
├── server/
│   └── server.py
├── frontend/
|   └──chatbot.py
|   └──main.py
|
├── script.py
├── requirements.txt
└── README.md
```

---

## Available Tools

### Note Management

- `add_note`: Save personal notes and reminders  
- `read_notes`: View all saved notes  
- `search_notes`: Find notes by content  

### Documentation Search

- `get_docs`: Search official documentation  
  - Supported: LangChain, OpenAI, LlamaIndex, Anthropic, HuggingFace, PyTorch, TensorFlow

### Mathematics

- `simple_math`: Safe mathematical expression evaluation  

### General Chat

- `general_chat`: Natural conversations with Gemini  

---

## Usage Examples

### Basic Conversations

```
You: "Hello! How can I make a Caesar salad?"
Bot: "Hi! I'd be happy to help you make a delicious Caesar salad! Here's a classic recipe..."
```

### Note Management

```
You: "Add a note about my doctor appointment tomorrow at 3pm"
Bot: "Successfully saved note #1: 'doctor appointment tomorrow at 3pm'"
```

### Math Calculations

```
You: "What's 25 * 17 + 33?"
Bot: "25 * 17 + 33 = 458"
```

---

## API Endpoints

### Core

- `POST /query`: Process user queries  
- `GET /health`: System health check  
- `GET /status`: Detailed system status  
- `GET /tools`: List available tools  

### Memory Management

- `GET /conversations`: List all conversations  
- `GET /conversations/{session_id}`: Get specific conversation  
- `DELETE /conversations/{session_id}`: Clear conversation history  

---

## Testing & Debugging

### Health Checks

```bash
# Test Redis connection
python debug/debug_redis.py

# Test MCP server connection
python debug/focused_debug.py

# API health check
curl http://localhost:8000/health
```

---

## Common Issues

### Redis Connection Failed

```bash
docker run -d --name redis -p 6379:6379 redis:alpine
python debug/debug_redis.py
```

### MCP Server Not Found

```bash
python debug/focused_debug.py
cd server && python server.py
```

### Gemini API Issues

- Verify API key in `.env`  
- Check rate limits: https://ai.google.dev/gemini-api/docs/rate-limits  

---

## Configuration

### Router

Set in `.env`:

```env
USE_SIMPLE_ROUTER=true  # Basic routing
USE_SIMPLE_ROUTER=false # LLM-based routing
```






