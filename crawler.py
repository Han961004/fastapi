# crawler.py

import json
from datetime import datetime
from crawler_logic import run_all_crawlers

def save_to_file(data):
    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "content": data
    }

    with open("latest.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=4)

    print("✅ 저장 완료 → latest.json")

if __name__ == "__main__":
    print("🔍 크롤링 시작...")
    data = run_all_crawlers()
    save_to_file(data)
