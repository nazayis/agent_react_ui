# agent.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import asyncio
import uuid
from pathlib import Path
from textwrap import dedent
import datetime

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
    from agno.knowledge.markdown import MarkdownKnowledgeBase
    from agno.vectordb.lancedb import LanceDb
except ImportError as e:
    print(f"Hata: Gerekli kütüphanelerden biri eksik: {e}")
    exit(1)

# --- Flask, CORS, Project Configuration ---
app = Flask(__name__)
CORS(app)
load_dotenv()
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
KB_DIR = Path(__file__).parent / "kb"
KB_DIR.mkdir(exist_ok=True)
LANCEDB_URI = OUTPUT_DIR / "vector_db"
knowledge_vector_db = LanceDb(table_name="markdown_kb", uri=LANCEDB_URI)
knowledge_base = MarkdownKnowledgeBase(path=KB_DIR, vector_db=knowledge_vector_db)
# İlk indeksleme için bir kez True, sonra False kullanın
try:
	knowledge_base.load(recreate=False)
except Exception as e:
	print(f"Knowledge base load error: {e}")

pending_runs = {}

# --- Custom Tool: read_articles ---
@tool
def read_articles(urls: list[str]) -> str:
    """Fetch and combine readable text content from multiple URLs into a single string."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def fetch(url: str, timeout: int = 6, max_chars: int = 3000) -> str:
        try:
            response = requests.get(url, timeout=timeout, headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            
            if response.encoding is None:
                response.encoding = getattr(response, "apparent_encoding", None) or 'utf-8'
            
            try:
                soup = BeautifulSoup(response.text, 'html.parser')
            except UnicodeDecodeError:
                enc = getattr(response, "apparent_encoding", None) or 'utf-8'
                soup = BeautifulSoup(response.content.decode(enc, errors='replace'), 'html.parser')

            for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                element.decompose()
            
            text = soup.get_text(separator=' ', strip=True)
            text = re.sub(r'\s+', ' ', text)
            text = ''.join(char for char in text if char.isprintable() or char in '\n\t')
            
            return f"\n\n--- CONTENT FROM {url} ---\n\n{text[:max_chars]}"
        except Exception as e:
            return f"\n\n--- ERROR READING {url}: {str(e)} ---\n\n"

    combined_text = ""
    max_workers = min(8, max(1, len(urls)))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(fetch, u): u for u in urls}
        for fut in as_completed(futures):
            combined_text += fut.result()
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
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        planning_agent = Agent(
            model=OpenAIChat(id="gpt-4o-mini"),
            tools=[],  # Planning agent doesn't need external tools
            instructions=[
                f"Sen iş araştırması ve teklif oluşturma için Stratejik Planlama Ajanısın. Bugünün tarihi: {today}",
                "Görevin kullanıcının isteğine dayalı olarak detaylı, yapılandırılmış bir eylem planı oluşturmaktır.",
                "Planı şu yapıda oluştur:",
                "1. ARAŞTIRMA_AŞAMASI: Pazar araştırması için 3-4 spesifik Google arama sorgusu oluştur",
                "2. ANALİZ_AŞAMASI: Toplanan verilerden hangi yönlerin analiz edileceğini tanımla. Toplam 3 analiz noktası olmalı. Her analiz noktası 5-6 kelimelik ve temel olmalı.",
                "Yanıtını şu anahtarları içeren JSON yapısı olarak formatla:",
                "- research_queries: arama sorgusu dizileri",
                "- analysis_focus: analiz noktaları dizisi",
                "Planı kapsamlı ama uygulanabilir yap. İş zekası toplamaya odaklan.",
                "SADECE JSON yapısı ile yanıtla, ek metin ekleme."
            ],
            session_id=session_id,
            knowledge=knowledge_base,
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
    queries = queries[:3]

    raw_focus = plan.get('analysis_focus', []) if isinstance(plan, dict) else []
    focuses = []
    if isinstance(raw_focus, list):
        for f in raw_focus:
            if isinstance(f, str):
                t = f.strip()
                if t:
                    focuses.append(t)

    # Sanitize output files: prefer output_format (string with newlines) from frontend
    default_files = ['pain_points.md', 'roadmap.md', 'business_strategy.md']
    raw_output_format = plan.get('output_format') if isinstance(plan, dict) else None
    files = []
    if isinstance(raw_output_format, str):
        files = [s.strip() for s in raw_output_format.split('\n') if s and s.strip()]
    # Ensure exactly three filenames
    if not files:
        files = default_files
    else:
        files = (files + default_files)[:3]

    sanitized_plan = {
        'research_queries': queries,
        'analysis_focus': focuses,
        'output_files': files
    }
    
    session_id = str(uuid.uuid4())
    user_id = f"user_{session_id}"

    async def _run():
        async with MCPTools(f"npx -y @modelcontextprotocol/server-filesystem {OUTPUT_DIR.resolve()}", timeout_seconds=10) as fs_tools:
            # 1. Araştırma ve Toplama Ajanı
            searcher = Agent(
                name="Araştırmacı",
                model=OpenAIChat(id="gpt-4o-mini"),
                tools=[GoogleSearchTools()],
                knowledge=knowledge_base,
                instructions=[
                    "Sen bir Araştırmacısın. Verilen arama sorgularını çalıştırıp URL'leri toplarsın.",
                    "FRAGMAN: Her sorgu için ÖNCE bilgi tabanında (KB) arama yap; ilgili bulguları kısa maddelerle özetle ve kaynak dosya adlarını belirt. Ardından Google araması yap.",
                    "Frontend'de onaylanan arama sorgularını esas alarak en etkin arama sorgularını oluştur",
                    "Toplam arama sorgusu 3'ü GEÇMEMELİ. Fazlaysa en alakalı 3'ünü seç ve yalnızca onlar için sonuç topla.",
                    "Her sorgu için en alakalı 2 URL bul ve listele.",
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
                    "Her URL'yi ayrı ayrı oku ve en fazla 5 maddede, toplam 400-600 karakterlik sıkıştırılmış özet çıkar.",
                    "YASAK: Öneri sunma, izin isteme.",
                ],
                markdown=True,
                debug_mode=True
            )
            
            # 3. Analiz Ajanı
            analyzer = Agent(
                name="Analist",
                model=OpenAIChat(id="gpt-4o-mini"),
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
            file1, file2, file3 = sanitized_plan['output_files']
            proposer_instructions = [
                "Rol: İş Stratejisti. Türkçe yaz. 3 dosya üret ve kaydet: 'output/{file1}', 'output/{file2}', 'output/{file3}'.",
                "Genel: Paragraf ağırlıklı, kısa cümleler; jargon ilk geçtiğinde açıkla; onay/öneri isteme; süreç anlatma.",
                f"1) 'output/{file1}' (pain_points.md): Giriş paragrafı; 3-5 acı noktası (problem, iş etkisi, kanıt); fırsat çerçevesi; küçük KPI tablosu (KPI | mevcut | hedef).",
                f"2) 'output/{file2}' (roadmap.md): KULLANICININ DANIŞTIĞI ÜRÜNÜN ROADMAP'i. Markdown TABLO ZORUNLU. Başlıklar AYNEN: Sprint/Release | Epic/Feature | User Story/Kapsam | Aşama (Discovery, Design, Build, Test, Launch) | Sorumlu (kişi/ekip) | Başlangıç (YYYY-MM-DD) | Bitiş (YYYY-MM-DD) | Öncelik (Yüksek/Orta/Düşük) | Bağımlılıklar | KPI/Metrik (ör. aktivasyon oranı, NPS, hata oranı). En az 5-8 satır. Aşağıdaki TERİMLER GEÇMEYECEK: Araştırmacı, İçerik Okuyucu, Analist, İş Planı Uzmanı, Koordinatör, ajan, adım, süreç, araştırma, okuma, analiz, ekip, team, koordine, koordinatör. Sadece ürün/feature planı.",
                f"3) 'output/{file3}' (business_strategy.md): Önerilen bölümler: Yönetsel Özet; Analiz Bulguları; Değer Önerisi ve Ürün Stratejisi; Go-to-Market ve Büyüme; Zaman Çizelgesi Özeti; Riskler ve Önlemler; KPI ve Hedefler; Sonraki Adım.",
                "Kayıt: write_file aracıyla kaydet."
            ]
            proposer = Agent(
                name="İş Planı Uzmanı",
                model=OpenAIChat(id="gpt-4o-mini"),
                tools=[fs_tools],
                instructions=proposer_instructions,
                markdown=True,
                debug_mode=True
            )
            
            # Takım Koordinatörü
            team_instructions = [
                "Sen bir Proje Koordinatörüsün. Takımı yönetir ve görevleri sırayla dağıtırsın.",
                "",
                "Eğer kullanıcı yeni bir projeye başlamak istiyorsa şu adımları takip et:",
                "0. Her arama sorgusu için ÖNCE bilgi tabanında (KB) ilgili içerik var mı diye ara ve bulguları not et; ardından web araması yap.",
                "1. Araştırmacı'ya arama sorgularını ver. Her arama sorgusu için en alakalı 3 URL bulmalı.",
                "2. İçerik Okuyucu'ya URL'leri ver", 
                "3. Analist'e içerikleri analiz ettir",
                "4. İş Planı Uzmanı'na 3 dosyayı hazırlat",
                "5. Oluşturulan 3 dosyayı oku ve özetle",
                "",
                "ÇIKTI: 3 dosyanın içeriğini şu dosyalardan oku ve aynen paylaş:",
                f"- output/{file1}",
                f"- output/{file2}",
                f"- output/{file3}",
                "",
                "Her dosyayı read_file ile oku ve aynen döndür.",
                "",
                "Kullanıcının yeni proje geliştirme talepleri dışındaki sorulara, takım dinamiklerini aklında bulundurarak kendin karar ver.",
                "",
                "YASAK: Kendi metin üretme, süreç anlatma, izin isteme, öneri yapma. Sadece son çıktıyı paylaş.",
            ]

            analysis_team = Team(
                name="İş Strateji Takımı",
                mode="coordinate",
                model=OpenAIChat(id="gpt-4o-mini"),
                members=[searcher, reader, analyzer, proposer],
                tools=[fs_tools],
                user_id=user_id,
                session_id=session_id,
                description=(
                    "Sen bir Proje Koordinatörüsün. Takımı yönetir ve verilen planı uygularsın."
                ),
                instructions=team_instructions,
                add_datetime_to_instructions=False,
                enable_agentic_context=False,
                share_member_interactions=False,
                markdown=True,
                debug_mode=True,
                knowledge=knowledge_base,
                search_knowledge=True,
            )

            # Convert plan to a readable format for the team
            plan_text = f"""
UYGULAMA PLANI:

ARAŞTIRMA SORGULARİ:
{chr(10).join(f"- {query}" for query in sanitized_plan.get('research_queries', []))}

ANALİZ ODAKLARI:
{chr(10).join(f"- {focus}" for focus in sanitized_plan.get('analysis_focus', []))}

ÇIKTI FORMATI: 3 dosya ({', '.join(sanitized_plan.get('output_files', []))})
"""

            response = await analysis_team.arun(f"Bu araştırma ve analiz planını takımımla birlikte tamamen uygula:\n{plan_text}")
            
            # Read generated output files and include them as structured documents
            documents = []
            try:
                output_files = sanitized_plan.get('output_files', [])
                for fname in output_files:
                    file_path = OUTPUT_DIR / fname
                    try:
                        content = file_path.read_text(encoding='utf-8')
                    except FileNotFoundError:
                        content = f"Dosya bulunamadı: {file_path}"
                    except Exception as e:
                        content = f"Dosya okunurken hata oluştu ({file_path}): {str(e)}"
                    documents.append({
                        'filename': str(fname),
                        'content': content
                    })
            except Exception as e:
                documents = [{
                    'filename': 'error',
                    'content': f'Dokümanları okurken beklenmeyen bir hata oluştu: {str(e)}'
                }]
            
            # Roadmap doğrulama ve gerekirse yeniden yazdırma
            try:
                roadmap_name = sanitized_plan.get('output_files', [None, None, None])[1]
                if roadmap_name:
                    roadmap_path = OUTPUT_DIR / roadmap_name
                    roadmap_content = ""
                    try:
                        roadmap_content = roadmap_path.read_text(encoding='utf-8')
                    except Exception:
                        roadmap_content = ""

                    banned_terms = [
                        "Araştırmacı", "İçerik Okuyucu", "Analist", "İş Planı Uzmanı", "Koordinatör",
                        "ajan", "adım", "süreç", "araştırma", "okuma", "analiz", "ekip", "team", "koordine", "koordinatör"
                    ]
                    required_headers = [
                        "Sprint/Release", "Epic/Feature", "User Story/Kapsam", "Aşama", "Sorumlu",
                        "Başlangıç", "Bitiş", "Öncelik", "Bağımlılıklar", "KPI/Metrik"
                    ]

                    def is_invalid_roadmap(text: str) -> bool:
                        lower = text.lower()
                        has_banned = any(term.lower() in lower for term in banned_terms)
                        has_table = "|" in text and "---" in text
                        has_all_headers = all(h in text for h in required_headers)
                        return (not has_table) or (not has_all_headers) or has_banned

                    if is_invalid_roadmap(roadmap_content):
                        fix_prompt = dedent(f"""
                        'output/{roadmap_name}' dosyası ürün ROADMAP'ı formatında DEĞİL. Şimdi yalnızca bu dosyayı yeniden yaz.
                        ZORUNLU:
                        - .md TABLO kullan
                        - Sütun başlıkları AYNEN: Sprint/Release | Epic/Feature | User Story/Kapsam | Aşama (Discovery, Design, Build, Test, Launch) | Sorumlu (kişi/ekip) | Başlangıç (YYYY-MM-DD) | Bitiş (YYYY-MM-DD) | Öncelik (Yüksek/Orta/Düşük) | Bağımlılıklar | KPI/Metrik (ör. aktivasyon oranı, NPS, hata oranı)
                        - En az 5-8 satır
                        - Aşağıdaki terimleri ve ajan süreçlerini KULLANMA: {', '.join(banned_terms)}
                        - Yalnızca ürün, özellikler, kullanıcı hikayeleri ve teslimat planına odaklan
                        EYLEM:
                        - Doğru içerikle 'output/{roadmap_name}' dosyasını yaz (write_file aracıyla) ve kaydet
                        - Başka metin döndürme
                        """)
                        try:
                            await proposer.arun(fix_prompt)
                            # Dosyayı tekrar oku ve documents içine güncellenmiş halini yansıt
                            try:
                                corrected = roadmap_path.read_text(encoding='utf-8')
                                for d in documents:
                                    if d.get('filename') == str(roadmap_name):
                                        d['content'] = corrected
                                        break
                            except Exception:
                                pass
                        except Exception:
                            pass
            except Exception:
                pass
            
            return jsonify({
                'success': True,
                'result': response.content,
                'documents': documents,
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


    """
    ihtiyaç analizi olduğunu takım lideriyle paylaş
        çıktı dosyasında iihtiyaç analiz dokümanı olması buna göre cevap vermesi
    son doküman pdf md txt formatta download edilebilir olması lazım
    sol taraftaki next step akış built in çalışmayan bir şey olur
    arayüzün dizaynı toparlanması ()
    """