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

def extract_text_from_pdf_bytes(file_bytes: bytes) -> str:
    from PyPDF2 import PdfReader
    import io
    
    reader = PdfReader(io.BytesIO(file_bytes))
    texts = []

    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        texts.append(t)

    return "\n\n".join(texts).strip()


# -------------------------------
# PDF 파일 업로드 처리
# -------------------------------
@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    
    # 1. PDF를 메모리에서 바로 읽기
    pdf_bytes = await file.read()

    # 2. 텍스트 추출
    extracted_text = extract_text_from_pdf_bytes(pdf_bytes)

    resume_data = parse_resume_text(extracted_text)

    print("📌 추출된 이력서 데이터:", resume_data)

    # 🎯 dict → ResumeRequest 로 변환
    req = ResumeRequest(
        major = resume_data.get("major", ""),
        grade = resume_data.get("grade", ""),
        certificates = [c.strip() for c in resume_data.get("certificates", "").split(",")]
    )

    # 🎯 필터 실행
    filtered_scholarships = await filter_scholarships(req)

    return {
        "resume_data": resume_data,
        "recommended": filtered_scholarships
    }


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




def normalize_major(major: str) -> str:
    """
    전공명에서 공백, 대소문자 차이 등을 표준화하여 반환
    예: '컴퓨터 공학', '컴퓨터과학' → '컴퓨터공학'
    """
    if not major:
        return ""
    
    major = major.lower().strip()  # 소문자화하고 앞뒤 공백 제거

    # 전공 표준화 (예시)
    major_map = {
        "컴퓨터공학": ["컴퓨터공학과", "컴퓨터과학", "소프트웨어공학"],
        "정보기술": ["정보기술학", "IT", "정보통신기술"],
        # 여기에 다른 전공도 추가할 수 있음
    }

    for standard, variants in major_map.items():
        if major in [v.lower() for v in variants]:
            return standard

    return major  # 찾을 수 없으면 그대로 반환


@app.post("/api/filter-scholarships")
# major 필터링 로직을 수정하여 'any'도 포함시킬 수 있도록 처리
async def filter_scholarships(req: ResumeRequest):
    response = table.scan()  # DynamoDB에서 장학금 목록을 가져옵니다.
    items = response.get("Items", [])
    
    recommended = []  # 추천된 장학금 목록을 저장할 리스트

    req_major = normalize_major(req.major)  # 전공을 표준화 (예: 공백 제거, 대소문자 통일 등)

    for item in items:
        match = False  # 해당 장학금이 추천될지 여부

        item_major = normalize_major(item.get("major", ""))  # DynamoDB에서 가져온 전공도 표준화

        # major가 "any"일 경우, 전공 필터링을 건너뛰고 매칭
        if req_major == "any":
            match = True
        else:
            # 전공이 명시되어 있고, 이를 비교하여 매칭
            if req_major and item_major:
                if req_major in item_major or item_major in req_major:
                    match = True
            elif req_major == item_major:  # 전공이 정확히 일치하는 경우
                match = True

        # 학년 필터링
        if req.grade and item.get("grade") == req.grade:
            match = True

        # 자격증 필터링
        item_certs = item.get("certificates", [])
        if req.certificates and item_certs:
            if any(c in item_certs for c in req.certificates):
                match = True

        # 필터링된 항목 추가
        if match:
            recommended.append(item)

    return {
        "count": len(recommended),
        "results": recommended
    }

