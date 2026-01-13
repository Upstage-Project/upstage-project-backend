# app/agents/tools.py
from typing import Optional, Dict, Any, List, Literal, Union
import os
import re
import httpx
import html
import json
import hashlib
from datetime import datetime

from bs4 import BeautifulSoup
from langchain.tools import tool
from langchain_core.runnables import RunnableConfig

from app.core.llm import get_solar_chat, get_upstage_embeddings
from app.service.vector_service import VectorService

from sqlalchemy import text

embedding_fn = get_upstage_embeddings()
solar_chat = get_solar_chat()

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"

ReportType = Literal["Q1", "H1", "Q3", "FY"]

REPRT_CODE_MAP = {
    "Q1": "11013",
    "H1": "11012",
    "Q3": "11014",
    "FY": "11011",
}

# HTML 태그와 엔티티를 제거해서 뉴스 제목/요약을 사람이 읽기 좋은 텍스트로 정리
def clean_html(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()

# URL을 SHA256 해시로 변환해 뉴스/기사의 고유 ID 생성
def make_id(url: str) -> str:
    return hashlib.sha256((url or "").encode("utf-8")).hexdigest()

# 단일 뉴스/기사/재무 정보를 VectorDB에 1건 저장
@tool
def add_to_invest_kb(
    content: str,
    config: RunnableConfig,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    print(f"\n[Tool: Add Knowledge] Adding content to KB...")
    print(f" - Content snippet: {content[:100]}...")

    try:
        vector_service: VectorService = config["configurable"].get("vector_service")
        if not vector_service:
            return {"status": "error", "message": "VectorService not found in config"}

        vector_service.add_documents([content], [metadata or {"source": "external"}])

        return {
            "status": "success",
            "message": "Successfully added information to investment knowledge base.",
            "metadata": metadata or {"source": "external"},
        }
    except Exception as e:
        print(f"[Tool: Add Knowledge] Error: {e}")
        return {"status": "error", "message": str(e), "metadata": metadata or {}}

# 여러 뉴스/기사/재무 문서를 한 번의 tool call로 VectorDB에 배치 저장
@tool
def add_many_to_invest_kb(
    contents: List[str],
    config: RunnableConfig,
    metadatas: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    여러 문서를 한 번에 KB(VectorDB)에 저장합니다.
    - 1턴 1툴 규칙에서, 뉴스/기사/재무를 모아 "한 번의 tool call"로 저장하기 위함.
    """
    print(f"\n[Tool: Add Many Knowledge] Adding {len(contents)} docs to KB...")

    try:
        vector_service: VectorService = config["configurable"].get("vector_service")
        if not vector_service:
            return {"status": "error", "message": "VectorService not found in config", "saved": 0}

        # ✅ 빈 문자열/공백 문서 제거 (품질/에러 방지)
        filtered = []
        filtered_meta = []
        if metadatas is None:
            metadatas = [{"source": "external"} for _ in contents]

        if len(metadatas) != len(contents):
            return {
                "status": "error",
                "message": f"metadatas length mismatch: {len(metadatas)} != {len(contents)}",
                "saved": 0,
            }

        for c, m in zip(contents, metadatas):
            c2 = (c or "").strip()
            if not c2:
                continue
            filtered.append(c2)
            filtered_meta.append(m or {"source": "external"})

        if not filtered:
            return {"status": "success", "message": "No valid contents to add.", "saved": 0}

        vector_service.add_documents(filtered, filtered_meta)

        return {
            "status": "success",
            "message": "Successfully added documents to investment knowledge base.",
            "saved": len(filtered),
        }

    except Exception as e:
        print(f"[Tool: Add Many Knowledge] Error: {e}")
        return {"status": "error", "message": str(e), "saved": 0}

# 네이버 뉴스 검색 API를 호출해 원시 뉴스 리스트(dict) 반환
def search_naver_news(topic: str, max_results: int = 20, sort: str = "date") -> List[Dict[str, Any]]:
    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")
    if not client_id:
        raise RuntimeError("NAVER_CLIENT_ID not set")
    if not client_secret:
        raise RuntimeError("NAVER_CLIENT_SECRET not set")

    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    params = {"query": topic, "display": min(max_results, 100), "start": 1, "sort": sort}

    with httpx.Client(timeout=10.0) as client:
        resp = client.get(NAVER_NEWS_URL, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()

    results: List[Dict[str, Any]] = []
    seen_urls = set()

    for item in data.get("items", []):
        url = item.get("link")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        results.append({
            "id": make_id(url),
            "topic": topic,
            "title": clean_html(item.get("title", "")),
            "summary": clean_html(item.get("description", "")),
            "url": url,
            "published_at": item.get("pubDate"),
            "source": "NAVER",
        })
    return results

# 네이버 뉴스 검색 결과를 표준화된 {status, items} 구조로 반환하는 LLM용 tool
@tool
def search_news(query: str) -> Dict[str, Any]:
    print(f"\n[Tool: News Search(Naver)] Query: {query}")
    try:
        items = search_naver_news(query, max_results=10, sort="date")
        if not items:
            return {"status": "not_found", "query": query, "items": [], "message": "No news results found."}
        return {"status": "success", "query": query, "items": items}
    except Exception as e:
        print(f"[Tool: News Search(Naver)] Error: {e}")
        return {"status": "error", "query": query, "items": [], "message": str(e)}

# 뉴스 검색 결과(dict 또는 문자열)에서 기사 URL 목록만 추출
@tool
def extract_urls_from_search_result(result: Union[str, Dict[str, Any]]) -> List[str]:
    urls: List[str] = []

    if isinstance(result, dict):
        items = result.get("items") or []
        for it in items:
            u = (it.get("url") or "").strip()
            if u:
                urls.append(u)
    else:
        urls = re.findall(r"Link:\s*(https?://\S+)", result or "")

    cleaned: List[str] = []
    for u in urls:
        cleaned.append(u.strip().rstrip(").,]"))

    seen = set()
    unique: List[str] = []
    for u in cleaned:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique

# 기사 본문 텍스트를 정리(불필요한 공백/줄바꿈 제거)
def _clean_text(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s

# HTML의 JSON-LD(schema.org)에서 기사 메타데이터 추출
def _extract_json_ld(soup: BeautifulSoup) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue

        candidates = data if isinstance(data, list) else [data]
        for c in candidates:
            if not isinstance(c, dict):
                continue
            t = c.get("@type")
            if t in ("NewsArticle", "Article", "ReportageNewsArticle"):
                out["title"] = out.get("title") or c.get("headline")
                out["published_at"] = out.get("published_at") or c.get("datePublished")
                out["modified_at"] = out.get("modified_at") or c.get("dateModified")
                pub = c.get("publisher")
                if isinstance(pub, dict):
                    out["publisher"] = out.get("publisher") or pub.get("name")
                author = c.get("author")
                if isinstance(author, dict):
                    out["author"] = out.get("author") or author.get("name")
                elif isinstance(author, list) and author and isinstance(author[0], dict):
                    out["author"] = out.get("author") or author[0].get("name")
    return out

# 네이버 뉴스 페이지 구조에 맞춰 제목/본문/언론사/날짜 파싱
def _parse_naver_news(soup: BeautifulSoup) -> Dict[str, Any]:
    title = None
    for sel in ["h2#title_area", "h2.media_end_head_headline"]:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            title = el.get_text(" ", strip=True)
            break

    body_el = soup.select_one("#dic_area") or soup.select_one("div#articeBody")
    body = body_el.get_text("\n", strip=True) if body_el else None

    publisher = None
    press_el = soup.select_one(".media_end_head_top_logo img")
    if press_el and press_el.get("alt"):
        publisher = press_el.get("alt")

    published_at = None
    time_el = soup.select_one("span.media_end_head_info_datestamp_time")
    if time_el and time_el.get("data-date-time"):
        published_at = time_el.get("data-date-time")

    return {"title": title, "body": body, "publisher": publisher, "published_at": published_at}

# 뉴스 기사 URL에 직접 접속해 본문·메타데이터를 추출하는 핵심 크롤링 tool
@tool
def fetch_article_from_url(url: str) -> Dict[str, Any]:
    print(f"\n[Tool: Fetch Article] URL: {url}")
    collected_at = datetime.now().isoformat()

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; invest-agent/1.0)",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        }
        with httpx.Client(timeout=20, headers=headers, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            raw_html = resp.text

        soup = BeautifulSoup(raw_html, "html.parser")

        canonical_url = None
        canon = soup.find("link", rel="canonical")
        if canon and canon.get("href"):
            canonical_url = canon.get("href").strip()

        ld = _extract_json_ld(soup)

        if "news.naver.com" in (url or ""):
            parsed = _parse_naver_news(soup)
            title = parsed.get("title") or ld.get("title")
            body = parsed.get("body")
            publisher = parsed.get("publisher") or ld.get("publisher")
            author = ld.get("author")
            published_at = parsed.get("published_at") or ld.get("published_at")
        else:
            og_title = None
            mt = soup.find("meta", property="og:title")
            if mt and mt.get("content"):
                og_title = mt.get("content").strip()

            title = ld.get("title") or og_title or (soup.title.get_text(strip=True) if soup.title else None)
            publisher = ld.get("publisher")
            author = ld.get("author")
            published_at = ld.get("published_at")
            body = soup.get_text("\n", strip=True)

        body = _clean_text(body or "")
        ok = bool(body and len(body) >= 200)

        return {
            "status": "success" if ok else "error",
            "url": url,
            "canonical_url": canonical_url,
            "title": title,
            "body": body if body else None,
            "publisher": publisher,
            "author": author,
            "published_at": published_at,
            "collected_at": collected_at,
            "error": None if ok else "extracted_body_too_short_or_empty",
        }

    except Exception as e:
        print(f"[Tool: Fetch Article] Error: {e}")
        return {
            "status": "error",
            "url": url,
            "canonical_url": None,
            "title": None,
            "body": None,
            "publisher": None,
            "author": None,
            "published_at": None,
            "collected_at": collected_at,
            "error": str(e),
        }

# 사용자 입력(회사명/종목코드)을 stock_code / corp_code로 정규화
@tool
def resolve_ticker(user_input: str, config: RunnableConfig) -> Dict[str, Any]:
    print(f"\n[Tool: Resolve Ticker] Input: {user_input}")

    resolver = config["configurable"].get("ticker_resolver")
    if not resolver:
        return {"status": "error", "message": "ticker_resolver not found in config"}

    try:
        if hasattr(resolver, "ensure_loaded"):
            resolver.ensure_loaded()
        result = resolver.resolve(user_input)
        print(f"[Tool: Resolve Ticker] Status: {result.get('status')}")
        return result
    except Exception as e:
        print(f"[Tool: Resolve Ticker] Error: {e}")
        return {"status": "error", "message": str(e)}

# DART API를 호출해 특정 기업의 재무제표(주요 계정)를 조회
@tool
def get_financial_statement(
    corp_code: str,
    bsns_year: int,
    report_type: ReportType,
    config: RunnableConfig,
) -> Dict[str, Any]:
    print(f"\n[Tool: DART Financials] corp_code={corp_code}, year={bsns_year}, report={report_type}")

    dart_api_key = config["configurable"].get("dart_api_key") or os.getenv("DART_API_KEY")
    if not dart_api_key:
        return {"status": "error", "message": "DART_API_KEY not found (env or config)"}

    url = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"
    params = {
        "crtfc_key": dart_api_key,
        "corp_code": corp_code,
        "bsns_year": str(bsns_year),
        "reprt_code": REPRT_CODE_MAP[report_type],
    }

    try:
        with httpx.Client(timeout=20) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()

        status = payload.get("status")
        if status != "000":
            return {
                "status": "error",
                "message": payload.get("message"),
                "dart_status": status,
                "corp_code": corp_code,
                "bsns_year": bsns_year,
                "report_type": report_type,
            }

        rows: List[Dict[str, Any]] = payload.get("list", [])
        normalized = _normalize_key_accounts(rows)

        return {
            "status": "success",
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "report_type": report_type,
            "reprt_code": REPRT_CODE_MAP[report_type],
            "raw_count": len(rows),
            "key_accounts": normalized,
            "raw": rows,
        }

    except Exception as e:
        print(f"[Tool: DART Financials] Error: {e}")
        return {
            "status": "error",
            "message": str(e),
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "report_type": report_type,
        }

# DART에서 내려오는 숫자 문자열을 안전하게 int로 변환
def _to_int_safe(v: Any) -> Optional[int]:
    if v is None:
        return None
    s = str(v).strip()
    if s in ("", "-", "null", "None"):
        return None
    s = s.replace(",", "")
    if re.match(r"^\(.*\)$", s):
        s = "-" + s.strip("()")
    try:
        return int(float(s))
    except Exception:
        return None

# 재무제표 전체 계정 중 답변에 자주 쓰는 핵심 지표만 추려서 정규화
def _normalize_key_accounts(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "revenue": None,
        "operating_income": None,
        "net_income": None,
        "total_assets": None,
        "total_liabilities": None,
        "total_equity": None,
        "unit": None,
        "fs_div": None,
    }

    for r in rows:
        account = (r.get("account_nm") or "").strip()
        amount = _to_int_safe(r.get("thstrm_amount"))
        unit = r.get("currency") or r.get("currency_nm")
        if unit and not result["unit"]:
            result["unit"] = unit

        fs_div = r.get("fs_div")
        if fs_div and not result["fs_div"]:
            result["fs_div"] = fs_div

        if amount is None:
            continue

        if result["revenue"] is None and ("매출" in account):
            result["revenue"] = amount
        elif result["operating_income"] is None and ("영업이익" in account):
            result["operating_income"] = amount
        elif result["net_income"] is None and ("당기순이익" in account or "순이익" in account):
            result["net_income"] = amount
        elif result["total_assets"] is None and ("자산총계" in account or account == "자산총계"):
            result["total_assets"] = amount
        elif result["total_liabilities"] is None and ("부채총계" in account or account == "부채총계"):
            result["total_liabilities"] = amount
        elif result["total_equity"] is None and ("자본총계" in account or account == "자본총계"):
            result["total_equity"] = amount

    return result

@tool
def get_portfolio_stocks(user_id: str, config: RunnableConfig) -> Dict[str, Any]:
    engine = config["configurable"].get("db_engine")
    if not engine:
        return {"status": "error", "user_id": user_id, "count": 0, "holdings": [], "error": "db_engine not found"}

    join_stock_master = bool(config["configurable"].get("join_stock_master", False))

    try:
        if not join_stock_master:
            sql = text("SELECT user_id, stock_id FROM pf_items WHERE user_id = :user_id")
        else:
            sql = text("""
                SELECT p.user_id, p.stock_id, s.ticker, s.name
                FROM pf_items p
                JOIN stocks s ON s.id = p.stock_id
                WHERE p.user_id = :user_id
            """)

        with engine.connect() as conn:
            rows = conn.execute(sql, {"user_id": user_id}).mappings().all()

        holdings = []
        for r in rows:
            holdings.append({
                "user_id": r["user_id"],
                "stock_id": r["stock_id"],
                "ticker": r.get("ticker") or r["stock_id"],
                "name": r.get("name"),
            })

        return {"status": "success", "user_id": user_id, "count": len(holdings), "holdings": holdings, "error": None}
    except Exception as e:
        return {"status": "error", "user_id": user_id, "count": 0, "holdings": [], "error": str(e)}
