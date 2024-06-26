import re
import sqlite3
from bs4 import BeautifulSoup
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404
from .models import News
# from django.conf import settings
import requests
from typing import List
from konlpy.tag import Okt
from textrankr import TextRank
import datetime
from django.db.models import Q
from django.utils import timezone

class OktTonkenizer:
    okt: Okt = Okt()
    def __call__(self, text: str) -> List[str]:
        tokens: List[str] = self.okt.phrases(text)
        return tokens

# 스크래핑 코드
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}

def makeUrlByDate(search, start_date, end_date):
    urls = []
    delta = end_date - start_date
    for i in range(delta.days + 1):
        date = start_date + datetime.timedelta(days=i)
        date_str = date.strftime("%Y%m%d")
        url = f"https://search.naver.com/search.naver?where=news&query={search}&sm=tab_pge&sort=0&photo=0&field=0&reporter_article=&pd=3&ds={date_str}&de={date_str}&docid=&nso=so%3Ar%2Cp%3Afrom{date_str}to{date_str}%2Ca%3A&mynews=0&refresh_start=0&related=0"
        urls.append(url)
    return urls

def articles_crawler(url):
    # html 불러오기
    original_html = requests.get(url, headers=headers)
    html = BeautifulSoup(original_html.text, "html.parser")

    url_naver = html.select("div.group_news > ul.list_news > li div.news_area > div.news_info > div.info_group > a.info")
    article_urls = [u['href'] for u in url_naver]
    return article_urls


def search_news(request):
    if 'kw' in request.GET:
        search = request.GET['kw']
        # now_time = datetime.datetime.now().strftime('%Y-%m-%d %H-%M-%S') # 현재 시각
        now_time = timezone.now()

        # 크롤링할 시작 날짜 입력
        start_date_str = str(request.GET.get('sDate'))
        end_date_str = str(request.GET.get('eDate'))
        if (search == '' or start_date_str == '' or end_date_str == ''):
            return render(request, 'pybo/news_list.html')
        start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d")
        end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d")

        # naver url 생성
        urls = makeUrlByDate(search, start_date, end_date)

        # 뉴스 크롤러 실행
        news_url = []
        for i in urls:
            url = articles_crawler(i)
            news_url.append(url)

        # 제목, 링크, 내용 담을 리스트 생성
        news_url_1 = []

        # 링크 꺼내는 코드
        for i in news_url:
            for j in i:
                news_url_1.append(j)

        # NAVER 뉴스만 남기기
        final_urls = []
        for i in range(len(news_url_1)):
            if "news.naver.com" in news_url_1[i]:
                final_urls.append(news_url_1[i])

        db_lst = [] # DB에 담을 데이터 리스트. 2차원으로 될 것.
        
        # DB에 있는 링크와 겹치면 가져온 데이터의 작업 취소
        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()
        saved_url = []
        for link in final_urls:
            cursor.execute("SELECT * FROM pybo_news WHERE link = ?", (link,)) # 링크 데이터 조회
            result = cursor.fetchall()
            if result:
                saved_url.append(link)
        for link in saved_url:
            final_urls.remove(link) # 현재 저장되어 있는 데이터 삭제
        # 뉴스 내용 크롤링
        if final_urls:
            for i in final_urls:
                # 각 기사 html get
                news = requests.get(i, headers=headers)
                news_html = BeautifulSoup(news.text, "html.parser")

                # 뉴스 제목
                title = news_html.select_one("#ct > div.media_end_head.go_trans > div.media_end_head_title > h2")
                if title == None:
                    title = news_html.select_one("#content > div.end_ct > div > h2")

                # 뉴스 본문
                content = news_html.select("article#dic_area")
                if content == []:
                    content = news_html.select("#articeBody")

                # list합치기
                content = ''.join(str(content))

                # html태그제거 및 텍스트 다듬기
                pattern1 = '<[^>]*>'
                title = re.sub(pattern=pattern1, repl='', string=str(title))
                content = re.sub(pattern=pattern1, repl='', string=content)
                pattern2 = """[\n\n\n\n\n// flash 오류를 우회하기 위한 함수 추가\nfunction _flash_removeCallback() {}"""
                content = content.replace(pattern2, '')

                try:
                    html_date = news_html.select_one("div#ct> div.media_end_head.go_trans > div.media_end_head_info.nv_notrans > div.media_end_head_info_datestamp > div > span")
                    news_date = html_date.attrs['data-date-time']
                except AttributeError:
                    news_date = news_html.select_one("#content > div.end_ct > div > div.article_info > span > em")
                    news_date = re.sub(pattern=pattern1, repl='', string=str(news_date))
                # 날짜 가져오기
                db_lst.append([title, content, now_time, news_date, i]) # DB 리스트에 저장

            # DB 연동
            conn = sqlite3.connect('db.sqlite3')
            cursor = conn.cursor()

            cursor.execute('''CREATE TABLE IF NOT EXISTS pybo_news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                content TEXT NOT NULL,
                create_date DATETIME NOT NULL,
                news_date DATETIME,
                link TEXT NOT NULL,
                summary TEXT
                )''')
            
            cursor.executemany('insert into pybo_news (subject, content, create_date, news_date, link) values (?,?,?,?,?)', db_lst)
            conn.commit()
            conn.close()

        saved_url += final_urls # DB에 저장된 링크 통합
        if len(saved_url) > 0:
            link_conditions = Q(link=saved_url[0])
            for link in saved_url[1:]:
                link_conditions |= Q(link=link)
            search_results = News.objects.filter(link_conditions).order_by('-news_date')
            context = {'news_list' : search_results}
        else:
            context = {'news_list' : []}
        return render(request, 'pybo/news_list.html', context)

def index(request):
    conn = sqlite3.connect('db.sqlite3')
    cursor = conn.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS pybo_news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT NOT NULL,
        content TEXT NOT NULL,
        create_date DATETIME NOT NULL,
        news_date DATETIME,
        link TEXT NOT NULL,
        summary TEXT
        )''')
    conn.close()
    saved_url = []
    try:
        link_conditions = Q(link=saved_url[0])
        for link in saved_url[1:]:
            link_conditions |= Q(link=link)
        search_results = News.objects.filter(link_conditions).order_by('-create_date')
        context = {'news_list' : search_results}
    except:
        context = {'news_list' : []}
    
    # news_list = News.objects.order_by('-create_date')
    # context = {'news_list' : news_list}
    return render(request, 'pybo/news_list.html',context)

def detail(request, news_id):
    news = get_object_or_404(News, pk = news_id)
    context = {'news': news}
    return render(request, 'pybo/news_detail.html', context)

def search_dict(request): # 사전 검색 api
    query = request.GET.get('kw')
    if query:
        api_key = ''
        response = requests.get(f'https://stdict.korean.go.kr/api/search.do?certkey_no=6592&key={api_key}&type_search=search&req_type=json&q={query}')
        if response.status_code == 200:
            data = response.json()
            means_lst = []
            for i in data['channel']['item']:
                means_lst.append(i['sense']['definition'])
            # print(data['channel']['item'][0]['sense']['definition']) # 실제로 쓰일 데이터
            meaning = means_lst
        else:
            meaning = '뜻을 찾을 수 없습니다.'
    else:
        meaning = '검색어를 입력하세요.'

    return JsonResponse({'meaning': meaning})

def summary(request, news_id): # 요약 함수
    news = News.objects.get(id=news_id)
    if news.summary:
        summaries = news.summary
        summaries = summaries.split(',')
        summaries[0] = summaries[0][1:] # 괄호 제거
        summaries[2] = summaries[2][:-1]
    else:
        mytokenizer: OktTonkenizer = OktTonkenizer()
        textrank: TextRank = TextRank(mytokenizer)
        k: int = 3
        summaries: List[str] = textrank.summarize(news.content, k, verbose=False)
        # for summary in summaries:
        #     print(summary)
        news.summary = summaries
        news.save()
    return render(request, 'summary_news.html', {'content': summaries})

    
#추가
# def search(request):
#     query = request.GET.get('q')
#     if query:
#         response = requests.get('https://newsapi.org/v2/everything', params={'q': query, 'apiKey': settings.NEWS_API_KEY})
#         articles = response.json().get('articles', [])
#         for article in articles:
#             News.objects.get_or_create(
#                 title=article['title'],
#                 content=article['content'],
#                 publication_date=article['publishedAt'][:10],
#                 summary=article['description'],
#                 summary_link=article['url']
#             )
#         articles = News.objects.filter(title__icontains=query)
#         return render(request, 'news/search_results.html', {'articles': articles, 'query': query})
#     return render(request, 'news/search_results.html')