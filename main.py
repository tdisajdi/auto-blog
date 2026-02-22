import os
import json
import datetime
import time
import requests
import feedparser
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import google.generativeai as genai 
import re
import html
from bs4 import BeautifulSoup

# --- 환경 변수 로드 ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

# Gemini 설정
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-3-flash-preview')

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
        cutoff = datetime.datetime.now() - datetime.timedelta(days=7)
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
        res = model.generate_content(prompt)
        nums = [int(s) for s in re.findall(r'\b\d+\b', res.text)]
        if len(nums) >= 2:
            return [filtered[nums[0]], filtered[nums[1]]]
    except: pass
    return filtered[:2]

# --- 3. 글 작성 ---
def write_blog_post(topic1, topic2, category_name):
    print(f"Writing {category_name} Post with Gemini...")
    
    # 애드센스 승인 및 고품질 콘텐츠를 위한 문체 프롬프트 유지
    tone_rule = """
    [구글 애드센스 고품질 콘텐츠를 위한 필수 문체 및 어조 지침]
    1. 문체: 가벼운 블로그 말투를 배제하고, 경제/테크 주요 언론사의 전문 칼럼니스트처럼 신뢰감 있고 정중한 경어체(~습니다, ~합니다)를 사용하세요.
    2. 전문성(E-E-A-T 충족): 단순 사실의 나열이 아닌, 현상의 원인과 향후 파급력을 논리적이고 깊이 있게 분석하세요. 독자에게 실질적인 가치를 제공해야 합니다.
    3. AI 말투 엄격 금지: '결론적으로', '알아보겠습니다', '이 기사를 통해', '안녕하세요' 등 AI 특유의 기계적이고 상투적인 도입/마무리 표현을 절대 금지합니다. 문단과 문단 사이를 아주 자연스럽게 이어주세요.
    4. 체류 시간 유도: 문장은 간결하면서도 정보의 밀도를 높여 작성하여 독자의 이탈을 방지하세요.
    """

    # [수정된 부분] 7단계 구조로 확장 (차별점 비교 및 긍정적 전망 추가)
    structure_instruction = """
    각 주제별로 반드시 아래 7가지 H2 태그 섹션을 포함해야 함:
    1. <h2>1. 배경 및 개요 (The Context)</h2> : 현 상황을 3줄 요약 리스트(<ul>)로 제시.
    2. <h2>2. 기존 기술/약물과의 차별점 (Comparative Analysis)</h2> : 과거 유사했던 특허나 기술, 약물 등과 비교하여 이번 주제가 어떤 방식으로 혁신적인지 명확히 분석.
    3. <h2>3. 기술적 메커니즘 (Technical Deep-Dive)</h2> : <table>을 1개 이상 반드시 포함.
    4. <h2>4. 시장 판도 및 경쟁사 분석 (Market Dynamics)</h2> : 객관적인 [수치/데이터] 포함.
    5. <h2>5. 리스크 및 한계점 (Risk Factors)</h2> : 규제, 경쟁, 기술적 장벽 분석.
    6. <h2>6. 긍정적 전망 및 기대 효과 (Future Hope & Impact)</h2> : 이 기술/약물이 향후 관련 산업이나 인류에게 가져올 희망적인 미래와 긍정적 파급력 서술.
    7. <h2>7. 스포(spo)의 인사이트 (Actionable Insights)</h2> : 시사점.
    """
    glossary_rule = "어려운 '전문 용어'는 반드시 <u> 태그로 감싸주세요."
    bold_rule = "가독성을 높이기 위해 문단에서 가장 중요한 '핵심 문장'과 '주요 키워드(단어)'는 반드시 <b> 태그를 사용하여 굵게 강조해주세요."

    outline = model.generate_content(f"주제1: {topic1['title']}\n주제2: {topic2['title']}\n위 두 주제로 '{category_name} 심층 분석' 개요 작성.").text
    
    p1_prompt = f"""
    역할: 독보적인 통찰력을 지닌 {category_name} 분야 최고 전문 분석가 '스포(spo)'.
    개요: {outline}
    주제 1: {topic1['title']} / 원문 내용: {topic1['raw']}
    {tone_rule}
    {glossary_rule}\n{bold_rule}
    [작성 지침] HTML 태그만 출력.
    <h1>[{category_name} 심층분석] {topic1['title']}</h1>
    [IMAGE_PLACEHOLDER_1]
    {structure_instruction}
    [IMAGE_PLACEHOLDER_2]
    주제 1의 내용만 작성.
    """
    part1 = re.sub(r"```[a-zA-Z]*\n?|```", "", model.generate_content(p1_prompt).text).strip()
    
    p2_prompt = f"""
    앞부분: {part1}
    주제 2: {topic2['title']} / 원문 내용: {topic2['raw']}
    {tone_rule}
    {glossary_rule}\n{bold_rule}
    [작성 지침] 앞 내용과 자연스럽게 이어지도록 작성. HTML 태그만 출력.
    <br><hr style="border: 0; height: 1px; background: #ddd; margin: 40px 0;"><br>
    <h1>[{category_name} 심층분석] {topic2['title']}</h1>
    [IMAGE_PLACEHOLDER_3]
    {structure_instruction}
    [IMAGE_PLACEHOLDER_4]
    <br><hr style="border: 0; height: 2px; background: #2c3e50; margin: 50px 0;"><br>
    <h2>🎯 통합 인사이트: 두 뉴스가 그리는 미래 (The Bridge)</h2>
    <h2>📖 오늘의 용어 정리 (Glossary)</h2>
    <h2>🔍 SEO 및 태그 정보 (업로드용)</h2>
    <hr style="border: 0; height: 1px; background: #eee; margin: 40px 0;">
    <p style="color:grey; font-size: 0.9em; text-align: center;">* 본 콘텐츠는 정보 제공을 목적으로 하며, 투자의 책임은 본인에게 있습니다. <br> Editor: 스포(spo)</p>
    """
    part2 = re.sub(r"```[a-zA-Z]*\n?|```", "", model.generate_content(p2_prompt).text).strip()
    
    return part1 + "\n" + part2

# --- 4. 이미지, 목차 생성 및 이메일 전송 ---
def get_image_tag(keyword, alt_text=""):
    search_query = f"{keyword}"
    url = f"https://api.unsplash.com/search/photos?query={search_query}&per_page=1&orientation=landscape&client_id={UNSPLASH_ACCESS_KEY}"
    try:
        data = requests.get(url, timeout=5).json()
        if not data['results']: 
            return ""
        img_url = data['results'][0]['urls']['regular']
        return f"""
        <figure style="margin: 30px 0;">
            <img src='{img_url}' alt='{alt_text}' style='width:100%; border-radius:12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);'>
            <figcaption style='color:#666; font-size:13px; text-align:center; margin-top:10px;'>Source: Unsplash ({keyword})</figcaption>
        </figure>
        """
    except: return ""

def inject_images(html_text, t1, t2):
    prompt = "Unsplash 이미지 검색용 영문 키워드를 추출해줘. 복잡한 고유명사, 신약 이름, 특허 번호 등은 모두 배제하고 'laboratory', 'doctor', 'medicine', 'blueprint', 'technology innovation' 같이 매우 직관적이고 시각적인 범용 단어 1~2개만 출력해. 기호 없이 영문만 출력:\n{}"
    try:
        k1_main = re.sub(r'[^a-zA-Z0-9\s]', '', model.generate_content(prompt.format(t1['title'])).text.strip())
        k1_sub = re.sub(r'[^a-zA-Z0-9\s]', '', model.generate_content(prompt.format(t1['title'] + " (Focus on abstract business or data concept)")).text.strip())
        k2_main = re.sub(r'[^a-zA-Z0-9\s]', '', model.generate_content(prompt.format(t2['title'])).text.strip())
        k2_sub = re.sub(r'[^a-zA-Z0-9\s]', '', model.generate_content(prompt.format(t2['title'] + " (Focus on abstract business or data concept)")).text.strip())
    except: 
        k1_main, k1_sub = "science research", "data analysis"
        k2_main, k2_sub = "future technology", "business innovation"
    
    html_text = html_text.replace("[IMAGE_PLACEHOLDER_1]", get_image_tag(k1_main, t1['title']))
    html_text = html_text.replace("[IMAGE_PLACEHOLDER_2]", get_image_tag(k1_sub, "Analysis")) 
    html_text = html_text.replace("[IMAGE_PLACEHOLDER_3]", get_image_tag(k2_main, t2['title']))
    html_text = html_text.replace("[IMAGE_PLACEHOLDER_4]", get_image_tag(k2_sub, "Market Insight"))
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

# --- 5. 통합 처리 함수 ---
def process_and_send(mode, category_korean, history):
    print(f"\n>>> Processing: {category_korean} ({mode})")
    candidates = get_candidates(mode)
    selected = select_top_2(candidates, history, category_korean)
    
    if len(selected) < 2:
        print(f"Not enough news for {mode}")
        return []
        
    raw_html = write_blog_post(selected[0], selected[1], category_korean)
    html_with_images = inject_images(raw_html, selected[0], selected[1])
    
    html_with_toc = generate_toc_and_add_ids(html_with_images)
    
    html_with_tooltips = apply_namuwiki_tooltips(html_with_toc)
    
    final_tistory_content = f"""
    <div class="spo-analysis-report" style="line-height: 1.8; color: #333; font-family: 'Noto Sans KR', sans-serif; word-break: keep-all; padding: 10px;">
        {html_with_tooltips}
    </div>
    """
    
    try:
        t1_kr = model.generate_content(f"다음 영문 제목을 자연스러운 한국어 블로그 제목으로 번역해. 다른 말 없이 결과만 출력해:\n{selected[0]['title']}").text.strip()
        t2_kr = model.generate_content(f"다음 영문 제목을 자연스러운 한국어 블로그 제목으로 번역해. 다른 말 없이 결과만 출력해:\n{selected[1]['title']}").text.strip()
    except:
        t1_kr, t2_kr = selected[0]['title'], selected[1]['title']
    
    subject = f"[{category_korean} 분석] {t1_kr} & {t2_kr}"
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
