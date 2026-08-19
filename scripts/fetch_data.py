"""
poong.today에서 members.json에 등록된 멤버들의 이번달 별풍선 데이터를 수집해서
data/latest.json 으로 저장하는 스크립트.
members.json에 있는 생일/직책 정보도 그대로 함께 실어 나른다 (표/생일란 렌더링용).

실행: python scripts/fetch_data.py
"""

import json
import time
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

ROOT = Path(__file__).resolve().parent.parent
MEMBERS_PATH = ROOT / "data" / "members.json"
OUTPUT_PATH = ROOT / "data" / "latest.json"

API_URL = "https://static.poong.today/bj/detail/get?id={id}&year={year}&month={month}"

REQUEST_DELAY_SEC = 0.5
MAX_RETRIES = 3
TIMEOUT_SEC = 10


def kst_now():
    return datetime.now(timezone.utc) + timedelta(hours=9)


def fetch_member_data(member_id: str, year: int, month: int):
    url = API_URL.format(id=member_id, year=year, month=month)
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urlopen(req, timeout=TIMEOUT_SEC) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except (URLError, HTTPError, TimeoutError) as e:
            print(f"  [경고] {member_id} 요청 실패 (시도 {attempt}/{MAX_RETRIES}): {e}", file=sys.stderr)
            time.sleep(1.0)
        except json.JSONDecodeError as e:
            print(f"  [경고] {member_id} 응답 파싱 실패: {e}", file=sys.stderr)
            return None
    return None


def main():
    if not MEMBERS_PATH.exists():
        print(f"[오류] {MEMBERS_PATH} 파일이 없습니다.", file=sys.stderr)
        sys.exit(1)

    with open(MEMBERS_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    now = kst_now()
    year, month = now.year, now.month

    result = {
        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "year": year,
        "month": month,
        "teams": [],
    }

    total_members = sum(len(t["members"]) for t in config["teams"])
    done = 0

    for team in config["teams"]:
        team_name = team["name"]
        print(f"[팀] {team_name} 처리 중...")
        team_out = {"name": team_name, "members": []}

        for m in team["members"]:
            done += 1
            member_id = m.get("id")
            print(f"  ({done}/{total_members}) {m['nickname']} ({member_id})")

            balloons = 0
            if member_id:
                data = fetch_member_data(member_id, year, month)
                if data:
                    balloons = data.get("b", 0) or 0
                else:
                    print("    -> 데이터 수집 실패, 0으로 처리", file=sys.stderr)
                time.sleep(REQUEST_DELAY_SEC)
            else:
                print("    -> SOOP ID 없음, 0으로 처리", file=sys.stderr)

            team_out["members"].append({
                "id": member_id,
                "nickname": m["nickname"],
                "gender": m.get("gender", "m"),
                "birthdate": m.get("birthdate"),
                "role": m.get("role"),
                "balloons": balloons,
            })

        result["teams"].append(team_out)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n완료: {OUTPUT_PATH} 에 저장됨")


if __name__ == "__main__":
    main()
