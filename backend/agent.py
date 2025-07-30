# agent.py

from flask import Flask, request, jsonify
from flask_cors import CORS
import asyncio
import uuid
from pathlib import Path
from textwrap import dedent

# Web scraping imports
import requests
from bs4 import BeautifulSoup
import re

# --- Agno & OpenAI Libraries ---
try:
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    from agno.tools.googlesearch import GoogleSearchTools
    from agno.tools.mcp import MCPTools
    from agno.tools import tool
    from agno.tools.user_control_flow import UserControlFlowTools
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Hata: Gerekli kütüphanelerden biri eksik: {e}")
    exit(1)

# --- Flask, CORS, Project Configuration ---
app = Flask(__name__)
CORS(app)
load_dotenv()
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# --- Global State ---
pending_runs = {}

# --- Custom Tool: read_articles ---
@tool
def read_articles(urls: list[str]) -> str:
    """Fetch and combine readable text content from multiple URLs into a single string."""
    combined_text = ""
    for url in urls:
        try:
            response = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            
            # Encoding'i düzgün handle et
            if response.encoding is None:
                response.encoding = 'utf-8'
            
            # BeautifulSoup'a düzgün encoded text ver
            try:
                # Önce response.text kullanmayı dene (otomatik encoding)
                soup = BeautifulSoup(response.text, 'html.parser')
            except UnicodeDecodeError:
                # Eğer hata olursa utf-8 ile zorla
                soup = BeautifulSoup(response.content.decode('utf-8', errors='ignore'), 'html.parser')
            
            # Sadece ana içerik alanlarını al
            # Scripttleri, style'ları ve navigation'ları kaldır
            for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                element.decompose()
            
            text = soup.get_text(separator=' ', strip=True)
            
            # Fazla boşlukları temizle
            text = re.sub(r'\s+', ' ', text)
            text = re.sub(r'\n\s*\n', '\n\n', text)
            
            # Sadece yazdırılabilir karakterleri tut
            text = ''.join(char for char in text if char.isprintable() or char in '\n\t')
            
            combined_text += f"\n\n--- CONTENT FROM {url} ---\n\n{text[:5000]}"  # İlk 5000 karakter
            
        except Exception as e:
            combined_text += f"\n\n--- ERROR READING {url}: {str(e)} ---\n\n"
    
    return combined_text

# ==============================================================================
# STEP 1: GENERATE QUERIES AND PAUSE FOR APPROVAL
# ============================================================================== 2 agent | 1 Agent --> market research & gerekli linkleri çıkart, okumayı yap, analiz  --> MCPye ihtiyacı yok GoogleSearchTools()
# ------------------------------------------------------------------------------         | 1 Agent --> sonuçları incele, proposal'ı yaz, MCP'ye bas | MCPye ihtiyacı var --> MCPTools()

@app.route('/generate-queries', methods=['POST'])
def generate_queries_endpoint():
    data = request.json
    user_message = data.get('message')
    if not user_message:
        return jsonify({'error': 'Message cannot be empty'}), 400

    session_id = str(uuid.uuid4())

    async def _run():
        # This agent now has a multi-step plan.
        query_and_search_agent = Agent(
            model=OpenAIChat(id="gpt-4o-mini"),
            # Give it all the tools it will need for the entire task.
            tools=[UserControlFlowTools(), GoogleSearchTools()],
            instructions=[
                "You have a two-step job.",
                "STEP 1: Take a topic from the user, generate 5 relevant Google search queries, and then immediately call the `get_user_input` tool to get user approval for these queries. Put each generated query into the `field_description` of a separate field.",
                "STEP 2: After the user approves the queries, you will receive them as the result of the tool call. Then, for each approved query, execute a `google_search` and collect the most relevant 3 of the resulting URLs.",
                "Finally, output a single, flat list of all the URLs you found. Your final output must only be the list of URLs."
            ],
            session_id=session_id,
            debug_mode=True
        )

        response = await query_and_search_agent.arun(user_message)

        if response.is_paused:
            run_id = response.run_id
            # Store the agent instance itself to continue its session later
            pending_runs[run_id] = {'agent': query_and_search_agent}

            queries = []
            for tool in response.tools_requiring_user_input:
                if tool.tool_name == 'get_user_input':
                    for field in tool.user_input_schema:
                        queries.append({'query': field.description, 'field_name': field.name})
            
            return jsonify({
                'is_paused': True,
                'run_id': run_id,
                'queries': queries,
                'message': 'Please approve the search queries.'
            })
        
        return jsonify({'error': "Agent did not pause for user confirmation."}), 500

    return asyncio.run(_run())

# ==============================================================================
# STEP 2: EXECUTE SEARCH WITH APPROVED QUERIES
# ==============================================================================

@app.route('/execute-search', methods=['POST'])
def execute_search_endpoint():
    data = request.json
    run_id = data.get('run_id')
    approved_queries = data.get('approved_queries', [])

    if not run_id or run_id not in pending_runs:
        return jsonify({'error': 'Invalid run_id'}), 404

    # Retrieve the agent instance from the previous step
    run_info = pending_runs.pop(run_id)
    agent = run_info['agent']
    
    run_response = agent.run_response
    if not run_response or not run_response.is_paused:
        return jsonify({'error': 'This run is not in a paused state.'}), 400

    async def _run():
        # Process user approvals from the frontend
        approved_map = {q['field_name']: q['query'] for q in approved_queries if q.get('approved', True)}
        for tool in run_response.tools_requiring_user_input:
            if tool.tool_name == 'get_user_input':
                for field in tool.user_input_schema:
                    # Provide the approved query as the 'value' for the input field
                    field.value = approved_map.get(field.name, "")

        # **FIXED**: Continue the run without the invalid 'user_message' argument.
        # The agent will now follow STEP 2 of its original instructions.
        response = await agent.acontinue_run(run_response=run_response)

        # The agent's final content should be the list of URLs
        return jsonify({'urls': response.content, 'message': 'URLs collected successfully.'})

    return asyncio.run(_run())

# ==============================================================================
# STEP 3: ANALYZE, PROPOSE, AND SAVE
# ==============================================================================

@app.route('/analyze-and-propose', methods=['POST'])
def analyze_and_propose_endpoint():
    data = request.json
    urls = data.get('urls') # This is a text block containing URLs
    if not urls:
        return jsonify({'error': 'URL list cannot be empty'}), 400
        
    session_id = str(uuid.uuid4())

    async def _run():
        async with MCPTools(f"npx -y @modelcontextprotocol/server-filesystem {OUTPUT_DIR.resolve()}", timeout_seconds=30) as fs_tools:
            orchestrator_agent = Agent(
                model=OpenAIChat(id="gpt-4o"),
                tools=[read_articles, fs_tools],
                instructions=[
                    "You are a Senior Business Analyst.",
                    "1. You will be given a block of text containing URLs. Your first step is to extract these URLs.",
                    "2. For each URL, call `read_articles` with a single URL in a list (e.g., read_articles(['url1']), then read_articles(['url2']), etc.). This prevents token limit issues.",
                    "3. Analyze the combined content from all URLs to identify key market insights, competitors, and opportunities.",
                    "4. Write a comprehensive, investor-ready business proposal in Turkish based on your analysis.",
                    "5. Call `write_file` to save the proposal to 'output/business_proposal.md'.",
                    "6. Return ONLY the proposal text ONLY ONCE without any additional commentary or analysis.",
                    "IMPORTANT: Do not repeat the proposal text. Return it only once at the end.",
                    "CRITICAL: Call read_articles separately for each URL to avoid token limits. Do NOT pass all URLs at once.",
                ],
                session_id=session_id,
                debug_mode=True
            )

            response = await orchestrator_agent.arun(f"Analyze the content from these URLs and write a proposal: {urls}")
            return jsonify({'proposal': response.content, 'message': 'Business proposal created and saved successfully.'})

    return asyncio.run(_run())


if __name__ == '__main__':
    app.run(debug=True, port=5001)