import os
import json
import datetime
import time
import requests
import feedparser
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google import genai
import re
import html
from bs4 import BeautifulSoup
import random

# --- 환경 변수 로드 (GitHub Actions 용) ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

client = genai.Client(api_key=GEMINI_API_KEY, http_options={'timeout': 600000})
MODEL_ID = 'gemini-3-flash-preview'

def load_history(filepath):
    if not os.path.exists(filepath): return []
    try:
        with open(filepath, 'r', encoding='utf-8') as f: return json.load(f)
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
    for item in new_items: cleaned.append({"id": item['id'], "title": item['title'], "date": today})
    with open(filepath, 'w', encoding='utf-8') as f: json.dump(cleaned, f, ensure_ascii=False, indent=4)

def scrape_article_text(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=5)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        paragraphs = soup.find_all('p')
        text = " ".join([p.get_text() for p in paragraphs])
        return text[:3000] if len(text) > 100 else None 
    except: return None

def fetch_rss(url, category):
    items = []
    try:
        feed = feedparser.parse(url)
        cutoff = datetime.datetime.now() - datetime.timedelta(days=3)
        for entry in feed.entries:
            if 'published_parsed' in entry and entry.published_parsed:
                pub_date = datetime.datetime.fromtimestamp(time.mktime(entry.published_parsed))
                if pub_date < cutoff: continue
            raw_text = scrape_article_text(entry.link)
            if not raw_text: raw_text = (entry.summary if 'summary' in entry else entry.title)[:2000]
            items.append({"id": entry.link, "title": entry.title, "type": category, "raw": raw_text})
    except: pass
    return items

def get_candidates(mode):
    items = []
    if mode == "TECH": urls = ["https://www.theverge.com/rss/index.xml", "https://techcrunch.com/feed/"]
    elif mode == "BIO": urls = ["https://news.google.com/rss/search?q=Biotech+OR+%22FDA+approval%22+OR+%22Clinical+Trial%22&hl=en-US&gl=US&ceid=US:en"]
    elif mode == "PATENT": urls = ["https://news.google.com/rss/search?q=Patent+OR+%22Technology+Innovation%22+OR+%22Future+Tech%22&hl=en-US&gl=US&ceid=US:en"]
    for u in urls: items.extend(fetch_rss(u, mode))
    return items

def select_top_2(candidates, history, category_name):
    history_ids = [h['id'] for h in history]
    filtered = [c for c in candidates if c['id'] not in history_ids]
    if len(filtered) < 2: return filtered[:2]
    cand_txt = "\n".join([f"{i}. {c['title']}" for i, c in enumerate(filtered[:15])])
    prompt = f"역할: 전문 투자 블로거 '핀큐(Fin-q)'.\n목표: {category_name} 분야 뉴스 2개 선정.\n[후보군]\n{cand_txt}\n조건: 숫자 2개만 반환 (예: 1, 4)."
    try:
        res = client.models.generate_content(model=MODEL_ID, contents=prompt)
        time.sleep(15) 
        nums = [int(s) for s in re.findall(r'\b\d+\b', res.text)]
        if len(nums) >= 2: return [filtered[nums[0]], filtered[nums[1]]]
    except: pass
    return filtered[:2]

def get_catchy_korean_title(english_title):
    prompt = f"다음 영문 뉴스 제목을 100% 한국어로 30자 이내 간결한 블로그 소제목(H2)으로 번역해. 오직 제목 1개만 출력.\n영문: {english_title}"
    try:
        res = client.models.generate_content(model=MODEL_ID, contents=prompt).text.strip()
        time.sleep(15) 
        return res
    except: return english_title

def get_unified_subject(category_name, t1_kr, t2_kr):
    prompt = f"두 뉴스 제목을 아우르는 이메일 메인 제목 작성 (최대 35자, 1개만 출력).\n주제1: {t1_kr}\n주제2: {t2_kr}"
    try:
        res = client.models.generate_content(model=MODEL_ID, contents=prompt).text.strip()
        time.sleep(15) 
        return f"[{category_name} 이슈] {res}"
    except: return f"[{category_name} 이슈] 오늘의 핵심 분석"

def write_blog_post(topic1, topic2, category_name, t1_kr, t2_kr, history):
    history_text = "이전 발행 글 없음"
    if history:
        history_titles = [h.get('title', '') for h in history[-15:]]
        history_text = "\n".join([f"- {title}" for title in history_titles])
        # 💡 [핵심 변경] 프롬프트 최상단 규칙으로 승격시킬 링크 규칙
        link_rule = """3. 🚨 내부 링크 강제 주입 (절대 누락 금지):
       아래 제공된 [이전 발행 글 목록] 중 가장 잘 맞는 글 1개를 무조건 선택해서 본문 문장 속에 언급하세요.
       언급할 때는 반드시 대괄호를 사용하여 [링크: 선택한 이전 글 제목] 형태로 정확히 적어야 합니다.
       (작성 예시: "최근 흐름은 지난번 다루었던 [링크: 이전 글 제목] 포스팅과 비슷한 맥락입니다.")"""
    else:
        link_rule = "3. 내부 링크: 이전 발행 글이 없으므로 생략합니다."

    include_table = random.choice([True, False]) 
    if include_table:
        table_styles = [
            "모던 스타일 (border-collapse: collapse; border-bottom: 1px solid #ddd;)",
            "클래식 스타일 (border-collapse: collapse; 짝수 행 배경색)",
            "심플 스타일 (border-collapse: collapse; 테두리 연하게)"
        ]
        t_style = random.choice(table_styles)
        table_instruction = f"- 비교표: 글 중간에 <table> 1개 삽입. 디자인: [{t_style}] 적용."
    else:
        table_instruction = ""

    writing_styles = [
        "개인적인 투자 경험담이나 시장의 피로감 등을 편안하게 푸는 에세이 형식",
        "핵심만 빠르게 짚어주는 리스트형 요약 시작",
        "스스로 질문을 던지고 답을 편안하게 풀어가는 Q&A 형식",
        "친한 지인에게 시장 상황을 설명해주듯 편안하고 쉬운 말투"
    ]
    chosen_style = random.choice(writing_styles)

    dynamic_structure_rule = f"""
    [미션: 100% 인간이 쓴 듯한 고품질 실전 투자 포스팅 작성]
    
    1. 자연스러운 어투: 딱딱하고 과장된 전문가 흉내를 내지 마세요. 개인 블로거로서 힘을 빼고 편안하게 작성하세요.
    
    2. 글의 구조 (순서 엄수): 반드시 아래의 [4단계 순서]를 지켜서 작성해야 합니다.
       - 1단계 [도입부]: 반드시 "안녕하세요, 핀큐(Fin-q)입니다."라는 첫인사로 시작하고, [{chosen_style}]을 적용하여 자연스럽게 시작.
       - 2단계 [첫 번째 뉴스 상세 분석]: {t1_kr}에 대한 상세 본문.
       - 3단계 [두 번째 뉴스 상세 분석]: {t2_kr}에 대한 상세 본문.
       - 4단계 [통합 인사이트]: 수치(PER, 밸류에이션 등)를 근거로 한 주관적 평가 1~2줄 추가하여 결론 짓기.
       
    {link_rule}
       
    4. 템플릿 완전 파괴: '용어 정리', '면책 조항', '출처' 코너를 절대로 직접 만들지 마세요. (파이썬 코드가 자동으로 추가할 예정입니다.)

    [SEO 및 체류시간 부스터]
    {table_instruction}
    - 상장사 주가 링크: 언급된 기업 뒤에 <a> 태그 삽입 (예: <a href="https://kr.investing.com/search/?q=Apple" target="_blank">[📈주가확인]</a>)
    - 이미지 삽입: 글 흐름에 맞춰 [IMAGE_PLACEHOLDER_1]과 [IMAGE_PLACEHOLDER_2]를 각 1번씩 삽입.
    
    [이전 발행 글 목록 (이 중 하나를 골라 반드시 본문에 쓸 것)]
    {history_text}
    """
    
    prompt = f"""
    역할: 10년차 실전 투자 블로거 '핀큐(Fin-q)'.
    주제1: {topic1['title']} / 원문: {topic1['raw']}
    주제2: {topic2['title']} / 원문: {topic2['raw']}
    {dynamic_structure_rule}
    [출력 지침] 오직 순수 HTML 코드만 출력하세요.
    """
    try:
        response = client.models.generate_content(model=MODEL_ID, contents=prompt)
        time.sleep(25) 
        if not response.candidates or not response.candidates[0].content.parts: return "<p>에러: 구글 AI 차단.</p>"
        
        raw_html = re.sub(r"```[a-zA-Z]*\n?|```", "", response.text).strip()
        
        source_and_disclaimer_html = f"""
        <div style="margin-top: 40px; padding: 15px; background-color: #f8f9fa; border-radius: 5px; font-size: 0.9em;">
            <strong style="color: #2c3e50;">🔗 참고 자료 (원본 출처)</strong>
            <ul style="margin-top: 10px; padding-left: 20px; line-height: 1.6;">
                <li><a href="{topic1['id']}" target="_blank" style="color: #7f8c8d; text-decoration: underline;">{topic1['title']}</a></li>
                <li><a href="{topic2['id']}" target="_blank" style="color: #7f8c8d; text-decoration: underline;">{topic2['title']}</a></li>
            </ul>
        </div>
        <hr style="border: 0; border-top: 1px solid #eee; margin: 30px 0;">
        <p style="color: #95a5a6; font-size: 0.85em; text-align: center; line-height: 1.5;">
            * 본 포스팅은 정보 제공을 목적으로 하며, 특정 종목에 대한 매수/매도 권유를 의미하지 않습니다.<br>
            투자의 최종 책임은 본인에게 있으며, 시장 상황에 따라 변동성이 발생할 수 있습니다.<br>
            <strong>Editor: 핀큐(Fin-q)</strong>
        </p>
        """
        
        return raw_html + source_and_disclaimer_html
        
    except Exception as e: return f"<h3>🚨 AI API 에러</h3><p>{str(e)}</p>"

def get_image_tag(keyword, used_urls, alt_text=""):
    url = f"https://api.unsplash.com/search/photos?query={keyword}&per_page=5&orientation=landscape&client_id={UNSPLASH_ACCESS_KEY}"
    try:
        data = requests.get(url, timeout=5).json()
        if not data.get('results'): return ""
        img_url = ""
        for res in data['results']:
            if res['urls']['regular'] not in used_urls:
                img_url = res['urls']['regular']
                used_urls.add(img_url)
                break
        if not img_url:
            img_url = data['results'][0]['urls']['regular']
            used_urls.add(img_url)
        return f'<figure style="margin: 30px 0;">\n    <img src="{img_url}" alt="{alt_text}" style="width:100%; border-radius:12px;" />\n</figure>'
    except: return ""

def inject_images(html_text, t1, t2, mode):
    fb_defaults = ["technology innovation", "software logic"]
    try:
        prompt = f"주제1({t1['title']})과 주제2({t2['title']})에 어울리는 Unsplash 영문 키워드 2개 추출.\n출력: {{\"k1\": \"키워드1\", \"k2\": \"키워드2\"}}"
        res = client.models.generate_content(model=MODEL_ID, contents=prompt).text.strip()
        time.sleep(15) 
        json_str = re.sub(r"```[a-zA-Z]*\n?|```", "", res).strip()
        keywords = json.loads(json_str)
        k1, k2 = keywords.get("k1", fb_defaults[0]), keywords.get("k2", fb_defaults[1])
    except: k1, k2 = fb_defaults[0], fb_defaults[1]
    
    used_urls = set() 
    html_text = html_text.replace("[IMAGE_PLACEHOLDER_1]", get_image_tag(k1, used_urls, "테크 관련 이미지 1"))
    html_text = html_text.replace("[IMAGE_PLACEHOLDER_2]", get_image_tag(k2, used_urls, "테크 관련 이미지 2")) 
    return html_text

def send_email(subject, final_content):
    escaped_html = html.escape(final_content)
    email_body = f"""
    <div style="font-family: sans-serif; max-width: 800px; margin: 0 auto;">
        <h2>핀큐(Fin-q)님, 새 포스팅 HTML입니다!</h2>
        <textarea style="width: 100%; height: 300px; font-family: monospace; font-size: 13px; padding: 10px;" readonly>{escaped_html}</textarea>
        <hr /><h3>👀 포스팅 미리보기</h3><div style="border: 1px solid #ccc; padding: 20px; line-height: 1.6;">{final_content}</div>
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
    except: pass

def process_and_send(mode, category_korean, history):
    candidates = get_candidates(mode)
    selected = select_top_2(candidates, history, category_korean)
    if len(selected) < 2: return []
    
    t1_kr = get_catchy_korean_title(selected[0]['title'])
    t2_kr = get_catchy_korean_title(selected[1]['title'])
    
    # 💡 history.json에 향후 영문 대신 '한국어 번역 제목'이 저장되도록 데이터 덮어쓰기
    selected[0]['title'] = t1_kr
    selected[1]['title'] = t2_kr

    raw_html = write_blog_post(selected[0], selected[1], category_korean, t1_kr, t2_kr, history)
    final_tistory_content = inject_images(raw_html, selected[0], selected[1], mode)
    
    subject = get_unified_subject(category_korean, t1_kr, t2_kr)
    send_email(subject, final_tistory_content)
    return selected

def main():
    history_file = 'history.json'
    history = load_history(history_file)
    kst_now = datetime.datetime.now() + datetime.timedelta(hours=9)
    weekday = kst_now.weekday()
    
    if weekday == 0: 
        print("💡 [테크] 포스팅 시작.")
        items = process_and_send("TECH", "테크", history)
        if items: save_history(history_file, history, items)

if __name__ == "__main__":
    main()
