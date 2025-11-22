import json
from datetime import datetime
from PyPDF2 import PdfReader
from openai import OpenAI

# ===========================
# 1. Upstage/Solar 설정
# ===========================
UPSTAGE_API_KEY = "up_4SGKCusvviP1TdH8rxetRMwlMhxMp"

client = OpenAI(
    api_key=UPSTAGE_API_KEY,
    base_url="https://api.upstage.ai/v1",
)


# ===========================
# 2. PDF → 텍스트 추출
# ===========================
def extract_text_from_pdf(pdf_path: str) -> str:
    """
    단일 PDF 파일 경로를 받아서,
    모든 페이지의 텍스트를 '\n\n'로 이어붙여 반환.
    """
    reader = PdfReader(pdf_path)
    texts = []

    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        texts.append(t)

    return "\n\n".join(texts).strip()


# ===========================
# 3. 프롬프트 생성 (졸업년도 + 분야 추가)
# ===========================
def build_resume_prompt(text: str) -> str:
    prompt = f"""다음 텍스트에서 학생 정보를 추출하여 정확한 JSON 형식으로만 답변해주세요.
다른 설명 없이 JSON만 출력하세요.

텍스트:
{text}

추출할 정보:
- name: 이름
- major: 학과 (전공)
- grade: 학년 (예: "3학년")
- graduation_year: 졸업년도 (예정 포함, 예: "2027", 없으면 "")
- certificates: 자격증 (여러 개면 쉼표로 구분, 없으면 빈 문자열)
- field: 주요 분야 (프로젝트/경험을 보고 한 단어 또는 짧은 구로 요약. 예: "백엔드 개발", "프론트엔드", "데이터 분석", "AI/컴퓨터 비전", "모름")

규칙:
1. 텍스트에 명시된 졸업년도(또는 졸업예정년도)를 graduation_year에 "YYYY" 형태로 넣으세요. 없으면 "".
2. grade는 텍스트에 명시된 학년이 있으면 그대로 사용하세요. 없으면 ""로 두세요.
   (학년 계산은 모델이 하지 말고, graduation_year만 정확히 추출하세요.)
3. field는 이력서 속 프로젝트/경험/기술스택을 보고 가장 대표적인 분야를 한국어로 짧게 요약하세요.
   예시: "백엔드 개발", "프론트엔드", "데이터 분석", "AI/컴퓨터 비전", "모바일 앱", "임베디드", 등.
   정보가 부족하면 "모름" 또는 "".
4. 정보가 전혀 없거나 애매하면 해당 필드는 ""로 두세요.

JSON 형식 예시:
{{"name":"홍길동","major":"컴퓨터공학과","grade":"3학년","graduation_year":"2027","certificates":"정보처리기사, AWS 자격증","field":"백엔드 개발"}}

만약 정보가 없다면 빈 문자열("")로 표시하세요."""
    return prompt


# ===========================
# 4. JSON 클리너
# ===========================
def clean_json_text(text: str) -> str:
    """
    LLM이 ```json ... ``` 같은 형식으로 감싸서 줄 때,
    JSON 본문만 잘라내는 유틸 함수.
    """
    text = text.strip()

    # ```json ... ``` 형식 처리
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 3:
            body = parts[1]
        else:
            body = text.replace("```", "")
        body = body.lstrip("json").strip()
        text = body

    # 첫 '{' ~ 마지막 '}' 구간만 추출
    if "{" in text and "}" in text:
        start = text.find("{")
        end = text.rfind("}") + 1
        text = text[start:end]

    return text.strip()


# ===========================
# 5. 졸업년도 → 학년 추정 함수
# ===========================
def infer_grade_from_graduation_year(graduation_year_str: str) -> str:
    """
    졸업년도(YYYY)를 받아서 4년제 기준으로 현재 학년을 추정.
    - 단순 규칙: 입학년도 = 졸업년도 - 4
      grade = 현재연도 - 입학년도 + 1 = 현재연도 - 졸업년도 + 5
    - 결과가 1~4 범위를 벗어나면 "" 반환.
    """
    if not graduation_year_str:
        return ""

    try:
        grad_year = int(graduation_year_str)
    except ValueError:
        return ""

    current_year = datetime.now().year
    grade_num = current_year - grad_year + 5  # 4년제 가정

    if 1 <= grade_num <= 4:
        return f"{grade_num}학년"
    else:
        return ""


# ===========================
# 6. 텍스트 이력서 파싱 + 학년 추정 + 분야
# ===========================
def parse_resume_text(text: str) -> dict:
    """
    이력서 텍스트에서:
    name, major, grade, graduation_year, certificates, field 를 추출.
    grade는 graduation_year로 한 번 더 보정.
    """
    prompt = build_resume_prompt(text)

    resp = client.chat.completions.create(
        model="solar-pro2",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.0,
        max_tokens=512,
    )

    raw = resp.choices[0].message.content or ""
    cleaned = clean_json_text(raw)

    # 기본 스키마
    default_result = {
        "name": "",
        "major": "",
        "grade": "",
        "graduation_year": "",
        "certificates": "",
        "field": ""
    }

    try:
        data = json.loads(cleaned)
    except Exception as e:
        print("⚠️ 이력서 JSON 파싱 실패:", e)
        print("----- 원문 응답 -----")
        print(raw)
        print("--------------------")
        return default_result

    result = {
        "name": data.get("name", ""),
        "major": data.get("major", ""),
        "grade": data.get("grade", ""),
        "graduation_year": data.get("graduation_year", ""),
        "certificates": data.get("certificates", ""),
        "field": data.get("field", ""),
    }

    # 🔥 졸업년도 기반으로 grade 보정
    inferred_grade = infer_grade_from_graduation_year(result["graduation_year"])
    if inferred_grade:
        # 졸업년도로 계산된 학년이 있으면 이 값으로 덮어쓰기
        result["grade"] = inferred_grade

    return result


# ===========================
# 7. PDF 이력서 파싱 (최종 함수)
# ===========================
def parse_resume_pdf(pdf_path: str) -> dict:
    """
    PDF 이력서 파일 경로를 받아서
    {name, major, grade, graduation_year, certificates, field} dict 반환.
    """
    text = extract_text_from_pdf(pdf_path)
    if not text.strip():
        print("⚠️ PDF에서 텍스트를 추출하지 못했습니다.")
        return {
            "name": "",
            "major": "",
            "grade": "",
            "graduation_year": "",
            "certificates": "",
            "field": ""
        }

    return parse_resume_text(text)


# ===========================
# 8. 사용 예시
# ===========================
if __name__ == "__main__":
    pdf_path = "/content/박지완 이력서.pdf"  # 네 PDF 경로로 변경
    info = parse_resume_pdf(pdf_path)
    print(json.dumps(info, ensure_ascii=False, indent=2))
