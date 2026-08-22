"""
누적시청자(cumulative_viewers) 지표를 fetch_data.py에 추가하기 전에 이미
data/archive/ 에 보관돼있던 과거 달 데이터는 이 필드가 없어서, generate_html.py의
normalize_balloons가 0으로 채워 넣는다. 이 스크립트는 그런 과거 아카이브 파일들을
대상으로 풍고 API를 다시 호출해 cumulative_viewers 값만 채워넣는 1회성 백필용이다.

풍고 API가 "최대 3개월까지 보관"이라고 안내하고 있어서, 그 기간을 벗어난 오래된
달은 데이터를 못 받아올 수 있다 - 그런 경우 경고만 출력하고 해당 파일은 건드리지
않는다.

기본적으로는 data/archive/ 안의 모든 파일 중 cumulative_viewers가 없는(=누락된)
멤버가 하나라도 있는 파일을 자동으로 찾아서 전부 백필한다. 특정 달만 하고 싶으면
--month YYYY-MM 옵션으로 지정.

실행: python scripts/backfill_cview.py
      python scripts/backfill_cview.py --month 2025-07
"""

import argparse
import json
import sys
from pathlib import Path

# fetch_data.py와 같은 폴더에 있다고 가정하고 재사용
from fetch_data import fetch_poonggo_monthly

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = ROOT / "data" / "archive"


def needs_backfill(data: dict) -> bool:
    """멤버 중 하나라도 cumulative_viewers 필드가 아예 없으면 백필 대상으로 간주.
    (필드가 있고 값이 0인 경우는 실제로 시청자가 0이었을 수도 있어 건드리지 않는다)"""
    return any("cumulative_viewers" not in m for m in data.get("members", []))


def backfill_file(path: Path) -> None:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    year, month = data.get("year"), data.get("month")
    if not year or not month:
        print(f"[건너뜀] {path.name}: year/month 정보가 없음", file=sys.stderr)
        return

    if not needs_backfill(data):
        print(f"[건너뜀] {path.name}: 이미 cumulative_viewers 있음")
        return

    ids = [m["id"] for m in data["members"] if m.get("id")]
    print(f"[백필] {year}년 {month}월 ({len(ids)}명) 풍고 API 재조회 중...")
    fetched = fetch_poonggo_monthly(year, month, ids)

    if fetched is None:
        print(f"[오류] {path.name}: API 조회 실패 - 건너뜀 (3개월 보관 기간을 넘겼을 수 있음)",
              file=sys.stderr)
        return

    updated = 0
    missing = []
    for m in data["members"]:
        member_id = m.get("id")
        if member_id and member_id in fetched:
            m["cumulative_viewers"] = fetched[member_id]["cumulative_viewers"]
            updated += 1
        else:
            m["cumulative_viewers"] = m.get("cumulative_viewers", 0)
            if member_id:
                missing.append(f"{m['nickname']}({member_id})")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[완료] {path.name}: {updated}명 채움" + (f", {len(missing)}명 데이터 없어 0 처리" if missing else ""))
    if missing:
        print("  없는 인원: " + ", ".join(missing[:20]) + (" ..." if len(missing) > 20 else ""), file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="과거 아카이브에 누적시청자 백필")
    parser.add_argument("--month", help="YYYY-MM 형식으로 특정 달만 백필 (예: 2025-07)")
    args = parser.parse_args()

    if not ARCHIVE_DIR.exists():
        raise SystemExit(f"[오류] {ARCHIVE_DIR} 가 없습니다.")

    if args.month:
        target = ARCHIVE_DIR / f"{args.month}.json"
        if not target.exists():
            raise SystemExit(f"[오류] {target} 가 없습니다.")
        backfill_file(target)
    else:
        files = sorted(ARCHIVE_DIR.glob("*.json"))
        if not files:
            print("아카이브 파일이 없습니다.")
            return
        for path in files:
            backfill_file(path)


if __name__ == "__main__":
    main()
