# app/agents/ticker_resolver.py
from typing import Dict, Any, Optional


class TickerResolver:
    """
    회사명/티커/종목코드를 표준화해서 반환하는 Resolver.
    지금은 "DB만 구현" 단계이므로 임시로 입력을 그대로 company_name으로 돌려준다.
    나중에 종목 마스터(DB/CSV/API) 붙이면 resolve()만 확장하면 됨.
    """

    _loaded: bool = False

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        # TODO: 필요 시 종목 마스터 로드 로직 추가
        self._loaded = True

    def resolve(self, user_input: str) -> Dict[str, Any]:
        q = (user_input or "").strip()
        if not q:
            return {"status": "error", "message": "empty input"}

        # ✅ 임시 구현: 입력을 회사명으로 간주
        # 반환 키는 info_collector.py가 기대하는 형태로 맞춤
        return {
            "status": "success",
            "company_name": q,
            "stock_code": None,
            "corp_code": None,
        }
