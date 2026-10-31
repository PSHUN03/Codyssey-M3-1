"""화면(HTML) 라우트."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.deps import current_user, require_member, require_onboarded
from app.models import User
from app.routers.auth import next_step
from app.services import account, planner
from app.services.agent.memory import KINDS
from app.services.finance.segment import SEGMENT_RULE_VERSION, SEGMENTS
from app.services.onboarding.flow import REGIONS
from app.services.policies import eligibility, repository
from app.web import render

router = APIRouter()

COACH_SUGGESTIONS = [
    "이번 달 30만 원 더 써도 될까요?",
    "청년미래적금에 월 30만 원 넣으면 얼마 받아요?",
    "제가 받을 수 있는 혜택이 뭐예요?",
    "비상금은 얼마나 모아야 해요?",
]


@router.get("/")
def landing(request: Request, user: User | None = Depends(current_user)):
    if user:
        return RedirectResponse(next_step(user), status_code=303)
    return render(request, "landing.html")


@router.get("/onboarding")
def onboarding_page(request: Request, redo: bool = False, user: User = Depends(require_member)):
    if user.profile and user.profile.onboarding_done and not redo:
        return RedirectResponse("/home", status_code=303)
    return render(request, "onboarding.html", user=user)


def _matches(user: User) -> list[eligibility.Eligibility]:
    return eligibility.match_all(user.profile, planner.goal_saving(user))


@router.get("/home")
def home(request: Request, user: User = Depends(require_onboarded)):
    matches = [m for m in _matches(user) if m.status in ("eligible", "check")][:3]
    commitment = next((m for m in reversed(user.memories) if m.kind == "commitment"), None)
    plan = planner.latest_plan(user)
    return render(request, "home.html", user=user, plan=plan, matches=matches, commitment=commitment,
                  goal=user.goals[-1] if user.goals else None, segment=planner.plan_segment(plan, user.profile))


@router.get("/plan")
def plan_page(request: Request, user: User = Depends(require_onboarded)):
    plan = planner.latest_plan(user)
    return render(request, "plan.html", user=user, plan=plan, facts=planner.profile_facts(user.profile),
                  segment=planner.plan_segment(plan, user.profile), segments=SEGMENTS,
                  segment_rule_version=SEGMENT_RULE_VERSION)


@router.get("/benefits")
def benefits_page(request: Request, user: User = Depends(require_onboarded)):
    groups: dict[str, list] = {status: [] for status in eligibility.STATUS_LABELS}
    for m in _matches(user):
        groups[m.status].append(m)
    return render(request, "benefits.html", user=user, groups=groups, labels=eligibility.STATUS_LABELS,
                  meta=repository.meta())


@router.get("/benefits/{policy_id}")
def benefit_detail(policy_id: str, request: Request, user: User = Depends(require_onboarded)):
    policy = repository.get_policy(policy_id)
    if policy is None:
        raise HTTPException(status_code=404)
    result = eligibility.evaluate(policy, user.profile, planner.goal_saving(user))
    return render(request, "benefit_detail.html", user=user, policy=policy, result=result, meta=repository.meta())


@router.get("/coach")
def coach_page(request: Request, user: User = Depends(require_onboarded)):
    sessions = [s for s in user.chat_sessions if s.kind == "coach"]
    messages = sessions[-1].messages[-40:] if sessions else []
    return render(request, "coach.html", user=user, messages=messages, suggestions=COACH_SUGGESTIONS)


@router.get("/settings")
def settings_page(request: Request, user: User = Depends(require_member)):
    return render(request, "settings.html", user=user, profile=user.profile,
                  facts=planner.profile_facts(user.profile), memories=list(reversed(user.memories)),
                  memory_kinds=KINDS, regions=REGIONS, consents=account.consent_status(user),
                  consent_labels={**account.REQUIRED_CONSENTS, **account.OPTIONAL_CONSENTS})


@router.get("/privacy")
def privacy(request: Request, user: User | None = Depends(current_user)):
    return render(request, "privacy.html", user=user)


@router.get("/terms")
def terms(request: Request, user: User | None = Depends(current_user)):
    return render(request, "terms.html", user=user)
