# main.py
from fastapi import FastAPI, HTTPException, UploadFile, File
from typing import List, Dict
import boto3
from datetime import datetime
import time
from crawler import run_all_crawlers
from pydantic import BaseModel
from pdfcrawl import *
import io


app = FastAPI()

# DynamoDB 연결
dynamodb = boto3.resource("dynamodb", region_name="us-east-2")  # 오하이오
table = dynamodb.Table("gwnu-ht-05-scholarship")


@app.get("/")
def root():
    return {"message": "FastAPI running on EC2"}


# ---------------------------------------------------------
# 🔥 고정 — ID 자동 생성 (충돌 없음, 초고속)
# ---------------------------------------------------------
def generate_id():
    return int(time.time() * 1000)   # 밀리초 기반 PK


# ---------------------------------------------------------
# 🔥 /crawl → 크롤링 + DynamoDB 저장
# ---------------------------------------------------------
@app.get("/crawl")
def crawl_and_save():
    data = run_all_crawlers()
    inserted = 0

    for _, items in data.items():
        for item in items:

            new_id = generate_id()  # PK 생성

            table.put_item(
                Item={
                    "id": new_id,
                    "board": item.get("board"),
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
                    "images": item.get("images", []),
                    "summary": item.get("summary"),
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            inserted += 1

    return {"status": "ok", "inserted": inserted}



# ---------------------------------------------------------
# 헬스 체크
# ---------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok"}



# ---------------------------------------------------------
# 전체 목록 조회
# ---------------------------------------------------------
@app.get("/api/list")
def get_all():
    res = table.scan()
    return res.get("Items", [])



# ---------------------------------------------------------
# 이력서 기반 추천 API
# ---------------------------------------------------------
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
        match = False

        # 전공
        if item.get("major") and item["major"] == req.major:
            match = True

        # 학년
        if item.get("grade") and item["grade"] == req.grade:
            match = True

        # 자격증
        item_certs = item.get("certificates", [])
        if item_certs and any(c in req.certificates for c in item_certs):
            match = True

        if match:
            recommended.append(item)

    return {"count": len(recommended), "results": recommended}



# ---------------------------------------------------------
# 장학금 전체 목록
# ---------------------------------------------------------
@app.get("/api/scholarships")
def get_scholarship_list(category: str = "all", search: str = ""):

    response = table.scan()
    items = response.get("Items", [])

    if search:
        items = [i for i in items if search.lower() in (i.get("title") or "").lower()]

    if category != "all":
        items = [i for i in items if i.get("type") == category]

    return {"count": len(items), "items": items}



# ---------------------------------------------------------
# 상세 정보
# ---------------------------------------------------------
@app.get("/api/scholarships/{id}")
def get_detail(id: int):
    res = table.get_item(Key={"id": id})
    item = res.get("Item")

    if not item:
        raise HTTPException(404, "Not found")

    return item




# -----------------------------
# 🔥 ID 자동 증가 함수
# -----------------------------
def get_next_id():
    # DynamoDB 전체 스캔해서 최대 id 찾기
    response = table.scan(ProjectionExpression="id")
    items = response.get("Items", [])

    if not items:
        return 1  # 첫 ID

    max_id = max(int(item["id"]) for item in items)
    return max_id + 1


@app.post("/upload-json")
def upload_json(data: List[Dict]):
    inserted = 0

    for item in data:
        # 새 ID 생성 (max+1)
        new_id = get_next_id()

        item["id"] = new_id
        item["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        table.put_item(Item=item)
        inserted += 1

    return {"status": "ok", "inserted": inserted}



# -------------------------------
# PDF 파일 업로드 처리
# -------------------------------
@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    # 파일을 메모리에서 바로 읽기
    file_content = await file.read()

    # 메모리에서 PDF 처리
    extracted_text = extract_text_from_pdf_memory(file_content)
    
    if not extracted_text.strip():
        return {"status": "fail", "message": "PDF에서 텍스트를 추출할 수 없습니다."}

    # 2. 텍스트에서 이력서 정보 추출
    resume_data = parse_resume_text(extracted_text)

    # 3. 이력서 정보 출력
    print(f"📌 추출된 이력서 데이터: {resume_data}")

    # 4. 이력서 기반으로 장학금 필터링
    filtered_scholarships = await filter_scholarships(resume_data)

    return {"resume_data": resume_data, "filtered_scholarships": filtered_scholarships}


def extract_text_from_pdf_memory(file_content: bytes) -> str:
    """
    메모리에서 PDF 파일을 읽고 텍스트 추출
    """
    from PyPDF2 import PdfReader

    # 메모리에서 PDF 파일 읽기
    reader = PdfReader(io.BytesIO(file_content))
    texts = []

    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        texts.append(t)

    return "\n\n".join(texts).strip()



@app.post("/api/filter-scholarships")
async def filter_scholarships(req: ResumeRequest):
    """
    이력서 정보에 맞는 장학금을 필터링하여 반환합니다.
    이력서에서 전공, 학년, 자격증 정보를 바탕으로 장학금 목록을 반환합니다.
    """
    # DynamoDB에서 모든 장학금 항목을 가져옵니다.
    response = table.scan()
    items = response.get("Items", [])

    recommended = []

    # 필터링 조건: major, grade, certificates
    for item in items:
        match = False

        # 전공 필터링
        if req.major and item.get("major") == req.major:
            match = True
        
        # 학년 필터링
        if req.grade and item.get("grade") == req.grade:
            match = True
        
        # 자격증 필터링
        item_certs = item.get("certificates", [])
        if req.certificates:
            if any(cert in item_certs for cert in req.certificates):
                match = True

        # 조건에 맞는 장학금 항목을 recommended 목록에 추가
        if match:
            recommended.append(item)

    # 필터링된 장학금 항목 반환
    return {"count": len(recommended), "results": recommended}
