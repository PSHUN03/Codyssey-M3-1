"""AI 재무 코치 (FR-09).

- AnthropicCoach: Claude가 도구를 골라 호출하는 Agent 루프 (스트리밍)
- MockCoach: API 키가 없을 때 쓰는 규칙 기반 코치. 같은 도구를 호출하므로 구조와 숫자는 실제와 같다.

두 코치 모두 이벤트 dict를 순서대로 내보낸다:
  {"type": "status", "text": ...}  도구 실행 중 안내
  {"type": "delta",  "text": ...}  답변 텍스트 조각
  {"type": "error",  "text": ...}  복구 불가 오류
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections.abc import Iterator
from typing import Protocol

import anthropic

from app.config import get_settings
from app.services.agent import llm
from app.services.agent.guardrails import INVESTMENT_GUARD_REPLY, is_investment_advice_request
from app.services.agent.memory import recent_memories
from app.services.agent.prompts import COACH_SYSTEM, context_block
from app.services.agent.tools import TOOL_LABELS, TOOL_SPECS, ToolContext, run_tool
from app.services.finance.money import find_amounts, find_duration_months, fmt_won
from app.services.policies.eligibility import today_kst
from app.services.text import josa

log = logging.getLogger("sadari.coach")


class Coach(Protocol):
    def stream(self, ctx: ToolContext, history: list[dict], user_text: str) -> Iterator[dict]: ...


def get_coach() -> Coach:
    return MockCoach() if get_settings().is_mock else AnthropicCoach()


# ------------------------------------------------------------------ Claude Agent

class AnthropicCoach:
    MAX_TURNS = 6
    ERROR_TEXT = "AI 서버와 연결하지 못했어요. 잠시 후 다시 시도해 주세요."

    def stream(self, ctx: ToolContext, history: list[dict], user_text: str) -> Iterator[dict]:
        settings = get_settings()
        model = settings.coach_model
        user = ctx.user
        system = [
            # 고정 프롬프트(+도구 정의)는 캐시하고, 바뀌는 정보는 뒤 블록에 둔다
            {"type": "text", "text": COACH_SYSTEM, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": context_block(
                user.nickname, today_kst().isoformat(),
                [m.content for m in recent_memories(user)],
                bool(user.profile and user.profile.onboarding_done),
            )},
        ]
        messages: list[dict] = [*history, {"role": "user", "content": user_text}]
        params: dict = {"model": model, "max_tokens": 16000, "system": system, "tools": TOOL_SPECS, "messages": messages}
        if llm.supports_effort(model):
            params["output_config"] = {"effort": settings.coach_effort}

        json_retries = 0
        need_separator = False
        for _ in range(self.MAX_TURNS):
            wrote_text = False
            try:
                with self._open_stream(model, params) as stream:
                    for event in stream:
                        if event.type == "text" and event.text:
                            if need_separator:
                                yield {"type": "delta", "text": "\n\n"}
                                need_separator = False
                            wrote_text = True
                            yield {"type": "delta", "text": event.text}
                    response = stream.get_final_message()
                json_retries = 0
            except ValueError:
                # 도구 입력 JSON을 전혀 해석할 수 없는 경우: 같은 턴을 제한적으로 다시 요청한다
                json_retries += 1
                if json_retries > 2:
                    yield {"type": "error", "text": self.ERROR_TEXT}
                    return
                continue
            except anthropic.APIError:
                log.exception("코치 API 호출 실패")
                yield {"type": "error", "text": self.ERROR_TEXT}
                return

            if response.stop_reason == "refusal":
                yield {"type": "delta", "text": "\n\n이 요청에는 답하기 어려워요. 돈 관리와 관련된 질문으로 다시 물어봐 주세요."}
                return
            if response.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": response.content})
                continue

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                return  # end_turn 등: 답변 완료
            if response.stop_reason == "max_tokens":
                yield {"type": "error", "text": "답변이 너무 길어져 멈췄어요. 질문을 나눠서 해 주세요."}
                return

            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in tool_uses:
                yield {"type": "status", "text": TOOL_LABELS.get(block.name, "확인하고 있어요")}
                output, is_error = run_tool(block.name, block.input, ctx)
                item = {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(output, ensure_ascii=False, default=str),
                }
                if is_error:
                    item["is_error"] = True
                results.append(item)
            messages.append({"role": "user", "content": results})
            need_separator = wrote_text

        yield {"type": "error", "text": "답변을 정리하지 못했어요. 질문을 조금 더 구체적으로 해 주세요."}

    @staticmethod
    def _open_stream(model: str, params: dict):
        client = llm.client()
        if llm.use_fallback(model):
            return client.beta.messages.stream(betas=[llm.FALLBACK_BETA], fallbacks="default", **params)
        return client.messages.stream(**params)


# ------------------------------------------------------------------ 모의 코치

_POLICY_RE = re.compile(r"정책|혜택|지원|적금|청약|월세|세액|소득세|감면|도약|미래적금|내일저축|연금|IRP|irp|ISA|받을\s*수|신청|자격|정부")
_SPEND_RE = re.compile(r"써도|쓸까|사도|살까|지출|사고\s*싶|질러|결제|구매|더\s*쓰")
_SAVE_RE = re.compile(r"모으|모을|저축|만기|시뮬|얼마나|얼마씩|몇\s*(년|달|개월)|넣으면|넣을")
_PLAN_RE = re.compile(r"배분|월급|예산|플랜|통장|쪼개|계획|비상금|생활비|내\s*상황")
_MEMORY_RE = re.compile(r"기억해|기억\s*해\s*줘|잊지\s*마|약속")
_TARGET_RE = re.compile(r"모으려면|필요|얼마씩|목표")


class MockCoach:
    """API 키 없이 동작하는 규칙 기반 코치. 실제 도구를 호출하므로 숫자는 모두 계산 엔진에서 나온다."""

    def stream(self, ctx: ToolContext, history: list[dict], user_text: str) -> Iterator[dict]:
        text = user_text.strip()
        try:
            reply = self._reply(ctx, text)
        except Exception:  # 모의 모드에서도 오류가 화면을 깨뜨리지 않게 한다
            log.exception("모의 코치 처리 실패")
            yield {"type": "error", "text": "답변을 만들지 못했어요. 다시 시도해 주세요."}
            return
        for i in range(0, len(reply), 14):
            yield {"type": "delta", "text": reply[i:i + 14]}

    def _call(self, ctx: ToolContext, name: str, args: dict) -> dict:
        result, is_error = run_tool(name, args, ctx)
        if is_error:
            raise ValueError(result.get("error"))
        return result

    def _reply(self, ctx: ToolContext, text: str) -> str:
        has_profile = bool(ctx.user.profile and ctx.user.profile.onboarding_done)
        if is_investment_advice_request(text):
            return INVESTMENT_GUARD_REPLY
        if _MEMORY_RE.search(text):
            self._call(ctx, "save_memory", {"kind": "commitment", "content": text[:200]})
            return f"기억해 둘게요. \"{text[:60]}\"\n다음 주 체크인 때 어땠는지 같이 볼게요."

        amounts = find_amounts(text, assume_manwon=False)
        if not has_profile and (_SPEND_RE.search(text) or _PLAN_RE.search(text)):
            return "재무 진단을 먼저 마치면 월급과 지출에 맞춰 계산해 드릴 수 있어요."
        if amounts and _SPEND_RE.search(text):
            return self._spending(ctx, amounts[0])
        if amounts and _SAVE_RE.search(text):
            return self._savings(ctx, text, amounts)
        if _POLICY_RE.search(text):
            return self._policies(ctx, text)
        if has_profile and _PLAN_RE.search(text):
            return self._plan(ctx)
        return (
            "월급 배분, 저축 계산, 청년 혜택을 물어보시면 숫자로 답해 드려요. 예를 들면 이런 질문이에요.\n"
            "· 이번 달 30만 원 더 써도 될까요?\n"
            "· 청년미래적금에 월 30만 원 넣으면 얼마 받아요?\n"
            "· 제가 받을 수 있는 월세 지원이 있나요?"
        )

    def _spending(self, ctx: ToolContext, amount: int) -> str:
        d = self._call(ctx, "check_extra_spending", {"amount": amount})
        if d["exceeds_goal_saving"]:
            return (f"{fmt_won(amount)}은 이번 달 목표 저축({fmt_won(d['goal_saving_before'])})보다 커요. "
                    "저축을 다 멈춰도 모자라니 비상금을 건드리기 전에 한 번 더 생각해 보세요.")
        lines = [f"생활비 예산 {fmt_won(d['living_budget'])} 안에서 해결하면 괜찮아요. "
                 f"그게 어렵다면 이번 달 목표 저축이 {fmt_won(d['goal_saving_before'])}에서 "
                 f"{fmt_won(d['goal_saving_after'])}으로 줄어요."]
        delay = d.get("delay_months")
        if delay and delay >= 1:
            lines.append(f"목표 달성은 {round(delay)}개월쯤 늦어져요.")
        elif delay:
            lines.append("목표 달성 시점은 한 달이 안 되게 늦어져요.")
        lines.append("결제 전에 하루만 기다려 보는 것도 방법이에요.")
        return " ".join(lines)

    def _savings(self, ctx: ToolContext, text: str, amounts: list[int]) -> str:
        months = find_duration_months(text)
        if "미래적금" in text:
            d = self._call(ctx, "simulate_savings", {"monthly_amount": amounts[0], "product": "youth_future_savings"})
            r = d["readable"]
            parts = f"원금 {r['원금']}, 이자 {r['세전 이자']}"
            if d["contribution"]:
                parts += f", 정부기여금 {r['정부기여금']}"
            return (f"청년미래적금에 매달 {fmt_won(d['monthly'])}씩 3년 넣으면 만기에 **{r['만기 수령액']}**쯤 받아요. "
                    f"{parts}을 더한 금액이에요.\n{' '.join(d['notes'])}")
        if _TARGET_RE.search(text) and months:
            monthly = math.ceil(amounts[0] / months / 1_000) * 1_000
            d = self._call(ctx, "simulate_savings", {"monthly_amount": monthly, "months": months,
                                                      "target_amount": amounts[0]})
            r = d["readable"]
            return (f"{months}개월 안에 {fmt_won(amounts[0])}을 모으려면 매달 **{fmt_won(monthly)}**이 필요해요. "
                    f"적금에 넣으면 이자까지 만기에 {r['만기 수령액']}쯤 돼요.\n{' '.join(d['notes'])}")
        months = months or 12
        d = self._call(ctx, "simulate_savings", {"monthly_amount": amounts[0], "months": months})
        r = d["readable"]
        return (f"매달 {fmt_won(d['monthly'])}씩 {months}개월 모으면 만기에 **{r['만기 수령액']}**쯤 받아요. "
                f"원금 {r['원금']}에 이자 {r['세전 이자']}, 세금 {r['세금']}을 계산했어요.\n{' '.join(d['notes'])}")

    def _policies(self, ctx: ToolContext, text: str) -> str:
        d = self._call(ctx, "search_youth_policies", {"query": text[:200]})
        results = d.get("results", [])
        if not results:
            return "관련 정책을 찾지 못했어요. 온통청년이나 복지로에서 한 번 더 찾아보세요."
        lines = []
        for r in sorted(results, key=lambda r: bool(r.get("failed_conditions"))):
            if r.get("failed_conditions"):
                # 받을 수 없는 정책은 이유만 짧게 말한다
                topic = josa(r["name"], "은/는")[len(r["name"]):]
                lines.append(f"**{r['name']}**{topic} {r['failed_conditions'][0]} 조건에 맞지 않아 지금은 받기 어려워요.")
                continue
            head = f"**{r['name']}**" + (f" ({r['status']})" if r.get("status") else "")
            body = r["summary"]
            if r.get("estimate"):
                body += f" {r['estimate']}."
            if r.get("needs_check"):
                body += f" {r['needs_check'][0]} 조건은 따로 확인해야 해요."
            lines.append(f"{head}\n{body}")
        lines.append(f"{results[0]['as_of']} 기준 정보예요. 출처는 아래에서 볼 수 있어요.")
        return "\n\n".join(lines)

    def _plan(self, ctx: ToolContext) -> str:
        d = self._call(ctx, "get_my_finances", {})
        rows = "\n".join(f"· {label} {amount}" for label, amount in d["monthly_plan_readable"].items())
        out = f"지금 월급은 이렇게 나눠져 있어요.\n{rows}"
        ef = d["emergency_fund"]
        if ef["gap"]:
            out += f"\n\n비상금은 {fmt_won(ef['target'])}이 목표인데 {fmt_won(ef['gap'])}이 모자라서 저축 일부를 비상금에 먼저 쓰고 있어요."
        if d["warnings"]:
            out += "\n\n" + d["warnings"][0]
        return out


