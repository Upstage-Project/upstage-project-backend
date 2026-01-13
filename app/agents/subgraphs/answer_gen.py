from typing import Dict, Any, List, Optional, Literal

from langgraph.graph import StateGraph, END
from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
    BaseMessage,
)

from app.agents.state import AnswerGenAgentState
from app.agents.tools import solar_chat
from app.agents.utils import get_current_time_str
from app.core.logger import log_agent_step


RouteType = Literal["term", "investment"]


# -------------------------
# 1) System Instruction
# -------------------------
instruction_answer_gen = """
당신은 투자 정보 응답 생성(Answer Generator) 에이전트입니다.
당신의 역할은 다음 두 가지 중 하나입니다.

(1) 용어 질문(term):
- 사용자의 질문이 투자/경제 용어 설명일 때, 이해하기 쉽게 설명합니다.
- 불명확하면 가장 대표 의미를 설명하되 '추정'임을 표시하고, 1문장으로 맥락을 되묻습니다.

(2) 투자 분석 전달(investment):
- 분석 에이전트(Agent2)가 생성한 analysis_results를 기반으로 사용자에게 최종 답변을 구성합니다.
- 절대 분석 결과에 없는 사실/수치/결론을 만들어내지 마세요.
- 투자 조언은 매수/매도 지시 대신 체크리스트/관찰 포인트 형태로 제시하세요.
- 답변은 한국어 Markdown으로 작성하세요.
"""


# -------------------------
# 2) Helpers
# -------------------------
# 대화 메시지 목록에서 “사용자의 최신 질문 텍스트”만 뽑아오는 함수
def _get_user_query(messages: List[BaseMessage]) -> str:
    for m in reversed(messages or []):
        if isinstance(m, HumanMessage):
            return m.content or ""
    return (getattr(messages[-1], "content", "") if messages else "") or ""


# 이 실행이 용어 설명(term) 인지, 투자 응답(investment) 인지 결정
def _infer_route(state: AnswerGenAgentState) -> RouteType:
    # 우선순위: state.route -> collected.route -> default(investment)
    route = state.get("route")
    if route in ("term", "investment"):
        return route

    collected = state.get("collected") or {}
    route2 = collected.get("route")
    if route2 in ("term", "investment"):
        return route2

    # analysis_results가 있으면 investment로 보는 게 안전
    if state.get("analysis_results"):
        return "investment"

    # 기본은 investment (Agent3 본연 역할 기준)
    # 단, 용어 질문은 오케스트레이터가 term으로 보내준다는 전제
    return "investment"


# Agent1이 수집한 근거(collected)를 LLM이 참고할 수 있는 짧은 텍스트 블록으로 변환 -> LLM이 출처를 쉽게 뽑도록 구조화
def _build_sources_block(collected: Dict[str, Any], max_news: int = 8, max_articles: int = 3) -> str:
    if not collected:
        return "정보 없음"

    news = collected.get("news") or []
    articles = collected.get("articles") or []
    financials = collected.get("financials") or {}

    lines: List[str] = []

    if news:
        lines.append("[NEWS_SNIPPETS]")
        for it in news[:max_news]:
            lines.append(f"- {it.get('published_at')} | {it.get('title')} | {it.get('url')}")

    if articles:
        lines.append("\n[ARTICLES]")
        for a in articles[:max_articles]:
            lines.append(f"- {a.get('published_at')} | {a.get('title')} | {a.get('url')} | {a.get('publisher')}")

    if isinstance(financials, dict) and financials.get("status") == "success":
        ka = financials.get("key_accounts") or {}
        lines.append("\n[FINANCIALS]")
        lines.append(f"- {financials.get('bsns_year')} {financials.get('report_type')} | key_accounts={ka}")

    return "\n".join(lines).strip() if lines else "정보 없음"


# Agent2의 분석 결과를 LLM 프롬프트에 넣기 좋게 “종목별 섹션” 형태로 합침
def _build_analysis_block(analysis_results: List[Dict[str, Any]], max_items: int = 10, max_chars_each: int = 5000) -> str:
    if not analysis_results:
        return "정보 없음"

    blocks: List[str] = []
    for r in analysis_results[:max_items]:
        name = r.get("stock_name") or ""
        code = r.get("stock_code") or ""
        rep = r.get("analysis_report") or ""
        if len(rep) > max_chars_each:
            rep = rep[:max_chars_each] + "\n...(truncated)"
        blocks.append(f"## {name} ({code})\n{rep}")

    return "\n\n".join(blocks).strip()


# 용어 질문(term)일 때 LLM에게 줄 프롬프트 텍스트를 생성
def _make_term_prompt(user_query: str) -> str:
    return f"""
[사용자 질문]
{user_query}

[작업]
사용자 질문의 핵심 용어를 설명하세요.

[출력 형식(Markdown)]
### 한 줄 정의
### 쉽게 풀어쓴 설명
### 투자에서 왜 중요?
### 예시 (상황/숫자)
### 오해/주의 포인트
### 같이 보면 좋은 용어 3개

[규칙]
- 질문이 모호하면 1문장으로 맥락을 되물어보고, 대표 의미 1개를 '추정'임을 표시하며 설명하세요.
- 지어내지 말고, 불확실하면 "정보 부족"이라고 말하세요.
"""


# 투자 응답(investment)일 때 LLM에게 줄 프롬프트 텍스트 생성
def _make_invest_prompt(user_query: str, analysis_block: str, sources_block: str) -> str:
    return f"""
[사용자 질문]
{user_query}

[Analysis Results: Agent2가 생성한 분석 결과]
{analysis_block}

[Sources: Agent1이 수집한 근거 요약]
{sources_block}

[작업]
아래 형식으로만 답하세요. (형식 엄수)
- News/Sources에 없는 내용은 "정보 없음"으로 표기하세요.
- 긍정/부정 판단은 반드시 근거를 함께 제시하세요.
- 출처는 Sources에 있는 URL만 사용하세요.

[출력 형식(Markdown)]
## (뉴스 분석)
- **주요 이슈 요약:** 
- **해당 이슈 긍정/부정:** (긍정/부정/중립 중 하나)
- **판단 근거:** (Analysis Results 또는 Sources에서 근거 문장/팩트를 기반으로)
- **출처:** (관련 URL을 bullet로)

## (기업 분석)
- **재무제표 분석(긍정/부정):** (긍정/부정/중립 중 하나)
- **판단 이유:** (재무 항목/추세가 있으면 언급, 없으면 "정보 없음")

[추가 규칙]
1) Analysis Results에 없는 사실/수치/결론은 만들지 마세요.
2) 매수/매도 지시 금지. 필요하면 "추가 확인 포인트"를 판단 이유 끝에 1~3개 bullet로 제안.
3) 한국어로 작성하고, 문장은 간결하게.
"""


# -------------------------
# 3) Node
# -------------------------
# LangGraph에서 실행되는 Agent3의 핵심 노드 함수
def answer_gen_agent(state: AnswerGenAgentState):
    messages: List[BaseMessage] = state.get("messages", [])
    user_query = _get_user_query(messages)
    route = _infer_route(state)

    # SystemMessage 주입 (레퍼런스 스타일 유지)
    if not messages or not isinstance(messages[0], SystemMessage):
        current_time = get_current_time_str()
        system_content = f"현재 시간: {current_time}\n\n{instruction_answer_gen}"
        messages = [SystemMessage(content=system_content)] + messages

    # Prompt 구성: term / investment
    if route == "term":
        log_agent_step("AnswerGen", "용어 질문 응답 생성 시작", {"query": user_query})
        prompt = _make_term_prompt(user_query)
    else:
        analysis_block = _build_analysis_block(state.get("analysis_results") or [])
        sources_block = _build_sources_block(state.get("collected") or {})
        log_agent_step("AnswerGen", "투자 분석 전달 응답 생성 시작", {"query": user_query})
        prompt = _make_invest_prompt(user_query, analysis_block, sources_block)

    # HumanMessage로 prompt 추가 후 LLM 호출
    llm_messages = messages + [HumanMessage(content=prompt)]
    response = solar_chat.invoke(llm_messages)

    log_agent_step("AnswerGen", "응답 생성 완료", {"route": route, "answer": response.content})
    return {"messages": messages + [response], "final_answer": response.content}


# -------------------------
# 4) Graph
# -------------------------
workflow = StateGraph(AnswerGenAgentState)
workflow.add_node("answer_gen_agent", answer_gen_agent)
workflow.set_entry_point("answer_gen_agent")
workflow.add_edge("answer_gen_agent", END)

answer_gen_graph = workflow.compile()


# -------------------------
# 5) Single-file Runner (Service 대체)
# -------------------------
def run_answer_gen(
    user_query: str,
    *,
    route: Optional[RouteType] = None,
    collected: Optional[Dict[str, Any]] = None,
    analysis_results: Optional[List[Dict[str, Any]]] = None,
    history: Optional[List[BaseMessage]] = None,
    config=None,
) -> Dict[str, Any]:
    """
    AnswerGenService를 분리하지 않고 answer_gen.py 안에서 실행까지 제공하기 위한 함수.

    - user_query: 사용자 질문 원문
    - route: "term" | "investment" (없으면 state/collected에서 추론)
    - collected: Agent1 결과(선택)
    - analysis_results: Agent2 결과(선택)
    - history: 이전 대화 히스토리 (선택)
    """
    messages: List[BaseMessage] = []
    if history:
        messages.extend(history)

    # user_query 자체는 messages에 포함(원하면 그대로 유지)
    messages.append(HumanMessage(content=user_query))

    init_state: AnswerGenAgentState = {
        "messages": messages,
        "route": route,
        "collected": collected or {},
        "analysis_results": analysis_results or [],
    }

    result = answer_gen_graph.invoke(init_state, config=config)

    # 레퍼런스 스타일: 신규 AIMessage만 뽑아서 logs로 반환
    all_msgs = result.get("messages", [])
    final_ai = next(
        (m for m in reversed(all_msgs) if isinstance(m, AIMessage)),
        None
    )

    return {
        "answer_logs": [final_ai] if final_ai else [],
        "final_answer": result.get("final_answer") or (final_ai.content if final_ai else ""),
        "process_status": "success",
    }

