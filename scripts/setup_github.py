"""저장소 초기 설정을 한 번에 한다: main 보호 규칙, 팀원 초대, 라벨·이슈 등록 (표준 라이브러리만 사용).

GitHub CLI 없이 개인 토큰으로 동작한다. 토큰은 실행할 때 화면에 보이지 않게 입력받고,
이 프로세스 안에서만 쓰며 파일이나 출력에 남기지 않는다.

토큰 만들기: GitHub → Settings → Developer settings → Fine-grained tokens → Generate new token
- Repository access: Only select repositories → 이 저장소
- Permissions: Administration(Read and write), Issues(Read and write)
- 다 쓰면 같은 화면에서 토큰을 삭제한다

사용법:
    python scripts/setup_github.py --repo PSHUN03/Codyssey-M3-1 --dry-run   # 할 일만 보여 줌 (토큰 불필요)
    python scripts/setup_github.py --repo PSHUN03/Codyssey-M3-1             # 보호 규칙 + 초대 + 이슈
    python scripts/setup_github.py --repo PSHUN03/Codyssey-M3-1 --token-dialog   # 터미널에 붙여넣기가 안 되면
    python scripts/setup_github.py --repo PSHUN03/Codyssey-M3-1 --assign    # 초대 수락 후 담당자 지정
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from create_github_issues import GitHub, assign, create, parse_issues

ROOT = Path(__file__).resolve().parents[1]
RULESET_PATH = ROOT / ".github" / "rulesets" / "main.json"


def team_members(owner: str) -> list[str]:
    """docs/tasks 의 "담당:" 아이디 중 저장소 소유자를 뺀 사람들."""
    found = {issue["owner"] for issue in parse_issues() if issue["owner"]}
    return sorted(m for m in found if m.lower() != owner.lower())


def apply_ruleset(gh: GitHub) -> None:
    ruleset = json.loads(RULESET_PATH.read_text(encoding="utf-8"))
    status, data = gh.call("GET", f"repos/{gh.repo}/rulesets")
    existing = next((r for r in data if r.get("name") == ruleset["name"]), None) if isinstance(data, list) else None
    method, path = ("PUT", f"repos/{gh.repo}/rulesets/{existing['id']}") if existing else (
        "POST", f"repos/{gh.repo}/rulesets")
    status, data = gh.call(method, path, ruleset)
    if status == 422 and "allowed_merge_methods" in json.dumps(data):
        # 이 옵션을 모르는 API면 빼고 다시 보낸다. 머지 방식은 저장소 설정으로 제한한다
        for rule in ruleset["rules"]:
            rule.get("parameters", {}).pop("allowed_merge_methods", None)
        status, data = gh.call(method, path, ruleset)
    ok = status in (200, 201)
    print(f"보호 규칙 '{ruleset['name']}': {'적용' if ok else '실패'} ({status})"
          + ("" if ok else f" {data.get('message', data) if isinstance(data, dict) else data}"))

    # 머지 방식은 merge commit·squash만 두고, 머지된 브랜치는 자동으로 지운다
    status, data = gh.call("PATCH", f"repos/{gh.repo}", {
        "allow_merge_commit": True, "allow_squash_merge": True, "allow_rebase_merge": False,
        "delete_branch_on_merge": True,
    })
    print(f"저장소 머지 설정: {'적용' if status == 200 else f'실패 ({status})'}")


def invite(gh: GitHub, members: list[str]) -> None:
    for member in members:
        status, data = gh.call("PUT", f"repos/{gh.repo}/collaborators/{member}", {"permission": "push"})
        result = {201: "초대 보냄", 204: "이미 협업자"}.get(status)
        if result is None:
            message = data.get("message", data) if isinstance(data, dict) else data
            result = f"실패 ({status}) {message}"
        print(f"초대 @{member}: {result}")


def dialog_token() -> str:
    """별도 입력 창으로 받는다. 일부 터미널은 getpass에 붙여넣기가 전달되지 않는다."""
    import tkinter
    from tkinter import simpledialog

    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    token = simpledialog.askstring("GitHub 토큰", "토큰을 붙여 넣고 확인을 누르세요.", show="*", parent=root)
    root.destroy()
    return token or ""


def read_token(use_dialog: bool) -> None:
    if os.getenv("GITHUB_TOKEN"):
        return
    if use_dialog:
        token = dialog_token().strip()
    elif not sys.stdin.isatty():
        sys.exit("GITHUB_TOKEN 환경변수가 없고 토큰을 입력받을 터미널도 아닙니다.")
    else:
        token = getpass.getpass("GitHub 토큰을 붙여 넣고 Enter (화면에 보이지 않습니다): ").strip()
    if not token:
        sys.exit("토큰이 비어 있습니다.")
    os.environ["GITHUB_TOKEN"] = token  # 이 프로세스 안에서만 쓴다


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="owner/name 형식의 저장소")
    parser.add_argument("--dry-run", action="store_true", help="할 일만 보여 주고 GitHub에는 아무것도 하지 않는다")
    parser.add_argument("--assign", action="store_true", help="초대를 수락한 팀원을 이슈 담당자로 지정한다")
    parser.add_argument("--token-dialog", action="store_true",
                        help="토큰을 터미널 대신 별도 입력 창으로 받는다 (터미널에 붙여넣기가 안 될 때)")
    args = parser.parse_args()

    owner = args.repo.split("/")[0]
    members = team_members(owner)
    issues = parse_issues()
    if args.dry_run:
        if args.assign:
            print(f"담당자 지정 대상 이슈 {sum(1 for i in issues if i['owner'])}개")
        else:
            print(f"보호 규칙: {RULESET_PATH.relative_to(ROOT)}")
            print(f"초대: {', '.join('@' + m for m in members)}")
            print(f"이슈: {len(issues)}개, 라벨: {len({lb for i in issues for lb in i['labels']})}개")
        return

    read_token(args.token_dialog)
    gh = GitHub(args.repo)
    status, data = gh.call("GET", f"repos/{args.repo}")
    if status != 200:
        message = data.get("message", data) if isinstance(data, dict) else data
        sys.exit(f"저장소에 접근하지 못했습니다 ({status}): {message}. 토큰의 저장소와 권한을 확인하세요.")

    if args.assign:
        assign(gh, issues)
        return
    apply_ruleset(gh)
    invite(gh, members)
    create(gh, issues)
    print("\n끝났습니다. 다 쓴 토큰은 GitHub 설정에서 삭제하세요.")


if __name__ == "__main__":
    main()
