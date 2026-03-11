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

# --- 환경 변수 로드 ---
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
    prompt = f"역할: 전문 투자 블로거 '스포(spo)'.\n목표: {category_name} 분야 뉴스 2개 선정.\n[후보군]\n{cand_txt}\n조건: 숫자 2개만 반환 (예: 1, 4)."
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

def write_blog_post(topic1, topic2, category_name, t1_kr, t2_kr):
    dynamic_structure_rule = f"""
    [미션: 구글 애드센스 통과를 위한 '비정형' 고품질 포스팅 작성]
    1. 정해진 틀 파괴: 매번 구성을 다르게 하세요.
    2. 소제목 다양화: 대주제인 "{t1_kr}"과 "{t2_kr}" 아래에 붙는 소제목들을 내용에 맞춰 호기심을 유발하도록 지으세요.
    3. 인간적인 서론/결론: "안녕하세요, 스포(spo)입니다."로 반드시 시작하되, 요즘 시장 분위기나 고민을 섞어 매일 첫/끝 문단이 겹치지 않게 쓰세요.
    4. HTML 제약: 오직 <p>, <h2>, <h3>, <ul>, <li>, <strong>, <em>, <hr /> 태그만 사용. <div>, <style>, <blockquote> 금지.
    """
    prompt = f"""
    역할: 업계 10년차 전문 투자 블로거 '스포(spo)'.
    주제1: {topic1['title']} / 원문: {topic1['raw']}
    주제2: {topic2['title']} / 원문: {topic2['raw']}
    {dynamic_structure_rule}
    [출력 지침] 오직 HTML 코드만 출력. 글 흐름에 맞춰 [IMAGE_PLACEHOLDER_1]과 [IMAGE_PLACEHOLDER_2]를 1번씩만 삽입.
    """
    try:
        response = client.models.generate_content(model=MODEL_ID, contents=prompt)
        time.sleep(25) 
        if not response.candidates or not response.candidates[0].content.parts:
             return "<p>안녕하세요, 스포(spo)입니다. 오류: 구글 AI가 안전 필터 문제로 답변 생성을 차단했습니다.</p>"
        return re.sub(r"```[a-zA-Z]*\n?|```", "", response.text).strip()
    except Exception as e:
        return f"<h3>🚨 AI API 호출 에러 발생</h3><p>스포(spo)입니다. 에러 원인: {str(e)}</p>"

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
        return f'<figure>\n    <img src="{img_url}" alt="{alt_text}" />\n</figure>'
    except: return ""

def inject_images(html_text, t1, t2, mode):
    fb_defaults = ["biology", "medicine"]
    try:
        prompt = f"주제1({t1['title']})과 주제2({t2['title']})에 어울리는 Unsplash 이미지 검색 영문 키워드 2개를 추출해.\n출력 예시: {{\"k1\": \"영문키워드1\", \"k2\": \"영문키워드2\"}}"
        res = client.models.generate_content(model=MODEL_ID, contents=prompt).text.strip()
        time.sleep(15) 
        json_str = re.sub(r"```[a-zA-Z]*\n?|```", "", res).strip()
        keywords = json.loads(json_str)
        k1, k2 = keywords.get("k1", fb_defaults[0]), keywords.get("k2", fb_defaults[1])
    except: k1, k2 = fb_defaults[0], fb_defaults[1]
    
    used_urls = set() 
    html_text = html_text.replace("[IMAGE_PLACEHOLDER_1]", get_image_tag(k1, used_urls, "본문 관련 이미지 1"))
    html_text = html_text.replace("[IMAGE_PLACEHOLDER_2]", get_image_tag(k2, used_urls, "본문 관련 이미지 2")) 
    return html_text

def send_email(subject, final_content):
    escaped_html = html.escape(final_content)
    email_body = f"""
    <div style="font-family: sans-serif; max-width: 800px; margin: 0 auto;">
        <h2>스포(spo)님, 새 포스팅 HTML입니다!</h2>
        <textarea style="width: 100%; height: 300px; font-family: monospace; font-size: 13px; padding: 10px;" readonly>{escaped_html}</textarea>
        <hr /><h3>👀 포스팅 미리보기</h3><div style="border: 1px solid #ccc; padding: 20px;">{final_content}</div>
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
    except Exception as e: print(f"❌ Email Fail: {e}")

def process_and_send(mode, category_korean, history):
    print(f"\n>>> Processing: {category_korean} ({mode})")
    candidates = get_candidates(mode)
    selected = select_top_2(candidates, history, category_korean)
    if len(selected) < 2: return []
    t1_kr = get_catchy_korean_title(selected[0]['title'])
    t2_kr = get_catchy_korean_title(selected[1]['title'])
    raw_html = write_blog_post(selected[0], selected[1], category_korean, t1_kr, t2_kr)
    final_tistory_content = inject_images(raw_html, selected[0], selected[1], mode)
    subject = get_unified_subject(category_korean, t1_kr, t2_kr)
    send_email(subject, final_tistory_content)
    return selected

# --- 메인 실행 (bio.py) ---
def main():
    history_file = 'history.json'
    history = load_history(history_file)
    kst_now = datetime.datetime.now() + datetime.timedelta(hours=9)
    weekday = kst_now.weekday()
    
    if weekday != 0: # 0(월요일)이 아닐 때만 실행
        print("💡 오늘은 화~일요일! [바이오] 포스팅을 시작합니다.")
        items = process_and_send("BIO", "바이오", history)
        if items: save_history(history_file, history, items)
    else:
        print("오늘은 월요일입니다. 바이오 스크립트를 건너뜁니다.")

if __name__ == "__main__":
    main()
