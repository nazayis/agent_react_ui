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
    from agno.team import Team
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
# NEW TWO-PHASE SYSTEM: PLAN FIRST, THEN EXECUTE
# ==============================================================================

# Phase 1: Planning Agent - Creates detailed action plan
@app.route('/generate-plan', methods=['POST'])
def generate_plan_endpoint():
    data = request.json
    user_message = data.get('message')
    if not user_message:
        return jsonify({'error': 'Message cannot be empty'}), 400

    session_id = str(uuid.uuid4())

    async def _run():
        planning_agent = Agent(
            model=OpenAIChat(id="gpt-5-nano"),
            tools=[],  # Planning agent doesn't need external tools
            instructions=[
                "Sen iş araştırması ve teklif oluşturma için Stratejik Planlama Ajanısın.",
                "Görevin kullanıcının isteğine dayalı olarak detaylı, yapılandırılmış bir eylem planı oluşturmaktır.",
                "Planı şu yapıda oluştur:",
                "1. ARAŞTIRMA_AŞAMASI: Pazar araştırması için 5-7 spesifik Google arama sorgusu oluştur",
                "2. ANALİZ_AŞAMASI: Toplanan verilerden hangi yönlerin analiz edileceğini tanımla",
                "Yanıtını şu anahtarları içeren JSON yapısı olarak formatla:",
                "- research_queries: arama sorgusu dizileri",
                "- analysis_focus: analiz noktaları dizisi",
                "Planı kapsamlı ama uygulanabilir yap. İş zekası toplamaya odaklan.",
                "SADECE JSON yapısı ile yanıtla, ek metin ekleme."
            ],
            session_id=session_id,
            debug_mode=True
        )

        response = await planning_agent.arun(user_message)
        
        try:
            # Try to parse the response as JSON
            import json
            plan_data = json.loads(response.content)
            
            return jsonify({
                'success': True,
                'plan': plan_data,
                'session_id': session_id,
                'message': 'Action plan generated successfully. Please review and modify as needed.'
            })
        except json.JSONDecodeError:
            # If not valid JSON, return as structured text
            return jsonify({
                'success': True,
                'plan': {
                    'raw_plan': response.content,
                    'research_queries': [],
                    'analysis_focus': []
                },
                'session_id': session_id,
                'message': 'Plan generated. Please structure the plan data manually.'
            })

    return asyncio.run(_run())

# Phase 2: Execution Agent - Executes the approved plan without human intervention
@app.route('/execute-plan', methods=['POST'])
def execute_plan_endpoint():
    data = request.json
    plan = data.get('plan')
    if not plan:
        return jsonify({'error': 'Plan cannot be empty'}), 400
        
    # Sanitize queries and analysis focus: trim, remove empty, de-duplicate, cap to 5
    raw_queries = plan.get('research_queries', []) if isinstance(plan, dict) else []
    queries = []
    seen = set()
    if isinstance(raw_queries, list):
        for q in raw_queries:
            if isinstance(q, str):
                t = q.strip()
                if t and t not in seen:
                    seen.add(t)
                    queries.append(t)
    queries = queries[:5]

    raw_focus = plan.get('analysis_focus', []) if isinstance(plan, dict) else []
    focuses = []
    if isinstance(raw_focus, list):
        for f in raw_focus:
            if isinstance(f, str):
                t = f.strip()
                if t:
                    focuses.append(t)

    sanitized_plan = {
        'research_queries': queries,
        'analysis_focus': focuses
    }
    
    session_id = str(uuid.uuid4())
    user_id = f"user_{session_id}"

    async def _run():
        async with MCPTools(f"npx -y @modelcontextprotocol/server-filesystem {OUTPUT_DIR.resolve()}", timeout_seconds=30) as fs_tools:
            # 1. Araştırma ve Toplama Ajanı
            searcher = Agent(
                name="Araştırmacı",
                model=OpenAIChat(id="gpt-5-nano"),
                tools=[GoogleSearchTools()],
                instructions=[
                    "Sen bir Araştırmacısın. Verilen arama sorgularını çalıştırıp URL'leri toplarsın.",
                    "Frontend'de onaylanan arama sorgularını esas alarak en etkin arama sorgularını oluştur",
                    "Toplam arama sorgusu 5'i GEÇMEMELİ. 5'ten fazlaysa en alakalı 5'ini seç ve yalnızca onlar için sonuç topla.",
                    "Her sorgu için en alakalı 3 URL bul ve listele.",
                    "YASAK: Öneri yapma, izin isteme, yorum ekleme.",
                ],
                markdown=True,
                debug_mode=True
            )
            
            # 2. İçerik Okuma Ajanı  
            reader = Agent(
                name="İçerik Okuyucu",
                model=OpenAIChat(id="gpt-4o-mini"),
                tools=[read_articles],
                instructions=[
                    "Sen bir İçerik Okuyucusun. Verilen URL'lerdeki içerikleri okur ve özetlersin.",
                    "Her URL'yi ayrı ayrı oku ve içeriği özetle.",
                    "YASAK: Yorum yapma, öneri sunma, izin isteme.",
                ],
                markdown=True,
                debug_mode=True
            )
            
            # 3. Analiz Ajanı
            analyzer = Agent(
                name="Analist",
                model=OpenAIChat(id="gpt-5-nano"),
                tools=[],
                instructions=[
                    "Sen bir İş Analistisisin. Verilen içerikleri analiz eder ve bulgularını raporlarsın.",
                    "Pazar trendleri, fırsatlar ve rakip analizi yap.",
                    "YASAK: Ek öneri sunma, izin isteme, yorum ekleme.",
                ],
                markdown=True,
                debug_mode=True
            )
            
            # 4. İş Planı ve Strateji Uzmanı
            proposer = Agent(
                name="İş Planı Uzmanı",
                model=OpenAIChat(id="gpt-5-nano"),
                tools=[fs_tools],
                instructions=[
                    "Sen bir İş Stratejistisisin. Analiz sonuçlarından 3 ayrı dosya hazırlarsın.",
                    "",
                    "GÖREV: Şu 3 dosyayı sırasıyla oluştur:",
                    "",
                    "1. DOSYA: 'output/pain_points.md'",
                    "İÇERİK:",
                    "- Proje fikrinin acı noktaları",
                    "- Competitor'ların yaptıkları analizi",
                    "- Bu sorunların üstesinden gelme yöntemleri",
                    "- Araştırma aşamasında öğrenilen kritik bilgiler",
                    "- Pazar eksiklikleri ve fırsatlar",
                    "",
                    "2. DOSYA: 'output/roadmap.md'", 
                    "İÇERİK (.md formatında kaydet, bu dosya içerisinde tablo oluştur):",
                    "- Hafta bazında görev planı",
                    "- Development aşamaları (Planning, Design, Development, Testing, Launch)",
                    "- Her görevin hangi aşamaya ait olduğu",
                    "- Sorumlu kişi/ekip bilgisi",
                    "- Başlangıç ve bitiş tarihleri",
                    "- Öncelik seviyeleri",
                    "",
                    "3. DOSYA: 'output/business_strategy.md'",
                    "İÇERİK (9 ana bölüm):",
                    "- YÖNETİCİ ÖZETİ",
                    "- ANALİZ BULGULARI", 
                    "- KARAR VERİ SÜRECİ",
                    "- STRATEJİK KARARLAR",
                    "- HEDEFLENEN SONUÇLAR",
                    "- UYGULAMA PLANI",
                    "- ZAMAN ÇİZELGESİ",
                    "- RİSK ANALİZİ",
                    "",
                    "KURALLAR:",
                    "- Üç dosyayı da (Türkçe) sırasıyla oluştur ve kaydet",
                    "- Her dosya detaylı ve kapsamlı olmalı",
                    "- Roadmap dosyasının içeriğini tablo formatında oluştur, .md olarak kaydet",
                    "- İzin isteme, onay bekleme",
                    "",
                    "YASAK: İzin isteme, öneri yapma, seçenek sunma.",
                ],
                markdown=True,
                debug_mode=True
            )
            
            # Takım Koordinatörü
            team_instructions = [
                "Sen bir Proje Koordinatörüsün. Takımı yönetir ve görevleri sırayla dağıtırsın.",
                "",
                "GÖREV: Şu adımları takip et:",
                "1. Araştırmacı'ya arama sorgularını ver",
                "2. İçerik Okuyucu'ya URL'leri ver", 
                "3. Analist'e içerikleri analiz ettir",
                "4. İş Planı Uzmanı'na 3 dosyayı hazırlat",
                "5. Oluşturulan 3 dosyayı oku ve özetle",
                "",
                "ÇIKTI: 3 dosyanın içeriğini şu format ile paylaş:",
                "=== PAIN POINTS ===",
                "[pain_points.md içeriği]",
                "",
                "=== ROADMAP ===", 
                "[roadmap.md içeriği]",
                "",
                "=== BUSINESS STRATEGY ===",
                "[business_strategy.md içeriği]",
                "",
                "Her dosyayı read_file ile oku ve aynen döndür.",
                "",
                "YASAK: Kendi metin üretme, süreç anlatma, öneri yapma.",
            ]

            analysis_team = Team(
                name="İş Strateji Takımı",
                mode="coordinate",
                model=OpenAIChat(id="gpt-5-nano"),
                members=[searcher, reader, analyzer, proposer],
                tools=[fs_tools],
                user_id=user_id,
                session_id=session_id,
                description=(
                    "Sen bir Proje Koordinatörüsün. Takımı yönetir ve verilen planı uygularsın."
                ),
                instructions=team_instructions,
                add_datetime_to_instructions=True,
                enable_agentic_context=True,
                share_member_interactions=True,
                markdown=True,
                debug_mode=True
            )

            # Convert plan to a readable format for the team
            plan_text = f"""
UYGULAMA PLANI:

ARAŞTIRMA SORGULARİ:
{chr(10).join(f"- {query}" for query in sanitized_plan.get('research_queries', []))}

ANALİZ ODAKLARI:
{chr(10).join(f"- {focus}" for focus in sanitized_plan.get('analysis_focus', []))}

ÇIKTI FORMATI: 3 dosya (pain_points.md, roadmap.md, business_strategy.md)
"""

            response = await analysis_team.arun(f"Bu araştırma ve analiz planını takımımla birlikte tamamen uygula:\n{plan_text}")
            
            return jsonify({
                'success': True,
                'result': response.content,
                'session_id': session_id,
                'message': 'Plan takım tarafından başarıyla uygulandı. İş stratejisi tamamlandı ve kaydedildi.'
            })

    return asyncio.run(_run())

# Legacy endpoint for backward compatibility (can be removed later)
@app.route('/generate-queries', methods=['POST'])
def generate_queries_endpoint():
    return jsonify({'error': 'This endpoint is deprecated. Use /generate-plan instead.'}), 410

@app.route('/execute-search', methods=['POST']) 
def execute_search_endpoint():
    return jsonify({'error': 'This endpoint is deprecated. Use /execute-plan instead.'}), 410

@app.route('/analyze-and-propose', methods=['POST'])
def analyze_and_propose_endpoint():
    return jsonify({'error': 'This endpoint is deprecated. Use /execute-plan instead.'}), 410


if __name__ == '__main__':
    app.run(debug=True, port=5001)