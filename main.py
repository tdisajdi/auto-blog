import os
import datetime
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

# --- 1. 뉴스 데이터 수집 ---
def get_tech_news():
    print(">>> 테크 뉴스 수집 중...")
    # 더 버지(The Verge)의 최신 기사 가져오기
    feed = feedparser.parse("https://www.theverge.com/rss/index.xml")
    if feed.entries:
        entry = feed.entries[0] # 가장 최신 기사 1개
        return {"title": entry.title, "link": entry.link, "summary": entry.summary}
    return None

# --- 2. 블로그 원고 작성 (Gemini) ---
def generate_blog_content(news_data):
    print(f">>> Gemini가 글을 쓰는 중: {news_data['title']}")
    model = genai.GenerativeModel('gemini-3-flash-preview')
    
    prompt = f"""
    너는 IT 전문 블로거 '스포(spo)'야. 아래 뉴스 내용을 바탕으로 티스토리 블로그에 올릴 포스팅을 HTML 형식으로 작성해줘.
    
    [뉴스 정보]
    제목: {news_data['title']}
    내용 요약: {news_data['summary']}
    링크: {news_data['link']}
    
    [작성 조건]
    1. 글 제목은 클릭을 유도하도록 매력적으로 지어줘.
    2. 서론은 "안녕하세요! 미래를 스포일러하는 스포(spo)입니다."로 시작할 것.
    3. 본론은 전문적이면서도 쉽게 설명하고, <h2>, <p>, <ul> 태그를 적절히 사용해.
    4. 글 중간에 이미지가 들어갈 위치에 딱 2군데만 [IMAGE_PLACEHOLDER] 라고 표시해줘.
    5. 결론에는 "더 많은 IT 소식이 궁금하다면 구독해주세요!"로 마무리해.
    6. 전체 내용은 <html>, <body> 태그 없이 <div> 태그로 감싸서 줘.
    """
    
    response = model.generate_content(prompt)
    return response.text.replace("```html", "").replace("```", "")

# --- 3. 이미지 검색 및 삽입 (Unsplash) ---
def add_images_to_html(html_content, query):
    print(">>> 이미지 검색 및 삽입 중...")
    url = f"https://api.unsplash.com/search/photos?query={query}&per_page=2&orientation=landscape&client_id={UNSPLASH_ACCESS_KEY}"
    
    try:
        response = requests.get(url).json()
        results = response.get('results', [])
        
        # 이미지가 있으면 HTML 내의 [IMAGE_PLACEHOLDER]를 실제 이미지 태그로 교체
        for img_data in results:
            img_url = img_data['urls']['regular']
            img_tag = f'<div style="text-align:center; margin: 20px 0;"><img src="{img_url}" style="width:100%; max-width:600px; border-radius:10px;"></div>'
            html_content = html_content.replace("[IMAGE_PLACEHOLDER]", img_tag, 1)
            
    except Exception as e:
        print(f"이미지 처리 중 오류 발생: {e}")
        # 오류 나면 이미지를 그냥 제거
        html_content = html_content.replace("[IMAGE_PLACEHOLDER]", "")
        
    return html_content

# --- 4. 이메일 발송 ---
def send_email(subject, html_body):
    print(">>> 이메일 전송 시작...")
    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER  # 나 자신에게 보냄
    msg['Subject'] = f"[스포(spo) 원고] {subject}"

    msg.attach(MIMEText(html_body, 'html'))

    try:
        # Gmail SMTP 서버 연결 (SSL 포트 465)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        print(">>> ✅ 이메일 전송 성공!")
    except Exception as e:
        print(f">>> ❌ 이메일 전송 실패: {e}")

# --- 메인 실행 ---
def main():
    # 1. 뉴스 가져오기
    news = get_tech_news()
    if not news:
        print("뉴스를 가져오지 못했습니다.")
        return

    # 2. 글 쓰기
    raw_html = generate_blog_content(news)

    # 3. 이미지 넣기 (검색어는 뉴스 제목 활용)
    final_html = add_images_to_html(raw_html, "technology")

    # 4. 메일 보내기
    send_email(news['title'], final_html)

if __name__ == "__main__":
    main()
