"""
poong.today의 월간 전체 랭킹 API를 '한 번만' 호출해서, members.json에 등록된
멤버들의 이번달 별풍선 데이터를 뽑아 data/latest.json 으로 저장하는 스크립트.

기존에는 멤버 1명당 1번씩(243번) 요청했지만, /chart/get 엔드포인트가
poong.today에 등록된 전체 스트리머의 월간 데이터를 한 번에 반환하므로
그 안에서 우리 멤버 ID만 찾아서 쓰면 된다. 요청 횟수가 줄어서
차단(403) 위험도 낮아지고 훨씬 빠르다.

실행: python scripts/fetch_data.py
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

ROOT = Path(__file__).resolve().parent.parent
MEMBERS_PATH = ROOT / "data" / "members.json"
OUTPUT_PATH = ROOT / "data" / "latest.json"

CHART_API_URL = (
    "https://static.poong.today/chart/get"
    "?ctype=month&ks=false&year={year}&month={month}&day=undefined"
)

TIMEOUT_SEC = 30
MAX_RETRIES = 3


def kst_now():
    return datetime.now(timezone.utc) + timedelta(hours=9)


def fetch_chart(year: int, month: int) -> dict:
    url = CHART_API_URL.format(year=year, month=month)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://poong.today/",
        "Origin": "https://poong.today",
        "Accept": "application/json, text/plain, */*",
    }
    req = Request(url, headers=headers)

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urlopen(req, timeout=TIMEOUT_SEC) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except (URLError, HTTPError, TimeoutError) as e:
            last_err = e
            print(f"[경고] 전체 랭킹 요청 실패 (시도 {attempt}/{MAX_RETRIES}): {e}", file=sys.stderr)
        except json.JSONDecodeError as e:
            last_err = e
            print(f"[경고] 응답 파싱 실패 (시도 {attempt}/{MAX_RETRIES}): {e}", file=sys.stderr)

    raise SystemExit(f"[오류] 전체 랭킹 데이터를 가져오지 못했습니다: {last_err}")


def main():
    if not MEMBERS_PATH.exists():
        print(f"[오류] {MEMBERS_PATH} 파일이 없습니다.", file=sys.stderr)
        sys.exit(1)

    with open(MEMBERS_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    now = kst_now()
    year, month = now.year, now.month

    print(f"전체 랭킹 데이터 요청 중... ({year}년 {month}월)")
    chart = fetch_chart(year, month)

    # chart["b"] 는 [{"i": 아이디, "n": 닉네임, "b": 이번달 별풍선, ...}, ...] 형태
    balloon_by_id = {}
    for entry in chart.get("b", []):
        member_id = entry.get("i")
        if member_id:
            balloon_by_id[member_id] = entry.get("b", 0) or 0

    print(f"전체 {len(balloon_by_id)}명의 데이터 수신 완료")

    result = {
        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "year": year,
        "month": month,
        "teams": [],
    }

    not_found = []

    for team in config["teams"]:
        team_out = {"name": team["name"], "members": []}
        for m in team["members"]:
            member_id = m.get("id")
            balloons = balloon_by_id.get(member_id, 0) if member_id else 0
            if member_id and member_id not in balloon_by_id:
                not_found.append(f"{m['nickname']}({member_id})")

            team_out["members"].append({
                "id": member_id,
                "nickname": m["nickname"],
                "gender": m.get("gender", "m"),
                "birthdate": m.get("birthdate"),
                "role": m.get("role"),
                "balloons": balloons,
            })
        result["teams"].append(team_out)

    if not_found:
        print(
            f"[참고] 이번달 방송 기록이 없거나 랭킹에 없는 {len(not_found)}명은 0으로 처리됨: "
            + ", ".join(not_found[:20])
            + (" ..." if len(not_found) > 20 else ""),
            file=sys.stderr,
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"완료: {OUTPUT_PATH} 에 저장됨")


if __name__ == "__main__":
    main()
