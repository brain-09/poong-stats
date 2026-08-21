"""
[일회성 스크립트] 업로드받은 2026년 7월 로스터(data/members_2026_07.json)로 실제
풍고 API를 호출해서 2026년 7월 확정 데이터를 data/archive/2026-07.json 으로 저장한다.

이미 자동화된 fetch_data.py의 월 전환 로직으로는 놓친 과거 달을 나중에 수동으로
채워 넣을 때 쓰는 용도. 한 번 실행해서 data/archive/2026-07.json이 생기면,
그 뒤로는 이 스크립트도, data/members_2026_07.json도, 이 스크립트를 실행하는
GitHub Actions 워크플로우(.github/workflows/backfill-july.yml)도 전부 지워도 된다
(fetch_data.py는 archive 파일이 이미 있으면 절대 덮어쓰지 않으므로 안전하게 보존됨).

실행: python scripts/backfill_july.py
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_data import fetch_poonggo_monthly  # 기존 크롤링 로직 그대로 재사용

ROOT = Path(__file__).resolve().parent.parent
JULY_MEMBERS_PATH = ROOT / "data" / "members_2026_07.json"
ARCHIVE_DIR = ROOT / "data" / "archive"
OUT_PATH = ARCHIVE_DIR / "2026-07.json"

YEAR, MONTH = 2026, 7


def clean_birthdate(bd):
    if not bd or bd in ("체크", ""):
        return None
    return bd


def clean_role(role):
    return role if role else None


def main():
    if OUT_PATH.exists():
        print(f"[안내] {OUT_PATH} 가 이미 존재해서 아무것도 하지 않고 종료합니다.")
        return

    with open(JULY_MEMBERS_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    members = config["members"]
    ids = [m["id"] for m in members if m.get("id")]

    print(f"{YEAR}년 {MONTH}월 데이터 조회 중... ({len(ids)}명)")
    data_by_id = fetch_poonggo_monthly(YEAR, MONTH, ids)
    if data_by_id is None:
        raise SystemExit(f"[오류] {YEAR}년 {MONTH}월 데이터를 가져오지 못했습니다.")

    print(f"전체 {len(data_by_id)}명의 데이터 수신 완료")

    not_found = []
    out_members = []
    for m in members:
        member_id = m.get("id")
        d = data_by_id.get(member_id)
        if member_id and d is None:
            not_found.append(f"{m['nickname']}({member_id})")

        out_members.append({
            "id": member_id,
            "nickname": m["nickname"],
            "gender": m.get("gender", "m"),
            "birthdate": clean_birthdate(m.get("birthdate")),
            "role": clean_role(m.get("role")),
            "team": m.get("team"),
            "balloons": d["balloons"] if d else 0,
            "broadcast_seconds": d["broadcast_seconds"] if d else 0,
        })

    if not_found:
        print(
            f"[참고] 데이터가 없는 {len(not_found)}명은 0으로 처리됨: "
            + ", ".join(not_found[:20])
            + (" ..." if len(not_found) > 20 else "")
        )

    now = datetime.now(timezone.utc) + timedelta(hours=9)
    result = {
        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S") + " (수동 백필)",
        "year": YEAR,
        "month": MONTH,
        "members": out_members,
    }

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"완료: {OUT_PATH} 생성됨")


if __name__ == "__main__":
    main()
