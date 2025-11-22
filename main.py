# main.py
from fastapi import FastAPI, HTTPException
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
# /crawl 호출 → 크롤링 + DynamoDB 저장
# -> 6시간마다 돌리도록 추후에  
# -----------------------------
def get_next_id():
    response = table.update_item(
        Key={"counter": "main"},
        UpdateExpression="SET current_id = current_id + :inc",
        ExpressionAttributeValues={":inc": 1},
        ReturnValues="UPDATED_NEW"
    )
    return int(response["Attributes"]["current_id"])

@app.get("/crawl")
def crawl_and_save():
    data = run_all_crawlers()
    inserted = 0

    for _, items in data.items():
        for item in items:
            
            new_id = get_next_id()    # 🔥 숫자 ID 발급
            
            table.put_item(
                Item={
                    "id": new_id,             # 🔥 숫자 PK
                    "url": item.get("url"),
                    "title": item.get("title"),
                    "type": item.get("type"),
                    "major": item.get("major"),
                    "grade": item.get("grade"),
                    "price": item.get("price"),
                    "start_at": item.get("start_at"),
                    "end_at": item.get("end_at"),
                    "content": item.get("content"),
                    "etc": item.get("etc"),
                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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
def get_all():
    res = table.scan()
    return res.get("Items", [])


# -----------------------------
# 이력 폼 받기 (Recommend API)
# -----------------------------
class ResumeRequest(BaseModel):
    major: str
    grade: str
    certificates: List[str] = []


@app.post("/api/resumes")
async def submit_resume(req: ResumeRequest):
    response = table.scan()
    items = response.get("Items", [])

    recommended = []

    for item in items:

        match = False  # ← 최소 하나라도 맞으면 True

        # --- 전공 OR 조건 ---
        item_major = item.get("major")
        if item_major and item_major == req.major:
            match = True

        # --- 학년 OR 조건 ---
        item_grade = item.get("grade")
        if item_grade and item_grade == req.grade:
            match = True

        # --- 자격증 OR 조건 ---
        item_certs = item.get("certificates", [])
        if item_certs:
            if any(c in req.certificates for c in item_certs):
                match = True

        # --- 하나도 맞지 않으면 제외 ---
        if not match:
            continue

        recommended.append(item)

    return {
        "count": len(recommended),
        "results": recommended
    }



# ----------------------------------
# 1) 전체 장학금 목록
# ----------------------------------
@app.get("/api/scholarships")
def get_scholarship_list(category: str = "all", search: str = ""):
    # DynamoDB 스캔
    response = table.scan()
    items = response.get("Items", [])

    # 검색 필터
    if search:
        items = [i for i in items if search.lower() in (i.get("title") or "").lower()]

    # category 필터
    # (너가 직접 type 필드를 나중에 넣으면 type 으로 필터)
    if category != "all":
        items = [i for i in items if i.get("type") == category]

    return {"count": len(items), "items": items}


# ----------------------------------
# 2) 장학금 상세 조회
# ----------------------------------
@app.get("/api/scholarships/{id}")
def get_detail(id: int):
    res = table.get_item(Key={"id": id})
    item = res.get("Item")

    if not item:
        raise HTTPException(404, "Not found")

    return item

