# app/core/logger.py
import logging
import os
from datetime import datetime
from typing import Any

# 1. 로그 디렉토리 생성 (없으면 생성)
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# 2. 로그 파일 경로 설정 (날짜별 분리)
log_filename = f"agent_flow_{datetime.now().strftime('%Y%m%d')}.log"
log_path = os.path.join(LOG_DIR, log_filename)

# 3. 로거 초기화
logger = logging.getLogger("agent_flow")
logger.setLevel(logging.INFO)

# 기존 핸들러 제거 (중복 로깅 방지)
if logger.hasHandlers():
    logger.handlers.clear()

# 4. 파일 핸들러 설정 (모든 로그를 파일에 저장)
file_handler = logging.FileHandler(log_path, encoding="utf-8")
file_formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s"
)
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# 5. 콘솔 핸들러 설정 (실시간 확인용)
console_handler = logging.StreamHandler()
console_formatter = logging.Formatter("%(message)s")  # 콘솔은 깔끔하게 메시지만 출력
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)


def log_agent_step(
    agent_name: str,
    step_description: str,
    data: Any = None
):
    """
    에이전트의 특정 단계 실행을 정해진 포맷으로 로깅합니다.
    Args:
        agent_name: 실행 중인 에이전트/노드 이름 (예: 'InfoExtractAgent')
        step_description: 수행 내용 요약
        data: (선택) 함께 기록할 추가 데이터 (JSON, 텍스트 등)
    """
    message = f"[{agent_name}] {step_description}"
    if data:
        message += f"\nData: {data}"

    logger.info(message)
    logger.info("-" * 50)  # 가독성을 위한 구분선
