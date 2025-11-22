# main.py
from fastapi import FastAPI
import boto3
from boto3.dynamodb.conditions import Key
from crawler_logic import run_all_crawlers
from datetime import datetime

app = FastAPI()

dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-2")
table = dynamodb.Table("gwnu-ht-05-scholarship")

@app.get("/")
def root():
    return {"message": "FastAPI running"}



# -----------------------------
# 🔥 특정 URL 호출 시 크롤링 실행
# -----------------------------
@app.get("/crawl")
def crawl_and_save():
    data = run_all_crawlers()

    inserted = 0

    for _, items in data.items():
        for item in items:
            table.put_item(
                Item={
                    "url": item.get("url"),   # PK
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
            inserted += 1

    return {"status": "ok", "inserted": inserted}
