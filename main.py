from fastapi import FastAPI
import json
import os

app = FastAPI()

FILE_PATH = "latest.json"  # 로컬 파일에서 데이터 로드

@app.get("/")
def root():
    return {"message": "FastAPI is running on EC2"}

@app.get("/data")
def get_data():
    if not os.path.exists(FILE_PATH):
        return {"error": "latest.json not found. Run your crawler first."}

    with open(FILE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data
