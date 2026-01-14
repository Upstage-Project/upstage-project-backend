import os
import json
import zipfile
import io
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional
import requests  # pip install requests 필요


class TickerResolver:
    """
    DART에서 제공하는 고유번호(CORPCODE) XML 파일을 다운로드 및 파싱하여,
    기업명/종목코드를 입력받아 정확한 식별자(Corp Code)를 반환하는 클래스입니다.
    """

    MASTER_FILE_NAME = "company_master.json"

    def __init__(self, data_path: Optional[str] = None):
        # 데이터 저장 경로 설정 (없으면 현재 디렉토리)
        self.data_path = data_path or os.path.join(os.getcwd(), self.MASTER_FILE_NAME)

        self._loaded = False

        # 검색 인덱스 (메모리 로딩용)
        self.ticker_index: Dict[str, Dict[str, Any]] = {}
        self.name_index: Dict[str, Dict[str, Any]] = {}

    def ensure_loaded(self):
        """데이터가 로드되지 않았다면 로드합니다 (없으면 다운로드 시도)."""
        if self._loaded:
            return

        # 1. 로컬에 마스터 파일이 없으면 DART에서 다운로드
        if not os.path.exists(self.data_path):
            print("[TickerResolver] Master file not found. Downloading from DART...")
            success = self._download_and_parse_dart_master()
            if not success:
                print("[TickerResolver] Failed to download master data. Using empty index.")
                self._loaded = True
                return

        # 2. 파일 로드
        self._load_from_json_file()
        self._loaded = True

    def _download_and_parse_dart_master(self) -> bool:
        """
        DART Open API (corpCode.xml)를 호출하여 전체 기업 목록을 가져옵니다.
        """
        api_key = os.getenv("DART_API_KEY")
        if not api_key:
            print("[TickerResolver] Error: DART_API_KEY is missing in environment variables.")
            return False

        url = "https://opendart.fss.or.kr/api/corpCode.xml"
        params = {"crtfc_key": api_key}

        try:
            # 1. API 요청 (ZIP 파일 수신)
            resp = requests.get(url, params=params, stream=True)
            resp.raise_for_status()

            # 2. ZIP 메모리 해제 및 XML 파싱
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                # 압축 파일 내의 XML 파일명 찾기 (보통 CORPCODE.xml)
                xml_filename = zf.namelist()[0]
                with zf.open(xml_filename) as xml_file:
                    tree = ET.parse(xml_file)
                    root = tree.getroot()

            # 3. 데이터 추출 및 구조화
            company_list = []
            # <result><list>...</list><list>...</list></result> 구조
            for item in root.findall("list"):
                corp_code = item.findtext("corp_code")
                corp_name = item.findtext("corp_name")
                stock_code = item.findtext("stock_code")

                # stock_code가 있는 경우(상장사)와 없는 경우(비상장) 모두 저장하되,
                # 검색 효율을 위해 stock_code 공백 제거
                stock_code = stock_code.strip() if stock_code else None
                corp_name = corp_name.strip() if corp_name else ""

                if not corp_code:
                    continue

                entry = {
                    "company_name": corp_name,
                    "corp_code": corp_code,
                    "stock_code": stock_code,  # "005930" or None
                    "ticker": stock_code  # 호환성 필드
                }
                company_list.append(entry)

            print(f"[TickerResolver] Parsed {len(company_list)} companies from DART.")

            # 4. JSON 파일로 저장 (캐싱)
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(company_list, f, ensure_ascii=False, indent=None)  # 용량 절약 위해 indent 제거

            return True

        except Exception as e:
            print(f"[TickerResolver] Error downloading/parsing DART data: {e}")
            return False

    def _load_from_json_file(self):
        """로컬 JSON 파일에서 데이터를 메모리로 로드하고 인덱싱합니다."""
        print(f"[TickerResolver] Loading index from {self.data_path}...")
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for item in data:
                name = item.get("company_name")
                ticker = item.get("stock_code")

                # 결과 포맷 통일
                info = {
                    "status": "success",
                    "company_name": name,
                    "ticker": ticker,
                    "stock_code": ticker,
                    "corp_code": item.get("corp_code")
                }

                # 1. 이름 인덱싱
                if name:
                    self.name_index[name] = info
                    # 검색 편의: 공백제거+소문자 (예: "삼성 전자" -> "삼성전자")
                    self.name_index[name.replace(" ", "").lower()] = info

                # 2. 티커 인덱싱 (상장사의 경우)
                if ticker and ticker.strip():
                    self.ticker_index[ticker] = info

            print(f"[TickerResolver] Loaded {len(data)} companies into memory.")

        except Exception as e:
            print(f"[TickerResolver] Failed to load JSON file: {e}")

    def resolve(self, user_input: str) -> Dict[str, Any]:
        """
        사용자 입력(이름 또는 코드)을 바탕으로 기업 정보를 반환합니다.
        """
        self.ensure_loaded()

        query = str(user_input).strip()
        if not query:
            return {"status": "error", "message": "Empty input"}

        # 1. 숫자 6자리면 Ticker로 우선 검색
        if query.isdigit() and len(query) == 6:
            if query in self.ticker_index:
                return self.ticker_index[query]

        # 2. 이름으로 정확히 검색
        if query in self.name_index:
            return self.name_index[query]

        # 3. 정규화된 이름(공백 제거)으로 검색
        norm_query = query.replace(" ", "").lower()
        if norm_query in self.name_index:
            return self.name_index[norm_query]

        # 4. 검색 실패 (Fallback)
        return {
            "status": "not_found",
            "message": f"Could not find company: '{user_input}'",
            "company_name": user_input,
            "ticker": query if query.isdigit() else None,
            "stock_code": query if query.isdigit() else None,
            "corp_code": None
        }