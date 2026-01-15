import os
import json
import zipfile
import io
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional, List
import requests  # pip install requests 필요


class TickerResolver:
    """
    - DART corpCode.xml 기반 기업 마스터를 다운로드/캐싱하고
    - 사용자 입력(종목명/티커/부분검색/번호선택)으로 기업을 식별합니다.

    ✅ 핵심 개선점
    1) "3" 같은 번호 선택 지원 (직전에 만든 후보 리스트에서 선택)
    2) exact match 실패 시 부분검색으로 candidates 생성
    3) status를 명확히:
       - success
       - need_user_selection (후보 중 선택 필요)
       - need_user_input (입력 자체가 너무 부실/불명확)
       - error
    """

    MASTER_FILE_NAME = "company_master.json"

    def __init__(self, data_path: Optional[str] = None):
        self.data_path = data_path or os.path.join(os.getcwd(), self.MASTER_FILE_NAME)

        self._loaded = False

        # 검색 인덱스
        self.ticker_index: Dict[str, Dict[str, Any]] = {}
        self.name_index: Dict[str, Dict[str, Any]] = {}

        # 원본 리스트(부분검색용)
        self.company_list: List[Dict[str, Any]] = []

    # -----------------------------
    # Load / Cache
    # -----------------------------
    def ensure_loaded(self):
        if self._loaded:
            return

        if not os.path.exists(self.data_path):
            print("[TickerResolver] Master file not found. Downloading from DART...")
            success = self._download_and_parse_dart_master()
            if not success:
                print("[TickerResolver] Failed to download master data. Using empty index.")
                self._loaded = True
                return

        self._load_from_json_file()
        self._loaded = True

    def _download_and_parse_dart_master(self) -> bool:
        api_key = os.getenv("DART_API_KEY")
        if not api_key:
            print("[TickerResolver] Error: DART_API_KEY is missing in environment variables.")
            return False

        url = "https://opendart.fss.or.kr/api/corpCode.xml"
        params = {"crtfc_key": api_key}

        try:
            resp = requests.get(url, params=params, stream=True, timeout=30)
            resp.raise_for_status()

            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                xml_filename = zf.namelist()[0]
                with zf.open(xml_filename) as xml_file:
                    tree = ET.parse(xml_file)
                    root = tree.getroot()

            company_list = []
            for item in root.findall("list"):
                corp_code = item.findtext("corp_code")
                corp_name = item.findtext("corp_name")
                stock_code = item.findtext("stock_code")

                stock_code = stock_code.strip() if stock_code else None
                corp_name = corp_name.strip() if corp_name else ""

                if not corp_code:
                    continue

                entry = {
                    "company_name": corp_name,
                    "corp_code": corp_code,
                    "stock_code": stock_code,
                    "ticker": stock_code,  # 호환 필드
                }
                company_list.append(entry)

            print(f"[TickerResolver] Parsed {len(company_list)} companies from DART.")

            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(company_list, f, ensure_ascii=False, indent=None)

            return True

        except Exception as e:
            print(f"[TickerResolver] Error downloading/parsing DART data: {e}")
            return False

    def _load_from_json_file(self):
        print(f"[TickerResolver] Loading index from {self.data_path}...")
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.company_list = data if isinstance(data, list) else []

            for item in self.company_list:
                name = (item.get("company_name") or "").strip()
                ticker = (item.get("stock_code") or "").strip() or None

                info = {
                    "status": "success",
                    "company_name": name,
                    "ticker": ticker,
                    "stock_code": ticker,
                    "corp_code": item.get("corp_code"),
                }

                if name:
                    # 원문/정규화 키 둘 다 인덱싱
                    self.name_index[name] = info
                    self.name_index[name.replace(" ", "").lower()] = info

                if ticker:
                    self.ticker_index[ticker] = info

            print(f"[TickerResolver] Loaded {len(self.company_list)} companies into memory.")
        except Exception as e:
            print(f"[TickerResolver] Failed to load JSON file: {e}")
            self.company_list = []

    # -----------------------------
    # Utilities
    # -----------------------------
    @staticmethod
    def _norm(s: str) -> str:
        return (s or "").replace(" ", "").strip().lower()

    def _build_candidate(self, item: Dict[str, Any]) -> Dict[str, Any]:
        name = (item.get("company_name") or "").strip()
        ticker = (item.get("stock_code") or "").strip() or None
        return {
            "company_name": name,
            "ticker": ticker,
            "stock_code": ticker,
            "corp_code": item.get("corp_code"),
        }

    def _search_candidates(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        부분검색 후보 생성:
        - 회사명에 query 포함 (정규화 기준)
        - 티커가 query로 시작(사용자가 2~5자리만 입력한 경우)
        """
        nq = self._norm(query)
        if not nq:
            return []

        cands: List[Dict[str, Any]] = []

        # 티커 partial
        if nq.isdigit():
            # 1~5자리 입력이면 티커 prefix로 찾기
            for item in self.company_list:
                t = (item.get("stock_code") or "").strip()
                if t and t.startswith(nq):
                    cands.append(self._build_candidate(item))
                    if len(cands) >= limit:
                        return cands

        # 이름 contains
        for item in self.company_list:
            name = (item.get("company_name") or "").strip()
            if not name:
                continue
            if nq in self._norm(name):
                cands.append(self._build_candidate(item))
                if len(cands) >= limit:
                    break

        # 중복 제거(같은 ticker/name)
        seen = set()
        uniq = []
        for c in cands:
            key = (c.get("ticker"), c.get("company_name"))
            if key in seen:
                continue
            seen.add(key)
            uniq.append(c)
        return uniq[:limit]

    # -----------------------------
    # Public API
    # -----------------------------
    def resolve(
        self,
        user_input: str,
        *,
        last_candidates: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        user_input:
          - "005930" (6자리 티커)
          - "삼성전자" (회사명)
          - "삼성" (부분검색 → 후보 리스트 반환)
          - "3" (후보 리스트에서 3번 선택)

        last_candidates:
          - 직전 턴에 보여준 후보 리스트를 넘겨주면 "3" 선택 가능
        """
        self.ensure_loaded()

        query = str(user_input).strip()
        if not query:
            return {"status": "need_user_input", "message": "빈 입력입니다. 종목명 또는 6자리 종목코드를 입력해줘."}

        # ✅ 0) 번호 선택 처리 ("3")
        if query.isdigit() and len(query) < 6:
            if last_candidates and len(last_candidates) > 0:
                idx = int(query) - 1
                if 0 <= idx < len(last_candidates):
                    pick = last_candidates[idx]
                    # pick에는 company_name/ticker/corp_code가 있어야 함
                    return {
                        "status": "success",
                        "company_name": pick.get("company_name"),
                        "ticker": pick.get("ticker"),
                        "stock_code": pick.get("stock_code") or pick.get("ticker"),
                        "corp_code": pick.get("corp_code"),
                    }
                return {
                    "status": "need_user_selection",
                    "message": f"번호가 범위를 벗어났어. 1~{len(last_candidates)} 중에서 골라줘.",
                    "candidates": last_candidates,
                }

            # 후보가 없는데 "3"만 들어오면 애초에 선택 불가
            return {
                "status": "need_user_input",
                "message": "지금은 후보 목록이 없어서 번호 선택(예: 3)을 할 수 없어. 종목명이나 6자리 종목코드를 입력해줘.",
            }

        # ✅ 1) 6자리 숫자면 ticker 정확히 검색
        if query.isdigit() and len(query) == 6:
            if query in self.ticker_index:
                return self.ticker_index[query]
            # 6자리인데 없으면 not_found(그래도 부분검색은 의미 없음)
            return {
                "status": "not_found",
                "message": f"해당 6자리 종목코드를 찾지 못했어: '{query}'",
                "ticker": query,
                "stock_code": query,
                "corp_code": None,
            }

        # ✅ 2) 회사명 exact
        if query in self.name_index:
            return self.name_index[query]

        # ✅ 3) 회사명 정규화 exact
        norm_query = self._norm(query)
        if norm_query in self.name_index:
            return self.name_index[norm_query]

        # ✅ 4) 부분검색 후보 생성
        candidates = self._search_candidates(query, limit=5)
        if candidates:
            return {
                "status": "need_user_selection",
                "message": "여러 개가 걸렸어. 번호로 선택해줘.",
                "candidates": candidates,
            }

        # ✅ 5) 완전 실패
        return {
            "status": "not_found",
            "message": f"회사를 찾지 못했어: '{user_input}' (정확한 종목명 또는 6자리 종목코드를 입력해줘)",
            "company_name": user_input,
            "ticker": None,
            "stock_code": None,
            "corp_code": None,
        }
