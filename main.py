import os
import json
import datetime
import time
import requests
import feedparser
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google import genai  # <-- 새로운 공식 SDK로 변경됨
import re
import html
from bs4 import BeautifulSoup

# --- 환경 변수 로드 ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

# --- Gemini 설정 (새로운 SDK 적용) ---
# 기존 request_options에 있던 timeout 설정을 클라이언트 레벨에서 전역 처리합니다.
client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={'timeout': 600000} 
)
MODEL_ID = 'gemini-3-flash-preview'

# --- 0. 히스토리 관리 ---
def load_history(filepath):
    if not os.path.exists(filepath): return []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except: return []

def save_history(filepath, history, new_items):
    cutoff = datetime.datetime.now() - datetime.timedelta(days=30)
    cleaned = []
    
    for item in history:
        try:
            d = datetime.datetime.strptime(item.get('date', '2000-01-01'), "%Y-%m-%d")
            if d >= cutoff: cleaned.append(item)
        except: continue
        
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    for item in new_items:
        cleaned.append({"id": item['id'], "title": item['title'], "date": today})
        
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=4)

# --- 1. 데이터 수집 (웹 스크래핑 추가) ---
def scrape_article_text(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, headers=headers, timeout=5)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        paragraphs = soup.find_all('p')
        text = " ".join([p.get_text() for p in paragraphs])
        return text[:3000] if len(text) > 100 else None 
    except Exception as e:
        print(f"Scraping failed for {url}: {e}")
        return None

def fetch_rss(url, category):
    items = []
    try:
        feed = feedparser.parse(url)
        cutoff = datetime.datetime.now() - datetime.timedelta(days=3)
        for entry in feed.entries:
            if 'published_parsed' in entry and entry.published_parsed:
                pub_date = datetime.datetime.fromtimestamp(time.mktime(entry.published_parsed))
                if pub_date < cutoff: continue
            
            print(f"Scraping: {entry.title}")
            raw_text = scrape_article_text(entry.link)
            if not raw_text:
                raw_text = (entry.summary if 'summary' in entry else entry.title)[:2000]
            
            items.append({
                "id": entry.link,
                "title": entry.title,
                "type": category,
                "raw": raw_text
            })
    except Exception as e:
        print(f"RSS Error ({url}): {e}")
    return items

def get_candidates(mode):
    items = []
    if mode == "TECH":
        urls = ["https://www.theverge.com/rss/index.xml", "https://techcrunch.com/feed/"]
    elif mode == "BIO":
        urls = ["https://news.google.com/rss/search?q=Biotech+OR+%22FDA+approval%22+OR+%22Clinical+Trial%22&hl=en-US&gl=US&ceid=US:en"]
    elif mode == "PATENT":
        urls = ["https://news.google.com/rss/search?q=Patent+OR+%22Technology+Innovation%22+OR+%22Future+Tech%22&hl=en-US&gl=US&ceid=US:en"]
    
    for u in urls: items.extend(fetch_rss(u, mode))
    return items

# --- 2. 주제 선정 ---
def select_top_2(candidates, history, category_name):
    history_ids = [h['id'] for h in history]
    filtered = [c for c in candidates if c['id'] not in history_ids]
    
    if len(filtered) < 2: return filtered[:2]
    
    cand_txt = "\n".join([f"{i}. {c['title']}" for i, c in enumerate(filtered[:15])])
    
    prompt = f"""
    역할: 전문 투자/기술 블로그 편집장 '스포(spo)'.
    목표: {category_name} 분야에서 심층 분석(Deep-Dive)이 가능하고 투자자들의 관심이 집중될 뉴스 2개 선정.
    
    [후보군]
    {cand_txt}
    
    조건:
    1. 기술적 원리나 시장 파급력을 분석할 거리가 있는 주제 우선.
    2. 오직 숫자 2개만 반환 (예: 1, 4).
    """
    try:
        res = client.models.generate_content(model=MODEL_ID, contents=prompt)
        time.sleep(5) # API 호출 제한 방지
        nums = [int(s) for s in re.findall(r'\b\d+\b', res.text)]
        if len(nums) >= 2:
            return [filtered[nums[0]], filtered[nums[1]]]
    except: pass
    return filtered[:2]

# --- 3. 매력적인 한국어 제목 생성 함수 ---
def get_catchy_korean_title(english_title):
    prompt = f"""
    다음 영문 뉴스 제목을 번역하되, 사람들의 호기심을 끌면서도 '깔끔하고 핵심을 찌르는' 한 줄짜리 한국어 블로그 제목으로 만들어줘.
    
    [조건]
    1. 무조건 100% 한국어로만 작성할 것 (불가피한 고유명사 제외).
    2. 길이는 30자 이내로 간결하게 1줄로 작성할 것.
    3. 과도한 특수기호(!, ?, [])나 어그로성 단어([충격], [경악] 등)는 피하고, 전문가다운 세련되고 트렌디한 느낌을 줄 것.
    4. 다른 부가 설명 없이 오직 생성된 '제목 1개'만 출력할 것.
    
    영문 제목: {english_title}
    """
    try:
        title_res = client.models.generate_content(model=MODEL_ID, contents=prompt).text.strip()
        time.sleep(5) # API 호출 제한 방지
        return title_res
    except:
        return english_title

# --- 이메일 전송용 통합 제목 생성 함수 ---
def get_unified_subject(category_name, t1_kr, t2_kr):
    prompt = f"""
    다음 두 개의 뉴스 제목을 아우르는, 이메일 제목용 통합 블로그 제목을 작성해줘.

    [조건]
    1. 매우 간결하고 깔끔하게 1줄로 작성할 것 (최대 35자 이내).
    2. 두 주제의 핵심 내용이 자연스럽게 어우러지는 하나의 문장이나 구로 만들 것.
    3. '&' 같은 기호나 자극적인 수식어를 빼고 담백하면서도 인사이트가 느껴지도록 할 것.
    4. 다른 부가 설명 없이 오직 생성된 '제목 1개'만 출력할 것.

    주제1: {t1_kr}
    주제2: {t2_kr}
    """
    try:
        res = client.models.generate_content(model=MODEL_ID, contents=prompt).text.strip()
        time.sleep(5) # API 호출 제한 방지
        return f"[{category_name} 분석] {res}"
    except:
        return f"[{category_name} 분석] {t1_kr[:15]}... 외 핵심 이슈"

# --- 4. 글 작성 (내부 링크 기능 추가) ---
def write_blog_post(topic1, topic2, category_name, t1_kr, t2_kr, history):
    print(f"Writing {category_name} Post with Gemini...")
    
    tone_rule = """
    [구글 애드센스 승인 및 고품질 콘텐츠를 위한 필수 문체 및 어조 지침 (10년차 현업 전문가 페르소나)]
    1. 페르소나: 관련 업계에서 10년 이상 구르며(?) 산전수전 다 겪은 베테랑 실무 전문가. 지루한 교과서적 설명이 아닌, 현업의 '진짜 돌아가는 이야기'를 트렌디하고 감각적으로 풀어냅니다.
    2. 문체: 군더더기 없이 깔끔하고 가독성 높은 문장을 구사합니다. "~습니다", "~하죠" 등 신뢰감 있는 경어체를 사용하되, 지인에게 고급 실무 정보를 슬쩍 공유해주듯 자연스럽고 전문가 특유의 여유가 묻어나는 어투를 사용하세요.
    3. 주관적이고 예리한 분석: 단순 사실 전달을 넘어, "솔직히 이번 이슈로 볼 때 A사보다는 B사가 시장 선점에 훨씬 유리한 고지를 차지할 겁니다. 현업에서 그렇게 보는 이유는..."과 같이 10년차 특유의 뚜렷한 주관과 예리한 비교 분석을 반드시 포함하세요.
    4. AI 말투 200% 금지: '결론적으로', '알아보겠습니다', '이 기사를 통해', '안녕하세요', '요약하자면', '흥미진진한' 등 AI 특유의 상투적이고 영혼 없는 표현은 절대 금지합니다. 진짜 사람이 쓴 것처럼 문단 간 연결을 매끄럽게 하세요.
    """

    glossary_rule = "어려운 '전문 용어'는 반드시 <u> 태그로 감싸주세요."
    bold_rule = "가독성을 높이기 위해 문단에서 가장 중요한 '핵심 문장'과 '주요 키워드(단어)'는 반드시 <b> 태그를 사용하여 굵게 강조해주세요."

    # 이전 발행 글 목록 텍스트화 (최근 15개)
    history_text = "이전 발행 글 없음"
    if history:
        recent_history = history[-15:]
        history_lines = [f"- 원문 제목: {h.get('title', '')} (URL: {h.get('id', '')})" for h in recent_history]
        history_text = "\n".join(history_lines)

    # 대안 2: 이전 글 히스토리 기반 실제 내부 링크 삽입 (수익화/SEO 포인트 2)
    internal_link_rule = f"""
    [블로그 내부 링크 자동 삽입 지침 - SEO 최적화]
    아래 '이전 발행 글 목록'을 분석하여, 현재 작성 중인 글과 맥락이 가장 잘 맞는 이전 글 1개를 선정하세요.
    그리고 독자가 글을 읽다가 자연스럽게 누를 수 있는 위치에 아래 HTML 코드로 '관련 글 링크'를 삽입하세요.
    (만약 연관된 글이 없거나 목록이 비어있다면, 기존처럼 https://spo26.tistory.com/search/[핵심키워드] 방식을 사용하세요.)

    [이전 발행 글 목록]
    {history_text}
    
    <div style="margin: 25px 0; padding: 15px; background-color: #f8f9fa; border-left: 4px solid #3498db; border-radius: 4px;">
        <span style="font-weight: bold; color: #2c3e50;">🔗 스포(spo) 블로그 연관 글 보기:</span> 
        <a href="[선정된 URL]" target="_blank" style="color: #3498db; text-decoration: none; font-weight: bold;">[선정된 이전 글 제목 또는 클릭을 유도하는 관련 문구]</a>
    </div>
    """

    citation_rule = """
    [출처(Citations) 및 외부 링크 삽입 지침]
    본문에 'Nature Medicine', 특정 임상시험 이름(예: BROOKLYN 임상 3상), 주요 논문, 공신력 있는 기관(FDA, EMA 등)이나 뉴스 매체(Reuters 등)가 언급될 경우, 
    해당 텍스트에 실제 참고할 수 있는 공신력 있는 외부 링크(URL)를 1~2개 이상 HTML <a> 태그(target='_blank', style='color: #2980b9; text-decoration: underline;')를 사용하여 자연스럽게 걸어주세요.
    """

    stock_link_rule = """
    [상장사 실시간 주가 링크 삽입 지침]
    본문에 언급된 핵심 기업이 상장사(Public Company)인 경우, 독자들이 실시간 주가를 확인할 수 있도록 해당 기업이 처음 언급되는 부분(혹은 적절한 문맥)에 
    인베스팅닷컴(Investing.com) 검색 결과 링크를 <a> 태그로 추가해주세요. 상장사가 아니면 무조건 생략하세요.
    형식: 기업명 뒤에 괄호를 열고 삽입 (예: 테슬라 <a href='https://kr.investing.com/search/?q=Tesla' target='_blank' style='font-size: 0.85em; color: #e74c3c; text-decoration: none; font-weight: bold;'>[📈주가확인]</a>)
    """

    outline_prompt = f"주제1: {topic1['title']}\n주제2: {topic2['title']}\n위 두 주제로 '{category_name} 심층 분석' 개요 작성."
    outline = client.models.generate_content(model=MODEL_ID, contents=outline_prompt).text
    time.sleep(5) # API 호출 제한 방지
    
    # 주제 1 작성 프롬프트 (수익화/SEO 포인트 5: 애드센스 플레이스홀더 추가)
    p1_prompt = f"""
    역할: {category_name} 업계 10년차 현업 전문가이자, 트렌디하고 깔끔한 인사이트를 제공하는 실무 분석가 '스포(spo)'.
    개요: {outline}
    주제 1: {topic1['title']} / 원문 내용: {topic1['raw']}
    {tone_rule}
    {glossary_rule}\n{bold_rule}
    {internal_link_rule}
    {citation_rule}
    {stock_link_rule}
    
    [작성 지침] HTML 태그만 출력하세요. 아래 제공된 뼈대(Skeleton)를 반드시 그대로 복사해서 뼈대를 유지한 채 (지침) 부분을 실제 글로 채워주세요. 
    내부 링크, 외부 출처 링크, 주가 확인 링크는 뼈대를 해치지 않는 적절한 곳에 삽입하세요.
    주의: [IMAGE_PLACEHOLDER_X] 및 [애드센스 광고 위치] 태그를 절대 임의로 옮기거나 삭제하지 마세요.

    <h1>[{category_name} 심층분석] {t1_kr}</h1>
    
    [IMAGE_PLACEHOLDER_1]
    
    <h2>1. 배경 및 개요 (The Context)</h2>
    (지침: 현 상황을 뻔하지 않게 3줄 요약 리스트(<ul>)로 제시)
    
    <h2>2. 기존 기술/약물과의 차별점 (Comparative Analysis)</h2>
    (지침: 과거 유사했던 사례와 비교하여 이번 주제의 진짜 혁신 포인트가 무엇인지 에디터의 시각으로 분석)
    
    <div class="adsense-placeholder" style="text-align:center; margin: 30px 0; padding: 20px; background:#f8f9fa; color:#adb5bd; border:2px dashed #dee2e6; border-radius: 8px; font-weight: bold;">[💰 애드센스 본문 상단 광고 삽입 위치 1]</div>

    [IMAGE_PLACEHOLDER_2]
    
    <h2>3. 기술적 메커니즘 (Technical Deep-Dive)</h2>
    (지침: <table>을 1개 이상 반드시 포함. 전문적이지만 독자가 이해하기 쉽게 적절한 비유를 섞어 설명)
    
    <h2>4. 시장 판도 및 경쟁사 분석 (Market Dynamics)</h2>
    (지침: 객관적인 데이터와 함께, 구체적이고 주관적인 기업/기술 간 우위 분석을 반드시 작성)
    
    <h2>5. 리스크 및 한계점 (Risk Factors)</h2>
    (지침: 표면적인 리스크가 아닌, 실무자/투자자 관점에서의 진짜 걸림돌(규제, 경쟁 심화, 기술적 장벽 등)을 예리하게 지적)
    
    [IMAGE_PLACEHOLDER_3]
    
    <h2>6. 긍정적 전망 및 기대 효과 (Future Hope & Impact)</h2>
    (지침: 이 변화가 가져올 미래 산업의 모습을 생생하게 그려주듯 서술)
    
    <h2>7. 스포(spo)의 인사이트 (Actionable Insights)</h2>
    (지침: 단순 요약 금지. "그래서 지금 우리는 무엇을 주목해야 하는가?"에 대한 에디터 스포의 매우 주관적이고 사람 냄새 나는 솔직한 총평과 투자/산업적 조언)
    """
    part1_res = client.models.generate_content(model=MODEL_ID, contents=p1_prompt).text
    time.sleep(5) 
    part1 = re.sub(r"```[a-zA-Z]*\n?|```", "", part1_res).strip()
    
    # 주제 2 작성 프롬프트 (수익화/SEO 포인트 1, 3, 5: 메타, 스키마, 광고 추가)
    p2_prompt = f"""
    앞부분: {part1}
    주제 2: {topic2['title']} / 원문 내용: {topic2['raw']}
    {tone_rule}
    {glossary_rule}\n{bold_rule}
    {internal_link_rule}
    {citation_rule}
    {stock_link_rule}
    
    [작성 지침] 앞 내용과 자연스럽게 이어지도록 작성하세요. HTML 태그만 출력. 아래 제공된 뼈대(Skeleton)를 반드시 그대로 복사해서 유지한 채 (지침) 부분을 실제 글로 채워주세요. 
    주의: [IMAGE_PLACEHOLDER_X] 및 [애드센스 광고 위치] 태그를 절대 임의로 옮기거나 삭제하지 마세요.

    <br><hr style="border: 0; height: 1px; background: #ddd; margin: 40px 0;"><br>
    
    <h1>[{category_name} 심층분석] {t2_kr}</h1>
    
    [IMAGE_PLACEHOLDER_4]
    
    <h2>1. 배경 및 개요 (The Context)</h2>
    (지침: 현 상황을 뻔하지 않게 3줄 요약 리스트(<ul>)로 제시)
    
    <h2>2. 기존 기술/약물과의 차별점 (Comparative Analysis)</h2>
    (지침: 과거 유사했던 사례와 비교하여 이번 주제의 진짜 혁신 포인트가 무엇인지 에디터의 시각으로 분석)
    
    [IMAGE_PLACEHOLDER_5]
    
    <h2>3. 기술적 메커니즘 (Technical Deep-Dive)</h2>
    (지침: <table>을 1개 이상 반드시 포함. 전문적이지만 독자가 이해하기 쉽게 적절한 비유를 섞어 설명)
    
    <div class="adsense-placeholder" style="text-align:center; margin: 30px 0; padding: 20px; background:#f8f9fa; color:#adb5bd; border:2px dashed #dee2e6; border-radius: 8px; font-weight: bold;">[💰 애드센스 본문 중단 광고 삽입 위치 2]</div>

    <h2>4. 시장 판도 및 경쟁사 분석 (Market Dynamics)</h2>
    (지침: 객관적인 데이터와 함께, 구체적이고 주관적인 기업/기술 간 우위 분석을 반드시 작성)
    
    <h2>5. 리스크 및 한계점 (Risk Factors)</h2>
    (지침: 표면적인 리스크가 아닌, 실무자/투자자 관점에서의 진짜 걸림돌(규제, 경쟁 심화, 기술적 장벽 등)을 예리하게 지적)
    
    [IMAGE_PLACEHOLDER_6]
    
    <h2>6. 긍정적 전망 및 기대 효과 (Future Hope & Impact)</h2>
    (지침: 이 변화가 가져올 미래 산업의 모습을 생생하게 그려주듯 서술)
    
    <h2>7. 스포(spo)의 인사이트 (Actionable Insights)</h2>
    (지침: 단순 요약 금지. "그래서 지금 우리는 무엇을 주목해야 하는가?"에 대한 에디터 스포의 매우 주관적이고 사람 냄새 나는 솔직한 총평과 투자/산업적 조언)
    
    <br><hr style="border: 0; height: 2px; background: #2c3e50; margin: 50px 0;"><br>
    
    <h2>🎯 통합 인사이트: 두 뉴스가 그리는 미래 (The Bridge)</h2>
    (지침: 두 주제를 관통하는 핵심 인사이트 작성)
    
    <h2>📖 오늘의 용어 정리 (Glossary)</h2>
    (지침: <u> 태그로 표시한 용어들 정리)
    
    <div class="adsense-placeholder" style="text-align:center; margin: 30px 0; padding: 20px; background:#f8f9fa; color:#adb5bd; border:2px dashed #dee2e6; border-radius: 8px; font-weight: bold;">[💰 애드센스 본문 하단 광고 삽입 위치 3]</div>

    <h2>🔍 SEO 및 메타 데이터 (업로드용)</h2>
    <div style="background-color: #f1f8ff; padding: 15px; border-radius: 8px; font-size: 0.9em; color: #333;">
        <p><b>💡 구글 검색엔진 최적화(SEO)를 위한 요약 및 태그</b><br>티스토리 '설명' 란과 '태그' 란에 아래 내용을 복사해서 넣으세요.</p>
        <p><b>Meta Description:</b> (지침: 본문 전체의 핵심을 관통하고 독자의 클릭을 유발할 수 있는 150자 내외의 한국어 요약문 작성)</p>
        <p><b>Tags:</b> (지침: 검색량이 많을 만한 핵심 키워드 10개 이상 쉼표로 구분하여 작성)</p>
    </div>

    <script type="application/ld+json">
    (지침: 아래 JSON-LD 형식에 맞춰 스키마 마크업을 완성하세요. Description은 위에서 작성한 Meta Description과 동일하게 작성할 것.)
    {{
      "@context": "https://schema.org",
      "@type": "Article",
      "headline": "[{category_name} 분석] {t1_kr} 외 핵심 이슈",
      "description": "[여기에 작성한 150자 Meta Description 삽입]",
      "author": {{
        "@type": "Person",
        "name": "스포(spo)"
      }}
    }}
    </script>
    
    <hr style="border: 0; height: 1px; background: #eee; margin: 40px 0;">
    <p style="color:grey; font-size: 0.9em; text-align: center;">* 본 콘텐츠는 정보 제공을 목적으로 하며, 투자의 책임은 본인에게 있습니다. <br> Editor: 스포(spo)</p>
    """
    part2_res = client.models.generate_content(model=MODEL_ID, contents=p2_prompt).text
    time.sleep(5)
    part2 = re.sub(r"```[a-zA-Z]*\n?|```", "", part2_res).strip()
    
    return part1 + "\n" + part2

# --- 5. 이미지, 목차 생성 및 이메일 전송 ---
def get_image_tag(keyword, used_urls, alt_text=""):
    search_query = f"{keyword}"
    url = f"https://api.unsplash.com/search/photos?query={search_query}&per_page=5&orientation=landscape&client_id={UNSPLASH_ACCESS_KEY}"
    try:
        data = requests.get(url, timeout=5).json()
        if not data.get('results'): 
            return ""
        
        img_url = ""
        for res in data['results']:
            candidate_url = res['urls']['regular']
            if candidate_url not in used_urls:
                img_url = candidate_url
                used_urls.add(img_url)
                break
        
        if not img_url:
            img_url = data['results'][0]['urls']['regular']
            used_urls.add(img_url)

        return f"""
        <figure style="margin: 30px 0;">
            <img src='{img_url}' alt='{alt_text}' style='width:100%; border-radius:12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);'>
            <figcaption style='color:#666; font-size:13px; text-align:center; margin-top:10px;'>Source: Unsplash ({keyword})</figcaption>
        </figure>
        """
    except: return ""

def inject_images(html_text, t1, t2, mode):
    fb_defaults = []
    if mode == "BIO":
        theme_instruction = "'laboratory', 'doctor', 'medicine', 'biology', 'DNA' 같이 바이오/의료 분야와 관련된 직관적이고 시각적인 범용 단어"
        fb_defaults = ["biology laboratory", "medical research", "healthcare technology", "medicine", "dna structure", "biotech"]
    elif mode == "PATENT":
        theme_instruction = "'blueprint', 'patent', 'document', 'invention', 'innovation' 같이 특허/발명 분야와 관련된 직관적이고 시각적인 범용 단어"
        fb_defaults = ["blueprint architecture", "patent document", "technology invention", "business innovation", "future prototype", "design patent"]
    else: # TECH
        theme_instruction = "'technology', 'software', 'computer', 'digital', 'network' 같이 IT/테크 분야와 관련된 직관적이고 시각적인 범용 단어"
        fb_defaults = ["digital technology", "software code", "future tech", "network data", "cyber security", "ai interface"]

    # 수익화/SEO 포인트 4: Alt 태그 구체화를 위해 프롬프트 및 JSON 스키마 수정
    prompt = f"""
    Unsplash 이미지 검색용 영문 키워드와 이미지 구체적 묘사(Alt 태그용)를 함께 추출해줘. 복잡한 고유명사나 특정 번호 등은 모두 배제하고, 반드시 본문 내용과 연관되면서 {theme_instruction} 3개씩 총 6개 출력해.
    Alt 태그용 설명은 구글 이미지 검색(SEO) 최적화를 위해, 해당 이미지가 나타내는 상황을 한국어로 30자 이내로 생생하고 구체적으로 묘사해줘. (예: "미래 지향적인 AI 소프트웨어 데이터 구조도")
    
    아래 JSON 형식에 맞춰서 6개의 키워드와 6개의 설명을 작성해줘. 기호 없이 영문(키워드) 및 한글(설명)만 작성.

    [주제 1] {t1['title']}
    [주제 2] {t2['title']}

    출력 형식 (반드시 JSON 코드만 출력):
    {{
        "k1_1": "주제1 첫번째 키워드", "alt1_1": "주제1 첫번째 이미지 구체적 묘사",
        "k1_2": "주제1 두번째 키워드", "alt1_2": "주제1 두번째 이미지 구체적 묘사",
        "k1_3": "주제1 세번째 키워드", "alt1_3": "주제1 세번째 이미지 구체적 묘사",
        "k2_1": "주제2 첫번째 키워드", "alt2_1": "주제2 첫번째 이미지 구체적 묘사",
        "k2_2": "주제2 두번째 키워드", "alt2_2": "주제2 두번째 이미지 구체적 묘사",
        "k2_3": "주제2 세번째 키워드", "alt2_3": "주제2 세번째 이미지 구체적 묘사"
    }}
    """
    
    try:
        response_text = client.models.generate_content(model=MODEL_ID, contents=prompt).text.strip()
        time.sleep(5) # API 호출 제한 방지
        json_str = re.sub(r"```[a-zA-Z]*\n?|```", "", response_text).strip()
        keywords = json.loads(json_str)
        
        k1_1 = re.sub(r'[^a-zA-Z0-9\s]', '', keywords.get("k1_1", fb_defaults[0]))
        alt1_1 = keywords.get("alt1_1", t1['title'])
        k1_2 = re.sub(r'[^a-zA-Z0-9\s]', '', keywords.get("k1_2", fb_defaults[1]))
        alt1_2 = keywords.get("alt1_2", "Analysis 1")
        k1_3 = re.sub(r'[^a-zA-Z0-9\s]', '', keywords.get("k1_3", fb_defaults[2]))
        alt1_3 = keywords.get("alt1_3", "Analysis 2")
        k2_1 = re.sub(r'[^a-zA-Z0-9\s]', '', keywords.get("k2_1", fb_defaults[3]))
        alt2_1 = keywords.get("alt2_1", t2['title'])
        k2_2 = re.sub(r'[^a-zA-Z0-9\s]', '', keywords.get("k2_2", fb_defaults[4]))
        alt2_2 = keywords.get("alt2_2", "Market Insight 1")
        k2_3 = re.sub(r'[^a-zA-Z0-9\s]', '', keywords.get("k2_3", fb_defaults[5]))
        alt2_3 = keywords.get("alt2_3", "Market Insight 2")

    except Exception as e: 
        print(f"Keyword JSON parsing failed: {e}")
        k1_1, k1_2, k1_3 = fb_defaults[0], fb_defaults[1], fb_defaults[2]
        alt1_1, alt1_2, alt1_3 = t1['title'], "Analysis 1", "Analysis 2"
        k2_1, k2_2, k2_3 = fb_defaults[3], fb_defaults[4], fb_defaults[5]
        alt2_1, alt2_2, alt2_3 = t2['title'], "Market Insight 1", "Market Insight 2"
    
    used_urls = set() 
    
    html_text = html_text.replace("[IMAGE_PLACEHOLDER_1]", get_image_tag(k1_1, used_urls, alt1_1))
    html_text = html_text.replace("[IMAGE_PLACEHOLDER_2]", get_image_tag(k1_2, used_urls, alt1_2)) 
    html_text = html_text.replace("[IMAGE_PLACEHOLDER_3]", get_image_tag(k1_3, used_urls, alt1_3)) 
    html_text = html_text.replace("[IMAGE_PLACEHOLDER_4]", get_image_tag(k2_1, used_urls, alt2_1))
    html_text = html_text.replace("[IMAGE_PLACEHOLDER_5]", get_image_tag(k2_2, used_urls, alt2_2))
    html_text = html_text.replace("[IMAGE_PLACEHOLDER_6]", get_image_tag(k2_3, used_urls, alt2_3))
    return html_text

def generate_toc_and_add_ids(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    toc_html = "<div class='spo-toc' style='background-color: #f8f9fa; padding: 25px; border-radius: 12px; margin-bottom: 40px; border: 1px solid #e9ecef;'>\n"
    toc_html += "<h2 style='margin-top: 0; color: #2c3e50; font-size: 1.4em; border-bottom: 2px solid #3498db; padding-bottom: 10px; display: inline-block;'>📑 목차</h2>\n"
    toc_html += "<ul style='list-style-type: none; padding-left: 0; margin-bottom: 0; line-height: 1.8;'>\n"
    
    headings = soup.find_all(['h1', 'h2'])
    for idx, tag in enumerate(headings):
        anchor_id = f"section-{idx}"
        tag['id'] = anchor_id
        text = tag.get_text(strip=True)
        
        if tag.name == 'h1':
            toc_html += f"<li style='margin-top: 15px; font-weight: bold; font-size: 1.1em;'><a href='#{anchor_id}' style='color: #2980b9; text-decoration: none;'>{text}</a></li>\n"
        elif tag.name == 'h2':
            toc_html += f"<li style='margin-top: 5px; margin-left: 20px; font-size: 0.95em;'><a href='#{anchor_id}' style='color: #34495e; text-decoration: none;'>- {text}</a></li>\n"
            
    toc_html += "</ul>\n</div>\n"
    return toc_html + str(soup)

def apply_namuwiki_tooltips(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    glossary_dict = {}
    glossary_header = soup.find(lambda tag: tag.name == 'h2' and '용어 정리' in tag.text)
    
    if glossary_header:
        list_tag = glossary_header.find_next_sibling(['ul', 'ol', 'dl'])
        if list_tag:
            for item in list_tag.find_all('li'):
                text = item.get_text(strip=True)
                if ':' in text:
                    parts = text.split(':', 1)
                elif '-' in text:
                    parts = text.split('-', 1)
                else:
                    continue
                    
                if len(parts) == 2:
                    term = parts[0].strip()
                    desc = parts[1].strip()
                    glossary_dict[term] = desc

    tooltip_css = """
    <style>
    .spo-tooltip-container {
        position: relative;
        display: inline-block;
        border-bottom: 2px dashed #3498db;
        color: #2980b9;
        cursor: pointer;
        font-weight: bold;
        text-decoration: none !important;
    }
    .spo-tooltip-container .spo-tooltip-text {
        visibility: hidden;
        width: max-content;
        max-width: 320px;
        background-color: #2c3e50;
        color: #ffffff;
        text-align: left;
        border-radius: 8px;
        padding: 10px 14px;
        position: absolute;
        z-index: 9999;
        bottom: 130%;
        left: 50%;
        transform: translateX(-50%);
        opacity: 0;
        transition: opacity 0.3s ease, transform 0.3s ease;
        font-size: 14px;
        font-weight: normal;
        line-height: 1.6;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        word-break: keep-all;
        white-space: pre-wrap;
    }
    .spo-tooltip-container .spo-tooltip-text::after {
        content: "";
        position: absolute;
        top: 100%;
        left: 50%;
        margin-left: -6px;
        border-width: 6px;
        border-style: solid;
        border-color: #2c3e50 transparent transparent transparent;
    }
    .spo-tooltip-container:hover .spo-tooltip-text,
    .spo-tooltip-container:active .spo-tooltip-text {
        visibility: visible;
        opacity: 1;
        transform: translateX(-50%) translateY(-3px);
    }
    </style>
    """

    if glossary_dict:
        for u_tag in soup.find_all('u'):
            term_text = u_tag.get_text(strip=True)
            
            matched_desc = None
            for key, desc in glossary_dict.items():
                if term_text.lower() in key.lower() or key.lower() in term_text.lower():
                    matched_desc = desc
                    break
            
            if matched_desc:
                span_container = soup.new_tag("span", attrs={"class": "spo-tooltip-container"})
                span_container.string = term_text
                
                span_tooltip = soup.new_tag("span", attrs={"class": "spo-tooltip-text"})
                span_tooltip.string = matched_desc
                
                span_container.append(span_tooltip)
                u_tag.replace_with(span_container)
                
    return tooltip_css + str(soup)

def send_email(subject, final_content):
    escaped_html = html.escape(final_content)
    email_body = f"""
    <div style="font-family: sans-serif; max-width: 800px; margin: 0 auto;">
        <h2 style="color: #2c3e50;">스포(spo) 편집장님, 새 포스팅이 준비되었습니다! 🎉</h2>
        <p style="color: #e74c3c; font-weight: bold;">[티스토리 업로드용 HTML 코드]</p>
        <textarea style="width: 100%; height: 200px; font-family: monospace; font-size: 13px; background-color: #f8f9fa; padding: 15px; border: 1px solid #ced4da; border-radius: 5px;" readonly>{escaped_html}</textarea>
        <hr style="border: 0; height: 1px; background: #ddd; margin: 40px 0;">
        <h3 style="color: #2c3e50;">👀 포스팅 미리보기</h3>
        <div style="border: 1px solid #eee; padding: 30px; border-radius: 10px; background-color: #fff;">
            {final_content}
        </div>
    </div>
    """

    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER 
    msg['Subject'] = subject
    msg.attach(MIMEText(email_body, 'html'))
    
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        print(f"✅ Email Sent: {subject}")
    except Exception as e:
        print(f"❌ Email Fail: {e}")

# --- 6. 통합 처리 함수 (history 파라미터 전달 추가) ---
def process_and_send(mode, category_korean, history):
    print(f"\n>>> Processing: {category_korean} ({mode})")
    candidates = get_candidates(mode)
    selected = select_top_2(candidates, history, category_korean)
    
    if len(selected) < 2:
        print(f"Not enough news for {mode}")
        return []
        
    t1_kr = get_catchy_korean_title(selected[0]['title'])
    t2_kr = get_catchy_korean_title(selected[1]['title'])
    
    # write_blog_post에 history 변수를 전달하여 내부 링크 생성에 활용
    raw_html = write_blog_post(selected[0], selected[1], category_korean, t1_kr, t2_kr, history)
    
    html_with_images = inject_images(raw_html, selected[0], selected[1], mode)
    
    html_with_toc = generate_toc_and_add_ids(html_with_images)
    
    html_with_tooltips = apply_namuwiki_tooltips(html_with_toc)
    
    final_tistory_content = f"""
    <div class="spo-analysis-report" style="line-height: 1.8; color: #333; font-family: 'Noto Sans KR', sans-serif; word-break: keep-all; padding: 10px;">
        {html_with_tooltips}
    </div>
    """
    
    subject = get_unified_subject(category_korean, t1_kr, t2_kr)
    send_email(subject, final_tistory_content)
    
    return selected

# --- 메인 실행 ---
def main():
    history_file = 'history.json'
    history = load_history(history_file)
    
    kst_now = datetime.datetime.now() + datetime.timedelta(hours=9)
    weekday = kst_now.weekday()
    
    new_items_total = []

    if weekday == 0: # 월요일
        items = process_and_send("TECH", "테크", history)
        new_items_total.extend(items)
    else: # 화~일요일
        items_bio = process_and_send("BIO", "바이오", history)
        new_items_total.extend(items_bio)
        items_patent = process_and_send("PATENT", "특허", history)
        new_items_total.extend(items_patent)
    
    if new_items_total:
        save_history(history_file, history, new_items_total)

if __name__ == "__main__":
    main()
