# main.py
from fastapi import FastAPI
from typing import List
import boto3
from datetime import datetime
from crawler import run_all_crawlers
from pydantic import BaseModel

app = FastAPI()

# DynamoDB 연결
dynamodb = boto3.resource("dynamodb", region_name="us-east-2")   # 오하이오
table = dynamodb.Table("gwnu-ht-05-scholarship")

@app.get("/")
def root():
    return {"message": "FastAPI running on EC2"}

# -----------------------------
# 🔥 /crawl 호출 → 크롤링 + DynamoDB 저장
# -----------------------------
@app.get("/crawl")
def crawl_and_save():
    data = run_all_crawlers()
    inserted = 0

    for _, items in data.items():
        for item in items:

            url = item.get("url")

            # 🔥 url이 없으면 DynamoDB 저장 불가 → 스킵
            if not url or url == "None":
                print(f"⚠️ URL 없음 → 저장 skipped: {item}")
                continue

            table.put_item(
                Item={
                    "url": url,    # PK
                    "title": item.get("title"),
                    "date": item.get("date"),
                    "content": item.get("content"),

                    "type": item.get("type"),
                    "major": item.get("major"),
                    "grade": item.get("grade"),
                    "price": item.get("price"),
                    "start_at": item.get("start_at"),
                    "end_at": item.get("end_at"),
                    "etc": item.get("etc"),

                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            )

            inserted += 1

    return {"status": "ok", "inserted": inserted}




# -----------------------------
# 서버 헬스체크 
# -----------------------------
@app.get("/api/health")
def health():
    return {"status": "ok"}


# -----------------------------
# 다이나모 디비 전체 item 보내기 
# -----------------------------
@app.get("/api/list")
def get_all_items():
    try:
        # DynamoDB 전체 스캔
        response = table.scan()
        items = response.get("Items", [])

        return {
            "count": len(items),
            "items": items
        }

    except Exception as e:
        return {"error": str(e)}



# -----------------------------
# 이력 폼 받기 (Recommend API)
# -----------------------------
class ResumeRequest(BaseModel):
    major: str
    grade: str
    certificates: List[str] = []


@app.post("/api/resumes")
async def submit_resume(req: ResumeRequest):

    # DynamoDB 전체 조회
    response = table.scan()
    items = response.get("Items", [])

    recommended = []

    for item in items:
        
        # 1) 전공 정확 매칭 (null 제거)
        if item.get("major") != req.major:
            continue

        # 2) 학년 정확 매칭 (null 제거)
        if item.get("grade") != req.grade:
            continue

        # 3) 자격증 매칭 (하나라도 맞으면 통과)
        item_certificates = item.get("certificates", [])
        if item_certificates:
            if not any(cert in req.certificates for cert in item_certificates):
                continue

        # =====================
        # 통과한 항목만 추천 목록 추가
        # =====================
        recommended.append(item)

    return {
        "count": len(recommended),
        "results": recommended
    }
