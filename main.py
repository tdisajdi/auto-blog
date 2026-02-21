import os
import json
import time
from datetime import datetime, timedelta
import pytz
import requests
import feedparser
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import google.generativeai as genai

# --- 환경 변수 로드 ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

# Gemini 설정
genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = 'gemini-3-flash-preview'

HISTORY_FILE = "history.json"

# --- 1. 유틸리티: 중복 방지를 위한 히스토리 관리 ---
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def clean_old_history(history):
    # 30일 지난 히스토리는 삭제
    now = datetime.now()
    cleaned = {}
    for link, date_str in history.items():
        try:
            date_obj = datetime.fromisoformat(date_str)
            if now - date_obj < timedelta(days=30):
                cleaned[link] = date_str
        except:
            pass
    return cleaned

# --- 2. 뉴스 데이터 수집 (최근 7일) ---
def get_articles_from_feeds(feed_urls, history):
    articles = []
    now = datetime.now()
    seven_days_ago = now - timedelta(days=7)
    
    for url in feed_urls:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            link = entry.link
            
            # 30일 내 포스팅했던 기사면 패스
            if link in history:
                continue
            
            # 최근 7일 기사만 수집
            try:
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_date = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    if pub_date < seven_days_ago:
                        continue
            except Exception:
                pass 
            
            articles.append({
                "title": entry.title,
                "link": link,
                "summary": entry.get('summary', '')[:500] 
            })
            
            # 최대 15개까지만 수집하여 AI 토큰 절약
            if len(articles) >= 15:
                return articles[:15]
                
    return articles[:15]

# --- 3. AI 편집장 선정 (Gemini) ---
def select_top_topics(articles, count=2, category_name="테크"):
    if len(articles) <= count:
        return articles
        
    print(f">>> AI 편집장이 [{category_name}] 분야에서 최적의 주제 선정 중...")
    model = genai.GenerativeModel(MODEL_NAME)
    
    prompt = f"""
    너는 '{category_name}' 분야 전문 블로그 편집장이야.
    아래 {len(articles)}개의 기사 후보군 중에서 '투자 가치가 가장 높고 심층 분석이 가능한' 가장 중요한 주제 {count}개를 골라줘.
    결과는 반드시 선택한 기사의 번호(1부터 시작)만 담긴 JSON 배열 형태로 반환해줘. (예: [1, 4])
    
    [기사 후보군]
    """
    for i, a in enumerate(articles):
        prompt += f"{i+1}. {a['title']}\n"
        
    try:
        # JSON 형식으로 안정적인 출력을 유도
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        indices = json.loads(response.text)
        selected = [articles[i-1] for i in indices[:count]]
        return selected
    except Exception as e:
        print(f">>> 주제 선정 AI 오류 (기본값 사용): {e}")
        return articles[:count]

# --- 4. 블로그 원고 작성 및 메타데이터 추출 (Gemini) ---
def generate_blog_content(news_list):
    print(f">>> Gemini(스포)가 5단계 심층 분석 글을 쓰는 중...")
    model = genai.GenerativeModel(MODEL_NAME)
    
    news_info = ""
    for i, news in enumerate(news_list):
        news_info += f"\n[주제 {i+1}]\n제목: {news['title']}\n요약: {news['summary']}\n링크: {news['link']}\n"
        
    prompt = f"""
    너는 IT/투자 전문 블로거 '스포(spo)'야. 아래 {len(news_list)}개의 뉴스를 묶어서 하나의 티스토리 블로그 포스팅으로 작성해.
    
    {news_info}
    
    [작성 조건]
    1. 글 제목은 제공된 주제들을 아우르면서 클릭을 유도하도록 매력적으로 지어줘. (가장 첫 줄에 <h1> 태그로 단 1번 작성)
    2. 서론은 "안녕하세요! 미래를 스포일러하는 스포(spo)입니다."로 시작해.
    3. 각 주제별로 전문적이면서도 쉽게 설명하고, 반드시 아래 5가지 섹션을 포함해:
       - 배경 및 개요 (The Context): 3줄 요약 리스트 (<ul>, <li> 사용)
       - 기술적 메커니즘 (Technical Deep-Dive): 기술 설명을 위한 HTML <table> 포함
       - 시장 판도 및 경쟁사 분석 (Market Dynamics): 구체적인 수치와 데이터 포함
       - 리스크 및 한계점 (Risk Factors): 비판적 시각의 분석
       - 스포(spo)의 인사이트 (Actionable Insights): 전문 분석가로서의 독자 제언
    4. 각 주제를 설명하는 첫 부분에 이미지가 들어갈 위치에 딱 1번씩 [IMAGE_PLACEHOLDER_{{주제번호}}] 라고 표시해. (총 {len(news_list)}개의 플레이스홀더)
    5. 결론에는 "더 많은 IT 소식이 궁금하다면 구독해주세요!"로 마무리해.
    6. 전체 내용은 티스토리에 붙여넣었을 때 바로 예쁘게 보이도록 모든 스타일을 inline-style(CSS)로 적용해. (배경색, 폰트 색상, 여백 등 깔끔하게)
    7. <html>, <body>, ```html 같은 불필요한 태그는 절대 쓰지 말고 <div> 태그로 전체를 감싸서 순수 HTML 코드만 줘.
    """
    
    response = model.generate_content(prompt)
    html_content = response.text.replace("```html", "").replace("```", "").strip()
    
    # 4-1. 메일 제목 및 검색용 키워드 분리 추출
    meta_prompt = f"""
    아래 블로그 원고를 읽고, 
    1) 메일 제목으로 쓸만한 멋진 제목 (이모지 포함, "[카테고리 분석]" 접두사 포함)
    2) Unsplash 이미지 검색용 영문 키워드 {len(news_list)}개 (각 주제의 핵심을 담은 1단어짜리 영어 단어)
    를 JSON 형식으로 반환해줘.
    
    형식 예시: 
    {{
        "mail_subject": "[카테고리 분석] 🚀 애플과 구글의 AI 전쟁이 바이오 시장에 미치는 영향",
        "keywords": ["apple", "biotech"]
    }}
    
    원고:
    {html_content[:1500]}
    """
    try:
        meta_res = model.generate_content(meta_prompt, generation_config={"response_mime_type": "application/json"})
        meta_data = json.loads(meta_res.text)
    except Exception:
        meta_data = {"mail_subject": "[카테고리 분석] 오늘의 딥다이브 리포트", "keywords": ["technology", "innovation"]}
        
    return html_content, meta_data

# --- 5. 이미지 검색 및 삽입 (Unsplash) ---
def add_images_to_html(html_content, keywords):
    print(f">>> 추출된 키워드({keywords})로 이미지 검색 및 삽입 중...")
    for i, keyword in enumerate(keywords):
        url = f"[https://api.unsplash.com/search/photos?query=](https://api.unsplash.com/search/photos?query=){keyword}&per_page=1&orientation=landscape&client_id={UNSPLASH_ACCESS_KEY}"
        placeholder = f"[IMAGE_PLACEHOLDER_{i+1}]"
        
        try:
            response = requests.get(url).json()
            results = response.get('results', [])
            
            if results:
                img_url = results[0]['urls']['regular']
                img_tag = f'<div style="text-align:center; margin: 30px 0;"><img src="{img_url}" style="width:100%; max-width:700px; border-radius:12px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);"></div>'
                html_content = html_content.replace(placeholder, img_tag)
            else:
                html_content = html_content.replace(placeholder, "")
        except Exception as e:
            print(f"이미지 처리 중 오류 발생: {e}")
            html_content = html_content.replace(placeholder, "")
            
    # 남아있는 플레이스홀더 잔재가 있다면 정리
    for i in range(1, 6):
         html_content = html_content.replace(f"[IMAGE_PLACEHOLDER_{i}]", "")
         
    return html_content

# --- 6. 이메일 발송 (소스코드 + 미리보기 템플릿) ---
def send_email(subject, html_body):
    print(f">>> 이메일 전송 시작: {subject}")
    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER
    msg['Subject'] = subject

    # HTML 코드를 텍스트박스에 넣기 위해 치환
    escaped_html = html_body.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    email_content = f"""
    <div style="font-family: 'Apple SD Gothic Neo', sans-serif; max-width: 850px; margin: auto; color: #333;">
        <h2 style="color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 10px;">📝 오늘의 포스팅 원고가 도착했습니다.</h2>
        <p style="font-size: 14px; color: #555;">아래 소스코드를 복사하여 티스토리 <b>[HTML 모드]</b>에 그대로 붙여넣으세요.</p>
        
        <textarea readonly style="width: 100%; height: 300px; padding: 15px; background-color: #f8f9fa; border: 1px solid #ced4da; border-radius: 8px; font-family: monospace; font-size: 13px; color: #d63384; line-height: 1.5;">
{escaped_html}
        </textarea>
        
        <hr style="margin: 50px 0; border: 0; border-top: 2px dashed #ddd;">
        
        <h2 style="color: #2c3e50; text-align: center; margin-bottom: 30px;">👀 실제 블로그 미리보기 👀</h2>
        <div style="border: 1px solid #e9ecef; padding: 30px; border-radius: 12px; background-color: #fff; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
            {html_body}
        </div>
    </div>
    """

    msg.attach(MIMEText(email_content, 'html'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        print(">>> ✅ 이메일 전송 성공!")
    except Exception as e:
        print(f">>> ❌ 이메일 전송 실패: {e}")

# --- 메인 실행 ---
def main():
    # 1. KST 기준 요일 확인 (0: 월요일 ~ 6: 일요일)
    kst = pytz.timezone('Asia/Seoul')
    now_kst = datetime.now(kst)
    weekday = now_kst.weekday() 
    
    print(f"\n========== 스포(spo) 자동화 봇 ==========")
    print(f">>> KST 현재 시간: {now_kst.strftime('%Y-%m-%d %H:%M:%S')}")
    
    history = load_history()
    history = clean_old_history(history)
    selected_news = []
    
    # 2. 요일에 따른 기사 수집 및 선정
    if weekday == 0:  # 월요일
        print(">>> [월요일 모드] 테크(TECH) 카테고리 기사 수집 (2개)")
        tech_feeds = [
            "[https://www.theverge.com/rss/index.xml](https://www.theverge.com/rss/index.xml)",
            "[https://techcrunch.com/feed/](https://techcrunch.com/feed/)"
        ]
        articles = get_articles_from_feeds(tech_feeds, history)
        selected_news = select_top_topics(articles, count=2, category_name="테크(TECH)")
        
    else:  # 화~일요일
        print(">>> [화~일 모드] 바이오(BIO) & 특허(PATENT) 수집 (각 1개)")
        bio_feeds = [
            "[https://news.google.com/rss/search?q=Biotech+OR+%22FDA+approval%22+OR+%22clinical+trials%22&hl=en-US&gl=US&ceid=US:en](https://news.google.com/rss/search?q=Biotech+OR+%22FDA+approval%22+OR+%22clinical+trials%22&hl=en-US&gl=US&ceid=US:en)"
        ]
        patent_feeds = [
            "[https://news.google.com/rss/search?q=Patent+OR+%22tech+innovation%22+OR+%22future+tech%22&hl=en-US&gl=US&ceid=US:en](https://news.google.com/rss/search?q=Patent+OR+%22tech+innovation%22+OR+%22future+tech%22&hl=en-US&gl=US&ceid=US:en)"
        ]
        
        bio_articles = get_articles_from_feeds(bio_feeds, history)
        patent_articles = get_articles_from_feeds(patent_feeds, history)
        
        bio_top = select_top_topics(bio_articles, count=1, category_name="바이오(BIO)")
        patent_top = select_top_topics(patent_articles, count=1, category_name="특허(PATENT)")
        
        selected_news.extend(bio_top)
        selected_news.extend(patent_top)

    if not selected_news:
        print(">>> 조건에 맞는 새로운 뉴스가 없어 종료합니다.")
        return

    # 3. 글 쓰기 및 메타데이터 추출
    raw_html, meta_data = generate_blog_content(selected_news)
    
    # 4. 이미지 넣기 (추출된 키워드 사용)
    final_html = add_images_to_html(raw_html, meta_data.get("keywords", []))
    
    # 5. 메일 보내기 (미리보기 포함)
    mail_subject = meta_data.get("mail_subject", "[카테고리 분석] 스포(spo)의 최신 딥다이브 리포트")
    send_email(mail_subject, final_html)
    
    # 6. 히스토리 저장
    iso_now = datetime.now().isoformat()
    for news in selected_news:
        history[news['link']] = iso_now
    save_history(history)
    print("========== 작업 완료 ==========\n")

if __name__ == "__main__":
    main()
