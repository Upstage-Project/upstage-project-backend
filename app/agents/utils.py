# app/agents/utils.py
import json
import re
from datetime import datetime

def get_current_time_str():
    """
    현재 시간을 문자열 포맷(YYYY-MM-DD HH:MM:SS)으로 반환합니다.
    에이전트가 최신 정보를 판단할 때 매우 중요한 요소이며, 로그를 남길 때도 사용합니다.
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clean_and_parse_json(text: str):
    """
    LLM이 반환한 텍스트에서 JSON 부분만 추출하여 파싱합니다.
    마크다운 코드 블록(```json ... ```)이나 앞뒤 공백/텍스트를 제거합니다.
    """
    try:
        # 1. 마크다운 코드 블록(```json ... ```) 안에 있는 내용 추출 시도
        match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            text = match.group(1)
        else:
            # 2. 코드 블록이 없다면, 가장 바깥쪽 중괄호 {} 쌍을 찾음
            match = re.search(r"(\{.*\})", text, re.DOTALL)
            if match:
                text = match.group(1)

        # 추출된 텍스트를 JSON 객체로 변환
        return json.loads(text)

    except Exception:
        # 파싱 실패 시 None 반환 (이후 로직에서 에러 처리 유도)
        return None
