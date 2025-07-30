from flask import Flask, request, jsonify
from flask_cors import CORS
import asyncio
import uuid
from pathlib import Path
from textwrap import dedent
import re
import requests
from bs4 import BeautifulSoup
from enum import Enum
from dataclasses import dataclass
from typing import Optional
from agno.models.message import Message



# --- Agno & OpenAI Kütüphaneleri ---
try:
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    from agno.team import Team
    from agno.tools.googlesearch import GoogleSearchTools
    from agno.tools.mcp import MCPTools
    from agno.tools import tool
    from agno.memory.v2 import Memory, MemoryManager
    from agno.memory.v2.db.sqlite import SqliteMemoryDb
    from agno.tools.user_control_flow import UserControlFlowTools
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Hata: Gerekli kütüphanelerden biri eksik: {e}")
    exit(1)

# --- Flask ve CORS Kurulumu ---
app = Flask(__name__)
CORS(app)

# --- Proje Konfigürasyonu ---
load_dotenv()
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# --- İş Akışı Aşamaları ---
class ProposalStage(Enum):
    INIT = "init"
    RESEARCH = "research"  # Searcher aşaması
    AWAITING_CONFIRM = "awaiting_confirm"  # Kullanıcı onayı bekleniyor
    ANALYSIS = "analysis"  # Summarizer aşaması
    WRITING = "writing"    # Proposer aşaması
    SAVING = "saving"      # Dosya kaydetme aşaması
    COMPLETE = "complete"
    ERROR = "error"

@dataclass
class StageInfo:
    stage: ProposalStage
    progress: int  # 0-100 arası
    message: str

# Aşama bilgilerini saklamak için global değişken
current_stage: Optional[StageInfo] = None

# Pending runs storage
pending_runs = {}

def update_stage(stage: ProposalStage, message: str = "") -> None:
    """İş akışı aşamasını günceller ve ilerleme yüzdesini hesaplar"""
    global current_stage
    
    # Her aşama için ilerleme yüzdesi
    progress_map = {
        ProposalStage.INIT: 0,
        ProposalStage.RESEARCH: 15,
        ProposalStage.AWAITING_CONFIRM: 25,
        ProposalStage.ANALYSIS: 50,
        ProposalStage.WRITING: 75,
        ProposalStage.SAVING: 90,
        ProposalStage.COMPLETE: 100,
        ProposalStage.ERROR: 0
    }
    
    stage_messages = {
        ProposalStage.INIT: "Hazırlanıyor...",
        ProposalStage.RESEARCH: "Arama sorguları hazırlanıyor...",
        ProposalStage.AWAITING_CONFIRM: "Arama sorgularının onayı bekleniyor...",
        ProposalStage.ANALYSIS: "Bilgiler analiz ediliyor...",
        ProposalStage.WRITING: "İş teklifi yazılıyor...",
        ProposalStage.SAVING: "Doküman kaydediliyor...",
        ProposalStage.COMPLETE: "Tamamlandı!",
        ProposalStage.ERROR: "Bir hata oluştu!"
    }

    current_stage = StageInfo(
        stage=stage,
        progress=progress_map[stage],
        message=message or stage_messages[stage]
    )

# --- Custom Tools ---
@tool
def read_articles(urls: list[str]) -> dict[str, str]:
    """Fetch readable text content from multiple URLs. Returns a dictionary mapping each URL to its extracted text."""
    results = {}
    for url in urls:
        try:
            response = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            
            # Encoding'i düzgün handle et
            if response.encoding is None:
                response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Scripttleri, style'ları ve navigation'ları kaldır
            for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                element.decompose()
            
            text = soup.get_text(separator=' ', strip=True)
            
            # Fazla boşlukları temizle
            text = re.sub(r'\s+', ' ', text)
            text = re.sub(r'\n\s*\n', '\n\n', text)
            
            # Sadece yazdırılabilir karakterleri tut
            text = ''.join(char for char in text if char.isprintable() or char in '\n\t')
            
            results[url] = text[:5000]  # İlk 5000 karakter
            
        except Exception as e:
            results[url] = f"Error reading article: {str(e)}"
    return results

# --- Agent Definitions with State Management ---
class StateAwareAgent(Agent):
    def __init__(self, *args, **kwargs):
        self.stage = kwargs.pop('stage', ProposalStage.INIT)
        super().__init__(*args, **kwargs)

    async def arun(self, *args, **kwargs):
        update_stage(self.stage)
        return await super().arun(*args, **kwargs)

# Updated searcher with improved user control flow instructions
searcher = StateAwareAgent(
    name="Searcher",
    role="Searches the top URLs for a topic",
    model=OpenAIChat(id="gpt-4o-mini"),
    stage=ProposalStage.RESEARCH,
    instructions=[
        "Your task is to find the best URLs about a given topic through user control flow:",
        "1. **Generate Search Queries**: Create 5 relevant search terms for the topic.",
        "2. **Get User Approval**: Use get_user_input tool to present these queries:",
        "   - Create 5 fields: query_1, query_2, query_3, query_4, query_5",
        "   - Put your proposed search query in the field_description",
        "   - Example: field_name='query_1', field_description='köpek gezdirme uygulamaları inceleme'",
        "3. **Execute Searches**: After receiving user input, use the approved queries to search.",
        "4. **Return URLs**: For each query, find 3 best URLs and return them all.",
        "IMPORTANT: Always use get_user_input first before doing any searches.",
        "The field_description should contain your proposed search query text.",
    ],
    tools=[GoogleSearchTools(), UserControlFlowTools()],
    monitoring=True,
)

summarizer = StateAwareAgent(
    name="Summarizer", 
    role="Summarizes article content to extract key pain points and business takeaways",
    description="Given a long article, this agent produces a concise summary of the pain points, key facts, and insights.",
    model=OpenAIChat(id="gpt-4o-mini"),
    stage=ProposalStage.ANALYSIS,
    instructions=[
        "Read all articles given to you by the Searcher Agent, one by one.",
        "Return a short, structured summary that captures:",
        "- Main pain points discussed",
        "- Any key facts, stats, or trends", 
        "- The core takeaway(s) for business or product strategy",
        "Use bullet points or short paragraphs for clarity.",
        "Be objective with your statements and reviews.",
        "Do not include advertisement baits",
        "Lastly, return a synthesized summary of all articles combined.",
    ],
    tools=[read_articles],
    monitoring=True,
)

proposer = StateAwareAgent(
    name="Proposer",
    role="Writes a high‑quality business proposal",
    description=(
        "Sen bir Girişim Danışmanlığı Şirketinde kıdemli bir Business Analyst Uzmanısın. Sana bir konu ve yapılmış competitor analysis verildiğinde, amacın bu konu hakkında yüksek kaliteli bir iş teklifi yazmaktır."
    ),
    stage=ProposalStage.WRITING,
    instructions=[
        "Summarizer Agent'ın sana ilettiği competitor analysis bilgilerini de kullanarak konu hakkında yüksek kaliteli ve Türkçe dilinde bir iş teklifi yaz.",
        "Teklif iyi yapılandırılmış, bilgilendirici, örneklendirici ve eleştirel olmalıdır.",
        "Mümkün olduğunda gerçekleri alıntılayarak nüanslı ve dengeli bir bakış açısı sun.",
        "Açıklık, tutarlılık ve genel kaliteye odaklan.",
        "Asla gerçek uydurma veya intihal yapma. Her zaman uygun atıf ver.",
        "Unutma: Tanınmış bir Startup Danışmanlık Şirketi için yazıyorsun, bu nedenle teklifin kalitesi çok önemlidir.",
    ],
    monitoring=True,
)

# --- Configuration & Memory Setup ---
USER_MEMORY_DB_FILE = Path(__file__).parent / "memory/user_preferences.db"
USER_MEMORY_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
user_memory_db = SqliteMemoryDb(table_name="user_memories", db_file=str(USER_MEMORY_DB_FILE))

memory_manager = MemoryManager(memory_capture_instructions=dedent("""
    Your job is to capture only the most valuable, final outputs from a conversation.
    - WHAT TO SAVE:
    1. The user's initial request/topic.
    2. The final, complete business proposal text.
    3. Key pain points identified by the Searcher agent.
    - WHAT TO IGNORE:
    - DO NOT save URL lists, search results, raw website text, intermediate summaries, or other unprocessed data.
    - Your goal is to store the refined, final output that can be useful for future reference. If the input text does not fit this description, ignore it.
"""))

# --- Unified Agent Logic ---
async def run_business_proposal_team(user_message: str, user_id: str, session_id: str) -> dict:
    """
    Runs the full agent team to generate or revise a business proposal.
    Returns both the response content and the current stage information.
    """
    try:
        update_stage(ProposalStage.INIT)
        memory_instance = Memory(db=user_memory_db, memory_manager=memory_manager)        
        
        team_instructions = [
            "You are a Senior Publisher. Your primary goal is to produce a high-quality, investor-ready business proposal based on a user's request.",
            "Your workflow:",
            "1. **NEW PROPOSAL**: For new topics, coordinate the team:",
            "   - FIRST, immediately instruct 'Searcher' to find relevant URLs using user-approved search queries",
            "   - IMPORTANT: The Searcher agent will use get_user_input to present 5 search queries (query_1 to query_5) for user approval",
            "   - Then, have 'Summarizer' analyze the content from those URLs", 
            "   - Finally, have 'Proposer' write a comprehensive business proposal in Turkish",
            "2. **REVISION**: For revisions, read existing files and update them",
            "3. **SAVE RESULTS**: Always save the final proposal to output/ directory",
            "CRITICAL: All file paths must start with 'output/' prefix.",
            "CRITICAL: Always start by transferring the task to 'Searcher' first - do not use get_user_input yourself.",
            "Focus on clarity, coherence, and overall quality."
        ]
        
        #  MCP sunucusunu başlat ve bağlantıyı kur
        mcp_server_command = f"npx -y @modelcontextprotocol/server-filesystem {OUTPUT_DIR.resolve()}"
        mcp_tools = MCPTools(mcp_server_command, timeout_seconds=30)
        await mcp_tools.__aenter__()

        try:
            editor_team = Team(
                name="Publisher",
                mode="coordinate",
                model=OpenAIChat(id="gpt-4o-mini"),
                members=[searcher, summarizer, proposer],
                # --- DEĞİŞİKLİK BURADA ---
                # UserControlFlowTools'u ana takımın araçlarına ekliyoruz.
                tools=[mcp_tools, UserControlFlowTools()],
                # -------------------------
                memory=memory_instance,
                enable_user_memories=True,
                add_history_to_messages=True, 
                user_id=user_id,
                session_id=session_id,
                description=(
                    "Sen kıdemli bir yayıncısın. Sana bir iş fikri verildiğinde, amacın detaylı, eleştirel ve yatırımcıya hazır bir iş teklifi sunmaktır."
                ),
                instructions=team_instructions,
                add_datetime_to_instructions=True,
                add_member_tools_to_system_message=False,
                enable_agentic_context=True,
                share_member_interactions=True,
                # Önceki öneriyi de koruyalım, bu en stabil sonucu verir.
                show_members_responses=False,
                markdown=True,
                debug_mode=True
            )

            response = await editor_team.arun(user_message)
            
            # DEBUG: Log paused state
            print(f"DEBUG: Team response.is_paused: {response.is_paused}")
            print(f"DEBUG: Team response has tools_requiring_user_input: {hasattr(response, 'tools_requiring_user_input')}")
            if hasattr(response, 'tools_requiring_user_input'):
                print(f"DEBUG: Team tools count: {len(response.tools_requiring_user_input) if response.tools_requiring_user_input else 0}")
            
            # Check if any agent needs user input
            # Also check member states even if team is not paused
            team_is_paused = response.is_paused
            member_is_paused = False
            
            # Extract search queries from user input tools
            queries = []
            
            # First check direct team tools
            if hasattr(response, 'tools_requiring_user_input') and response.tools_requiring_user_input:
                print(f"DEBUG: Found team level tools_requiring_user_input")
                for tool in response.tools_requiring_user_input:
                    if tool.tool_name == 'get_user_input':
                        for field in tool.user_input_schema:
                            if field.name.startswith('query_'):
                                proposed_query = field.description or f"Sorgu {field.name.split('_')[1]}"
                                queries.append({
                                    'query': proposed_query,
                                    'field_name': field.name
                                })
            
            # Check team members' states regardless of team paused state
            if hasattr(editor_team, 'members'):
                print(f"DEBUG: Checking {len(editor_team.members)} members")
                for member in editor_team.members:
                    print(f"DEBUG: Member {member.name} - has run_response: {hasattr(member, 'run_response')}")
                    if hasattr(member, 'run_response') and member.run_response:
                        member_response = member.run_response
                        print(f"DEBUG: Member {member.name} - is_paused: {hasattr(member_response, 'is_paused') and member_response.is_paused}")
                        print(f"DEBUG: Member {member.name} - has tools: {hasattr(member_response, 'tools_requiring_user_input') and bool(member_response.tools_requiring_user_input)}")
                        
                        if (hasattr(member_response, 'is_paused') and member_response.is_paused and 
                            hasattr(member_response, 'tools_requiring_user_input') and member_response.tools_requiring_user_input):
                            member_is_paused = True
                            print(f"DEBUG: Found paused member {member.name} with tools")
                            for tool in member_response.tools_requiring_user_input:
                                if tool.tool_name == 'get_user_input':
                                    for field in tool.user_input_schema:
                                        if field.name.startswith('query_'):
                                            proposed_query = field.description or f"Sorgu {field.name.split('_')[1]}"
                                            queries.append({
                                                'query': proposed_query,
                                                'field_name': field.name,
                                                'member_name': member.name
                                            })
            
            print(f"DEBUG: Total queries found: {len(queries)}")
            print(f"DEBUG: Queries: {queries}")
            
            # If team is paused OR any member is paused with user input tools
            if team_is_paused or (member_is_paused and queries):
                update_stage(ProposalStage.AWAITING_CONFIRM)
                
                # Store the run for later resume
                run_id = response.run_id
                pending_runs[run_id] = {
                    'team': editor_team,
                    'user_id': user_id,
                    'session_id': session_id,
                    'mcp_tools': mcp_tools
                }
                
                print(f"DEBUG: Returning paused response with {len(queries)} queries")
                return {
                    'response': 'Arama sorguları onayınızı bekliyor.',
                    'stage': current_stage.stage.value,
                    'progress': current_stage.progress,
                    'message': current_stage.message,
                    'is_paused': True,
                    'run_id': run_id,
                    'queries': queries
                }
            
            print(f"DEBUG: No paused state detected, completing normally")
            update_stage(ProposalStage.COMPLETE)
            
            return {
                'response': response.content,
                'stage': current_stage.stage.value,
                'progress': current_stage.progress,
                'message': current_stage.message,
                'is_paused': False
            }

        finally:
            # Only close MCP if not paused (if paused, we need it for resume)
            if not response.is_paused:
                await mcp_tools.__aexit__(None, None, None)

    except Exception as e:
        print(f"Team execution error: {e}")
        update_stage(ProposalStage.ERROR, str(e))
        return {
            'response': f"Ajan ekibi çalışırken bir hata oluştu: {e}",
            'stage': current_stage.stage.value,
            'progress': current_stage.progress,
            'message': current_stage.message,
            'is_paused': False
        }

# --- API Uç Noktası ---
@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_message = data.get('message')
        if not user_message:
            return jsonify({'error': 'Mesaj boş olamaz'}), 400

        user_id = data.get('user_id', 'business-proposer-demo')
        session_id = data.get('session_id', str(uuid.uuid4()))

        response = asyncio.run(run_business_proposal_team(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message
        ))

        return jsonify(response)
    except Exception as e:
        print(f"API Error: {e}")
        return jsonify({
            'error': str(e),
            'stage': 'error',
            'progress': 0,
            'message': f"Sistem hatası: {e}"
        }), 500

@app.route('/resume', methods=['POST'])
def resume():
    """Resume a paused agent run with user-approved queries"""
    try:
        data = request.json
        run_id = data.get('run_id')
        approved_queries = data.get('approved_queries', [])
        
        if not run_id:
            return jsonify({'error': 'run_id gerekli'}), 400
            
        if run_id not in pending_runs:
            return jsonify({'error': 'Geçersiz veya süresi dolmuş run_id'}), 404
            
        run_info = pending_runs[run_id]
        team = run_info['team']
        mcp_tools = run_info['mcp_tools']
        
        team_run_response = team.run_response
        
        if not team_run_response or not (team_run_response.is_paused or any(m.run_response and m.run_response.is_paused for m in team.members)):
             return jsonify({'error': 'Bu çalışma duraklama durumunda değil'}), 400

        try:
            response = None
            
            # 1. Duraklamış olan ajanı ve onun response'unu bul.
            paused_member = None
            member_run_response = None
            for member in team.members:
                if (hasattr(member, 'run_response') and member.run_response and
                    hasattr(member.run_response, 'is_paused') and member.run_response.is_paused):
                    paused_member = member
                    member_run_response = member.run_response
                    print(f"DEBUG RESUME: Found paused member: {paused_member.name}")
                    break
            
            if not paused_member or not member_run_response:
                return jsonify({'error': 'Kullanıcı girdisi bekleyen bir ajan bulunamadı.'}), 400

            # 2. Ajanın `run_response` nesnesini kullanıcı girdileriyle güncelle.
            approved_query_map = {q['field_name']: q for q in approved_queries}
            if hasattr(member_run_response, 'tools_requiring_user_input') and member_run_response.tools_requiring_user_input:
                for tool in member_run_response.tools_requiring_user_input:
                    if tool.tool_name == 'get_user_input':
                        for field in tool.user_input_schema:
                            if field.name in approved_query_map:
                                field.value = approved_query_map[field.name].get('query', '')
                                print(f"DEBUG RESUME: Set field '{field.name}' for member '{paused_member.name}'")

            # 3. SADECE duraklamış olan ajanı devam ettir ve sonucunu al.
            update_stage(ProposalStage.ANALYSIS, "Bilgiler analiz ediliyor...")
            print(f"DEBUG RESUME: Continuing ONLY the paused member '{paused_member.name}'.")
            agent_result_response = asyncio.run(paused_member.acontinue_run(run_response=member_run_response))
            agent_output_content = agent_result_response.content
            print(f"DEBUG RESUME: Member '{paused_member.name}' has finished. Now informing the team leader.")

            # 4. Takımın mesaj geçmişini, ajanın sonucuyla GÜNCELLE.
            #    Bu, OpenAI API hatasını önlemek için en kritik adımdır.
            #    Takımın yaptığı 'transfer_task_to_member' çağrısının cevabını ekliyoruz.
            if team.run_messages and team.run_response and team.run_response.tools:
                # Takımın yaptığı son tool_call'u bul
                last_tool_call = team.run_response.tools[-1]
                if last_tool_call.tool_name == 'transfer_task_to_member':
                    tool_call_id = last_tool_call.tool_call_id
                    
                    # 'tool' rolüyle yeni bir mesaj oluştur
                    tool_response_message = {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": agent_output_content
                    }
                    
                    # Bu mesajı takımın geçmişine ekle
                    team.run_messages.messages.append(Message(**tool_response_message))
                    print(f"DEBUG RESUME: Added tool response for call_id '{tool_call_id}' to team's message history.")
                else:
                    print("WARNING: Last tool call was not 'transfer_task_to_member'. State might be inconsistent.")
            
            # 5. Takımı, güncellenmiş durumuyla devam etmesi için tetikle.
            #    'arun' metoduna boş bir mesaj yolluyoruz, çünkü yeni bir kullanıcı girdisi yok,
            #    sadece mevcut iş akışına devam etmesini istiyoruz.
            print("DEBUG RESUME: Triggering team to continue orchestration with updated history...")
            response = asyncio.run(team.arun(message="")) 

            del pending_runs[run_id]
            
            if response.is_paused:
                # ... (Bu kısım aynı kalabilir)
                return jsonify({'response': '...', 'is_paused': True})
            else:
                update_stage(ProposalStage.COMPLETE)
                return jsonify({
                    'response': response.content,
                    'stage': current_stage.stage.value,
                    'progress': current_stage.progress,
                    'message': current_stage.message,
                    'is_paused': False
                })
                
        finally:
            if response and hasattr(response, 'is_paused') and not response.is_paused:
                try:
                    if 'mcp_tools' in run_info and run_info['mcp_tools']:
                        asyncio.run(run_info['mcp_tools'].__aexit__(None, None, None))
                except Exception as cleanup_error:
                    print(f"MCP cleanup error: {cleanup_error}")
                    
    except Exception as e:
        import traceback
        print(f"Resume Error: {e}")
        traceback.print_exc()
        if 'run_id' in locals() and run_id in pending_runs:
            del pending_runs[run_id]
        
        return jsonify({
            'error': str(e),
            'stage': 'error',
            'progress': 0,
            'message': f"Devam etme hatası: {e}"
        }), 500

# --- Sunucuyu Başlat ---
if __name__ == '__main__':
    app.run(debug=True, port=5001)