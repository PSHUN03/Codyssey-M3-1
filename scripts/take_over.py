"""MVP 코드 이관 도우미. 담당 단계의 파일만 이전 소스 묶음에서 이 저장소로 옮긴다 (표준 라이브러리만 사용).

MVP(2026-09-30~10-22)는 팀장이 Claude Code와 페어 프로그래밍으로 만들었다. 새 저장소에서는 각 담당자가
자기 모듈을 읽고 테스트한 뒤 PR로 옮기고, 커밋에 원작성자를 공동 작성자로 남긴다. 자세한 절차는
docs/migration.md 에 있다.

사용법:
    python scripts/take_over.py --list                                     # 단계별 파일 목록
    python scripts/take_over.py MIG-1 --source ../sadari-mvp-source.zip    # 파일 옮기기 + 커밋 메시지 준비
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_AUTHOR = "PSHUN03 <301172814+PSHUN03@users.noreply.github.com>"

STEPS: dict[str, dict] = {
    "MIG-1": {
        "title": "백엔드 기반과 계산 엔진",
        "owner": "1yuxnp",
        "after": [],
        "files": [
            "app/__init__.py", "app/config.py", "app/db.py", "app/models.py", "app/security.py",
            "app/services/__init__.py", "app/services/text.py",
            "app/services/finance/__init__.py", "app/services/finance/budget.py",
            "app/services/finance/money.py", "app/services/finance/savings.py",
            "app/services/finance/segment.py",
            "tests/__init__.py", "tests/conftest.py", "tests/test_finance.py", "tests/test_segment.py",
        ],
    },
    "MIG-2": {
        "title": "정책 데이터와 검색·자격 판정",
        "owner": "yak7297",
        "after": ["MIG-1"],
        "files": [
            "app/services/policies/__init__.py", "app/services/policies/eligibility.py",
            "app/services/policies/repository.py", "app/services/policies/search.py",
            "app/data/policies.json", "tests/test_policies.py", "eval/golden_policy_qa.jsonl", "n8n/README.md",
        ],
    },
    "MIG-3": {
        "title": "AI 코치 Agent·가드레일·메모리",
        "owner": "zero-ysyang",
        "after": ["MIG-2"],
        "files": [
            "app/services/agent/__init__.py", "app/services/agent/coach.py", "app/services/agent/guardrails.py",
            "app/services/agent/llm.py", "app/services/agent/memory.py", "app/services/agent/prompts.py",
            "app/services/agent/tools.py", "app/services/planner.py",
            "app/services/onboarding/__init__.py", "app/services/onboarding/llm_extract.py",
            "app/routers/__init__.py", "app/routers/coach.py",
            "tests/test_guardrails.py", "eval/redteam.jsonl", "eval/run_eval.py",
        ],
    },
    "MIG-4": {
        "title": "화면·디자인 시스템·진단 질문 카드",
        "owner": "hyoryeomii",
        "after": ["MIG-1"],
        "files": [
            "app/web.py", "app/routers/pages.py", "app/services/onboarding/flow.py",
            "app/static/css/app.css", "app/static/icons/favicon.svg", "app/static/icons/icon-192.png",
            "app/static/icons/icon-512.png", "app/static/icons/icon-maskable-512.png",
            "app/static/js/app.js", "app/static/js/sw.js", "app/static/manifest.webmanifest",
            "app/templates/_macros.html", "app/templates/auth.html", "app/templates/base.html",
            "app/templates/benefit_detail.html", "app/templates/benefits.html", "app/templates/coach.html",
            "app/templates/consent.html", "app/templates/error.html", "app/templates/home.html",
            "app/templates/landing.html", "app/templates/onboarding.html", "app/templates/plan.html",
            "app/templates/privacy.html", "app/templates/settings.html", "app/templates/terms.html",
            "scripts/make_icons.py", "scripts/make_demo_gif.py",
        ],
    },
    "MIG-5": {
        "title": "라우터·인증·앱 조립과 통합 테스트",
        "owner": "1yuxnp",
        "after": ["MIG-3", "MIG-4"],
        "files": [
            "app/deps.py", "app/main.py", "app/services/account.py",
            "app/routers/api.py", "app/routers/auth.py", "app/routers/internal.py",
            "app/routers/onboarding.py", "app/routers/public.py",
            "render.yaml", "tests/test_app_flow.py", "tests/test_onboarding_flow.py",
        ],
    },
}


class Source:
    """이전 소스 묶음. zip 파일이나 압축을 푼 폴더 모두 받는다."""

    def __init__(self, path: Path):
        self.path = path
        if path.is_file() and zipfile.is_zipfile(path):
            self.zip = zipfile.ZipFile(path)
            names = self.zip.namelist()
            # 압축을 한 번 더 감싼 폴더가 있으면 그 이름을 앞에 붙여 찾는다
            self.prefix = "" if "app/main.py" in names else next(
                (n.removesuffix("app/main.py") for n in names if n.endswith("/app/main.py")), "")
        elif path.is_dir():
            self.zip = None
        else:
            sys.exit(f"소스 묶음을 찾지 못했습니다: {path}")

    def read(self, rel: str) -> bytes:
        if self.zip is None:
            target = self.path / rel
            if not target.is_file():
                sys.exit(f"소스 묶음에 파일이 없습니다: {rel}")
            return target.read_bytes()
        try:
            return self.zip.read(self.prefix + rel)
        except KeyError:
            sys.exit(f"소스 묶음에 파일이 없습니다: {rel}")


def git(*args: str) -> str:
    res = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    return res.stdout.strip() if res.returncode == 0 else ""


def commit_message(step: str, me: str) -> str:
    info = STEPS[step]
    return (
        f"feat: [{step}] {info['title']} 이관\n\n"
        f"이전 저장소에서 만든 MVP 코드(2026-09-30~10-22, @PSHUN03이 Claude Code와 페어 프로그래밍으로\n"
        f"작성)를 담당자 @{me}가 읽고 테스트한 뒤 옮긴다. 옮긴 파일 {len(info['files'])}개, 목록은\n"
        f"docs/migration.md의 {step}.\n\n"
        f"Co-authored-by: {ORIGINAL_AUTHOR}\n"
        "Co-authored-by: Claude <noreply@anthropic.com>\n"
    )


def take_over(step: str, source: Source, force: bool) -> None:
    info = STEPS[step]
    missing = [s for s in info["after"] if not all((ROOT / f).exists() for f in STEPS[s]["files"])]
    if missing:
        sys.exit(f"{step}보다 먼저 {', '.join(missing)}가 main에 머지되어야 합니다. "
                 "`git switch main && git pull`로 최신 main을 받은 뒤 브랜치를 다시 만드세요.")
    branch = git("branch", "--show-current")
    if branch in ("", "main"):
        sys.exit(f"main이 아닌 작업 브랜치에서 실행하세요: git switch -c migrate/{step}")

    copied, same = [], 0
    for rel in info["files"]:
        data = source.read(rel)
        target = ROOT / rel
        if target.exists():
            if target.read_bytes() == data:
                same += 1
                continue
            if not force:
                sys.exit(f"이미 다른 내용의 파일이 있습니다: {rel} (덮어쓰려면 --force)")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        copied.append(rel)

    me = git("config", "user.name") or "담당자"
    msg_path = Path(git("rev-parse", "--absolute-git-dir") or ROOT / ".git") / f"{step}_COMMIT_MSG"
    msg_path.write_text(commit_message(step, me), encoding="utf-8")

    print(f"{step} {info['title']}: {len(copied)}개 옮김, {same}개는 이미 같음\n")
    print("다음 순서로 진행하세요.")
    print("1. 옮긴 파일을 직접 읽고, 이해한 내용을 PR 본문에 적을 준비를 합니다.")
    print("2. 확인:  ruff check .   그리고   pytest -q")
    print(f"3. 커밋:  git add {' '.join(sorted({r.split('/')[0] for r in info['files']}))}")
    print(f'         git commit -F "{msg_path}"')
    print(f"4. 올리기: git push -u origin {branch}")
    print("5. GitHub에서 PR을 열고 docs/migration.md의 PR 본문 양식을 채웁니다.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("step", nargs="?", choices=list(STEPS), help="이관 단계 (예: MIG-1)")
    parser.add_argument("--source", type=Path, help="이전 소스 묶음 (zip 또는 압축을 푼 폴더)")
    parser.add_argument("--list", action="store_true", help="단계별 파일 목록을 보여준다")
    parser.add_argument("--force", action="store_true", help="내용이 다른 파일이 있어도 덮어쓴다")
    args = parser.parse_args()

    if args.list or not args.step:
        for step, info in STEPS.items():
            after = f", 먼저 머지: {', '.join(info['after'])}" if info["after"] else ""
            print(f"{step} {info['title']} (@{info['owner']}, 파일 {len(info['files'])}개{after})")
            for rel in info["files"]:
                print(f"  {rel}")
        return
    if not args.source:
        sys.exit("--source 로 이전 소스 묶음 경로를 알려주세요.")
    take_over(args.step, Source(args.source), args.force)


if __name__ == "__main__":
    main()
