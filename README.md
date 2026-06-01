# Analyst Report Search

A tool to find analyst reports from top firms like Gartner, Forrester, IDC, Everest Group, and Quadrant Knowledge Solutions using natural language queries.

## Features

- **Natural Language Queries**: Ask questions in plain English (e.g., "What are the typical names of analyst reports for ABM category from Gartner?")
- **Smart Query Conversion**: Uses LangChain and OpenAI to convert natural language into optimized search queries
- **Any Analyst Firm**: The LLM uses its inherent knowledge to identify any analyst firm and their specific report types (not limited to hardcoded firms)
- **Serper Search Integration**: Finds PDF reports from across the web, excluding official analyst firm sites to locate free copies
- **FastAPI Backend**: RESTful API for search functionality
- **Streamlit UI**: Clean, interactive web interface with search history
- **Parallel Search**: Generates multiple query variations and runs them in parallel for faster results

## Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment variables**:
   Create a `.env` file with:
   ```
   OPENAI_API_KEY=your_openai_api_key
   OPENAI_MODEL=gpt-4o-mini
   SERPER_API_KEY=your_serper_api_key
   API_URL=http://localhost:8000
   ```

3. **Get API Keys**:
   - OpenAI API Key: https://platform.openai.com/api-keys
   - Serper API Key: https://serper.dev/api-key

## Usage

Start the FastAPI backend:
```bash
python api.py
```

The API will be available at `http://localhost:8000`

In a separate terminal, start the Streamlit frontend:
```bash
streamlit run app.py
```

The app will open in your browser at `http://localhost:8501`

## Example Queries

- "What are the typical names of analyst reports for ABM category from Gartner?"
- "Find Forrester Wave reports for cloud security"
- "IDC MarketScape for CRM platforms"
- "Everest Group PEAK Matrix for RPA tools"

## How It Works

1. User enters a natural language query
2. LangChain + OpenAI generates 3-5 different search query variations
3. All queries are executed in parallel using ThreadPoolExecutor
4. Serper API searches the web for PDF reports
5. Results are aggregated and deduplicated by link
6. Results are displayed with links and snippets
7. Search history is maintained in the Streamlit session

## Architecture

- **api.py**: FastAPI backend with parallel search functionality
- **app.py**: Streamlit frontend that calls the FastAPI endpoints
- **LangChain**: Handles LLM integration and prompt templates
- **FastAPI**: Provides RESTful API endpoints
- **Serper**: Web search API for finding analyst reports

## API Endpoints

- `POST /search`: Search for analyst reports
  - Request body: `{"query": "your query"}`
  - Response: `{"search_query": "...", "search_results": [...]}`
- `GET /`: Root endpoint with API info
