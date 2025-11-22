import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime
import time

# -------------------------------------------------------
# 공통 - 날짜 파싱
# -------------------------------------------------------

def parse_korean_datetime(text):
    if not text:
        return None
    text = text.replace("년", "-").replace("월", "-").replace("일", "")
    text = text.replace("시", ":").replace("분", ":").replace("초", "")
    text = text.strip()
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")


# -------------------------------------------------------
# ① wwwk.kangwon 공지 크롤러
# -------------------------------------------------------

def parse_detail(url):
    print(f"   🔎 상세 요청: {url}")   # 디버깅용 로그 추가
    res = requests.get(url)
    soup = BeautifulSoup(res.text, "html.parser")

    board_tag = soup.select_one(".sub_title h2")
    board = board_tag.get_text(strip=True) if board_tag else "unknown"

    title_tag = soup.select_one("tr.subject td")
    title = title_tag.get_text(strip=True) if title_tag else None

    date_tag = soup.select_one("span.write strong")
    raw_date = date_tag.get_text(strip=True) if date_tag else None
    date = parse_korean_datetime(raw_date) if raw_date else None

    content_tag = soup.select_one("#bbs_ntt_cn_con")
    content = content_tag.get_text("\n", strip=True) if content_tag else None

    return board, title, date, content


def crawl_list(list_url, max_pages=1):
    grouped = {}

    for p in range(1, max_pages + 1):
        url = f"{list_url}&pageIndex={p}"
        print(f"➡️ 목록 요청: {url}")   # 디버깅용 로그 추가

        res = requests.get(url)
        soup = BeautifulSoup(res.text, "html.parser")

        links = soup.select("a[href*='selectBbsNttView']")
        print(f"   ➕ 발견된 상세링크 수: {len(links)}")  # 몇 개 크롤했는지 로그

        for a in links:
            href = a.get("href")

            if "javascript" in href:
                parts = href.split("'")
                ntt_no = parts[1]
                base = list_url.split("selectBbsNttList")[0]
                full = f"{base}selectBbsNttView.do?nttNo={ntt_no}"
            else:
                full = urljoin(list_url, href)

            board, title, date, content = parse_detail(full)

            if board not in grouped:
                grouped[board] = []

            grouped[board].append({
                "url": full,
                "title": title,
                "date": date.strftime("%Y-%m-%d %H:%M:%S") if date else None,
                "content": content
            })

    return grouped


# -------------------------------------------------------
# ② 관광학과
# -------------------------------------------------------

def parse_tourism_detail(url):
    print(f"   🔎 관광 상세: {url}")
    res = requests.get(url)
    soup = BeautifulSoup(res.text, "html.parser")

    board = "관광학과 공지"

    title_box = soup.select_one(".b-title-box")
    if title_box:
        cate = title_box.select_one(".b-cate")
        cate_text = cate.get_text(strip=True) if cate else ""
        title_text = title_box.get_text(" ", strip=True)
        title = f"{title_text}".replace(cate_text, cate_text + " ") if cate else title_text
    else:
        title = None

    date_tag = soup.select_one(".b-date-box span:nth-child(2)")
    raw_date = date_tag.get_text(strip=True) if date_tag else None

    date = None
    if raw_date:
        try:
            date = datetime.strptime(raw_date, "%Y.%m.%d")
        except:
            pass

    content_tag = soup.select_one(".b-content-box")
    content = content_tag.get_text("\n", strip=True) if content_tag else None

    return board, title, date, content


def crawl_tourism_list(list_url, max_pages=1):
    grouped = {}

    for p in range(1, max_pages + 1):
        url = f"{list_url}?article.offset={(p-1)*10}&articleLimit=10"
        print(f"➡️ 관광 목록 요청: {url}")

        res = requests.get(url)
        soup = BeautifulSoup(res.text, "html.parser")

        links = soup.select("a[href*='articleNo']")
        print(f"   ➕ 관광 상세링크 수: {len(links)}")

        for a in links:
            href = a.get("href")
            full = urljoin(list_url, href)

            board, title, date, content = parse_tourism_detail(full)

            if board not in grouped:
                grouped[board] = []

            grouped[board].append({
                "url": full,
                "title": title,
                "date": date.strftime("%Y-%m-%d") if date else None,
                "content": content
            })

    return grouped


# -------------------------------------------------------
# ③ 대학일자리플러스 Job 크롤러
# -------------------------------------------------------

BASE = "https://job.kangwon.ac.kr"

job_headers = {
    "User-Agent": "Mozilla/5.0",
    "accept": "application/json, text/plain, */*",
    "x-auth-mid": "0105010000"
}

def fetch_json(url):
    print(f"   🔎 job API 요청: {url}")
    for _ in range(3):
        res = requests.get(url, headers=job_headers)
        try:
            return res.json()
        except:
            time.sleep(0.3)
    return None


def convert_job_item(raw):
    return {
        "campus": raw.get("cmpsNm"),
        "title": raw.get("ttl"),
        "date": raw.get("inptDt"),
        "content": raw.get("cn")
    }


def get_job_list(category_big, category_mid, page, per_page=9):
    url = f"{BASE}/api/common/ntc-list/{category_big}/{category_mid}/{page}?perPage={per_page}&inqSlctn=00&inqVal="
    data = fetch_json(url)

    if not data or not data.get("response"):
        return [], 0

    resp = data["response"]

    notice_list = resp.get("list") or []
    total_page = resp.get("pagination", {}).get("totPage", 0)

    return notice_list, total_page


def crawl_job_all(category_big="00", category_mid="00", max_pages=3):
    print("➡️ job 전체 크롤링 시작")
    all_items = []

    first_list, total_pages = get_job_list(category_big, category_mid, 1)
    all_items.extend(first_list)

    total_pages = min(total_pages, max_pages)

    for p in range(2, total_pages + 1):
        time.sleep(0.3)
        lst, _ = get_job_list(category_big, category_mid, p)
        all_items.extend(lst)

    return [convert_job_item(i) for i in all_items]


# -------------------------------------------------------
# ④ 전체 통합 크롤링 함수
# -------------------------------------------------------

def run_all_crawlers():
    print("🟦 [CRAWL] run_all_crawlers() 시작")

    result = {}

    # ---- www.kangwon ----
    url_list = [
        "https://wwwk.kangwon.ac.kr/www/selectBbsNttList.do?bbsNo=37&key=1176",
        "https://wwwk.kangwon.ac.kr/www/selectBbsNttList.do?bbsNo=81&key=277",
        "https://wwwk.kangwon.ac.kr/www/selectBbsNttList.do?bbsNo=34&key=232",
        "https://wwwk.kangwon.ac.kr/www/selectBbsNttList.do?bbsNo=117&key=768"
    ]

    for url in url_list:
        for board, items in crawl_list(url, max_pages=3).items():
            result.setdefault(board, []).extend(items)

    # ---- 관광학과 ----
    tourism_url = "https://tourism.kangwon.ac.kr/tourism/community/notice.do"
    for board, items in crawl_tourism_list(tourism_url, max_pages=3).items():
        result.setdefault(board, []).extend(items)

    # ---- Job ----
    job_items = crawl_job_all(max_pages=3)
    result["대학일자리플러스"] = job_items

    print("🟩 [CRAWL] 완료")
    return result
