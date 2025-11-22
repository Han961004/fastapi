# crawler.py

import boto3
from datetime import datetime
from crawler_logic import run_all_crawlers

dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-2")
table = dynamodb.Table("Notices")

def save_to_dynamodb(data):
    for _, items in data.items():
        for item in items:

            # 너가 원하는 필드 스키마로 변환
            table.put_item(
                Item={
                    "url": item.get("url"),     # PK
                    "title": item.get("title"),
                    "type": item.get("type"),
                    "major": item.get("major"),
                    "grade": item.get("grade"),
                    "price": item.get("price"),
                    "start_at": item.get("start_at"),
                    "end_at": item.get("end_at"),
                    "content": item.get("content"),
                    "etc": item.get("etc"),
                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            )

    print("✅ DynamoDB 저장 완료!")

if __name__ == "__main__":
    print("🔍 크롤링 시작…")
    data = run_all_crawlers()
    save_to_dynamodb(data)