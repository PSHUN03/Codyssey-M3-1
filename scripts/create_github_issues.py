"""docs/tasks/*.md 의 이슈 초안을 GitHub Issue로 한 번에 만든다 (표준 라이브러리만 사용).

사용법:
    python scripts/create_github_issues.py                                       # 미리 보기 (아무것도 만들지 않음)
    python scripts/create_github_issues.py --repo PSHUN03/Codyssey-M3-1 --apply   # 실제 생성 (같은 제목은 건너뜀)
    python scripts/create_github_issues.py --repo PSHUN03/Codyssey-M3-1 --assign  # 각 파일의 "담당:"대로 담당자 지정

인증은 두 가지 중 하나를 쓴다.
- GitHub CLI(`gh auth login`)로 로그인해 두면 gh가 인증을 처리한다. 토큰을 따로 다루지 않아도 된다.
- 개인 토큰을 쓰려면 해당 저장소의 Issues 쓰기 권한으로 발급하고 환경변수 GITHUB_TOKEN 으로만 전달한다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

TASKS_DIR = Path(__file__).resolve().parents[1] / "docs" / "tasks"
HEADING_RE = re.compile(r"^## (.+)$", re.MULTILINE)
OWNER_RE = re.compile(r"^담당:\s*@?([A-Za-z0-9-]+)\s*$", re.MULTILINE)


def parse_issues() -> list[dict]:
    issues = []
    for path in sorted(TASKS_DIR.glob("0*.md")):
        text = path.read_text(encoding="utf-8")
        parts = HEADING_RE.split(text)
        owner = OWNER_RE.search(parts[0])
        for title, body in zip(parts[1::2], parts[2::2], strict=True):
            labels: list[str] = []
            issue_owner = owner.group(1) if owner else None
            lines = []
            for line in body.strip().splitlines():
                if line.startswith("라벨:"):
                    labels = [label.strip() for label in line.removeprefix("라벨:").split(",") if label.strip()]
                elif m := OWNER_RE.match(line):  # 이슈마다 담당이 다르면 파일 맨 위 "담당:"보다 우선한다
                    issue_owner = m.group(1)
                else:
                    lines.append(line)
            body_text = "\n".join(lines).strip() + f"\n\n---\n출처: `docs/tasks/{path.name}`"
            issues.append({"title": title.strip(), "labels": labels, "body": body_text, "owner": issue_owner})
    return issues


class GitHub:
    """GITHUB_TOKEN이 있으면 REST API를 직접 부르고, 없으면 로그인된 gh CLI에 맡긴다."""

    def __init__(self, repo: str):
        self.repo = repo
        self.token = os.getenv("GITHUB_TOKEN")
        self.gh = shutil.which("gh") or next(
            (p for p in (r"C:\Program Files\GitHub CLI\gh.exe",) if Path(p).exists()), None)
        if not self.token and not self.gh:
            sys.exit("GitHub CLI(gh auth login) 또는 GITHUB_TOKEN 환경변수가 필요합니다.")

    def call(self, method: str, path: str, payload: dict | None = None) -> tuple[int, object]:
        if self.token:
            return self._rest(method, path, payload)
        return self._gh(method, path, payload)

    def _rest(self, method: str, path: str, payload: dict | None) -> tuple[int, object]:
        req = urllib.request.Request(
            f"https://api.github.com/{path}",
            method=method,
            data=json.dumps(payload).encode() if payload else None,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, json.loads(res.read() or b"{}")
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read() or b"{}")

    def _gh(self, method: str, path: str, payload: dict | None) -> tuple[int, object]:
        cmd = [self.gh, "api", "-X", method, "-i", path]
        if payload is not None:
            cmd += ["--input", "-"]
        res = subprocess.run(cmd, input=json.dumps(payload) if payload is not None else None,
                             capture_output=True, text=True, encoding="utf-8")
        head, _, body = res.stdout.replace("\r\n", "\n").partition("\n\n")
        match = re.match(r"HTTP/\S+ (\d+)", head)
        status = int(match.group(1)) if match else (0 if res.returncode else 200)
        try:
            return status, json.loads(body or "{}")
        except json.JSONDecodeError:
            return status, {"message": (res.stderr or body).strip()}

    def existing_issues(self) -> dict[str, dict]:
        """제목 → 이슈. PR은 빼고, 닫힌 이슈도 포함한다."""
        found: dict[str, dict] = {}
        page = 1
        while True:
            status, data = self.call("GET", f"repos/{self.repo}/issues?state=all&per_page=100&page={page}")
            if status != 200 or not isinstance(data, list):
                sys.exit(f"기존 이슈를 불러오지 못했습니다 ({status}): {data}")
            for item in data:
                if "pull_request" not in item:
                    found[item["title"]] = item
            if len(data) < 100:
                return found
            page += 1


def create(gh: GitHub, issues: list[dict]) -> None:
    existing = gh.existing_issues()
    for label in sorted({label for issue in issues for label in issue["labels"]}):
        status, _ = gh.call("POST", f"repos/{gh.repo}/labels", {"name": label, "color": "1f7a5a"})
        if status not in (201, 422):  # 422 = 이미 있음
            print(f"라벨 생성 실패: {label} ({status})")

    for issue in issues:
        if issue["title"] in existing:
            print(f"건너뜀 (이미 있음): {issue['title']}")
            continue
        payload = {k: issue[k] for k in ("title", "labels", "body")}
        status, data = gh.call("POST", f"repos/{gh.repo}/issues", payload)
        url = data.get("html_url", data) if isinstance(data, dict) else data
        print(f"{'생성' if status == 201 else '실패'} {status}: {issue['title']} {url}")


def assign(gh: GitHub, issues: list[dict]) -> None:
    """초대를 수락하지 않은 사람은 GitHub가 담당자로 받지 않으므로, 수락 후에 실행한다."""
    existing = gh.existing_issues()
    for issue in issues:
        found = existing.get(issue["title"])
        if not found or not issue["owner"]:
            print(f"건너뜀: {issue['title']} ({'이슈 없음' if not found else '담당 없음'})")
            continue
        if any(a["login"].lower() == issue["owner"].lower() for a in found.get("assignees", [])):
            continue
        status, data = gh.call("POST", f"repos/{gh.repo}/issues/{found['number']}/assignees",
                               {"assignees": [issue["owner"]]})
        assigned = isinstance(data, dict) and any(
            a["login"].lower() == issue["owner"].lower() for a in data.get("assignees", []))
        print(f"{'지정' if assigned else '실패'} {status}: #{found['number']} {issue['title']} → @{issue['owner']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", help="owner/name 형식의 저장소")
    parser.add_argument("--apply", action="store_true", help="실제로 이슈를 만든다")
    parser.add_argument("--assign", action="store_true", help="만들어진 이슈에 담당자를 지정한다")
    args = parser.parse_args()

    issues = parse_issues()
    for issue in issues:
        owner = f" @{issue['owner']}" if issue["owner"] else ""
        print(f"- {issue['title']}  [{', '.join(issue['labels'])}]{owner}")
    print(f"\n총 {len(issues)}개")
    if not (args.apply or args.assign):
        print("미리 보기입니다. 실제로 만들려면 --repo 와 --apply 를 붙이세요.")
        return
    if not args.repo:
        sys.exit("--repo 가 필요합니다.")

    gh = GitHub(args.repo)
    if args.apply:
        create(gh, issues)
    if args.assign:
        assign(gh, issues)


if __name__ == "__main__":
    main()
