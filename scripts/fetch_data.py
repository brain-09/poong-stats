"""
poong.today의 월간 전체 랭킹 API를 '한 번만' 호출해서, members.json에 등록된
멤버들의 이번달 별풍선 데이터를 뽑아 data/latest.json 으로 저장하는 스크립트.

달이 바뀐 첫 실행에서는, 이전 달을 단순 복사하지 않고 그 달 기준으로 API를
한 번 더 호출해 확정된 별풍선 값으로 갱신한 뒤 data/archive/YYYY-MM.json 으로
보관한다 (풍투데이가 월말 데이터를 다음 달 초에 한 번 더 갱신하는 경우 대응).

members.json은 flat 구조: {"members": [{"id":.., "team":.., ...}, ...]}

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
ARCHIVE_DIR = ROOT / "data" / "archive"

CHART_API_URL = (
    "https://static.poong.today/chart/get"
    "?ctype=month&ks=false&year={year}&month={month}&day=undefined"
)

TIMEOUT_SEC = 30
MAX_RETRIES = 3
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def kst_now():
    return datetime.now(timezone.utc) + timedelta(hours=9)


def fetch_chart(year: int, month: int):
    """성공 시 dict, 모든 재시도 실패 시 None 반환 (호출부에서 실패 처리 방식을 다르게 가져가기 위함)"""
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
            print(f"[경고] {year}년 {month}월 랭킹 요청 실패 (시도 {attempt}/{MAX_RETRIES}): {e}", file=sys.stderr)
        except json.JSONDecodeError as e:
            last_err = e
            print(f"[경고] {year}년 {month}월 응답 파싱 실패 (시도 {attempt}/{MAX_RETRIES}): {e}", file=sys.stderr)

    print(f"[오류] {year}년 {month}월 랭킹 데이터를 가져오지 못했습니다: {last_err}", file=sys.stderr)
    return None


def chart_to_balloon_map(chart: dict) -> dict:
    balloon_by_id = {}
    for entry in chart.get("b", []):
        member_id = entry.get("i")
        if member_id:
            balloon_by_id[member_id] = entry.get("b", 0) or 0
    return balloon_by_id


def archive_previous_month_if_needed(new_year: int, new_month: int):
    """
    기존 data/latest.json이 있고, 그 안의 연/월이 이번에 새로 가져올 연/월과 다르면
    (=달이 바뀌었으면) 그 이전 달을 보관한다.

    풍투데이는 월말 데이터를 다음 달 초에 한 번 더 갱신(확정)하는 경우가 있어서,
    단순히 마지막 스냅샷을 복사하지 않고 지난달 기준으로 API를 한 번 더 호출해
    확정된 별풍선 값으로 갱신한 뒤 보관한다. 팀/성별/직책 등 '그 당시 소속 정보'는
    기존 스냅샷 값을 그대로 유지한다 (재조회 API는 별풍선 숫자만 알려주기 때문).
    """
    if not OUTPUT_PATH.exists():
        return

    try:
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            prev = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[경고] 이전 데이터를 읽지 못해 보관을 건너뜀: {e}", file=sys.stderr)
        return

    prev_year, prev_month = prev.get("year"), prev.get("month")
    if not prev_year or not prev_month:
        return
    if (prev_year, prev_month) == (new_year, new_month):
        return  # 같은 달이면 보관할 필요 없음

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = ARCHIVE_DIR / f"{prev_year:04d}-{prev_month:02d}.json"
    if archive_path.exists():
        return  # 이미 보관 완료된 달이면 다시 건드리지 않음

    print(f"[보관] {prev_year}년 {prev_month}월 확정 데이터 재조회 중...")
    chart = fetch_chart(prev_year, prev_month)

    if chart is not None:
        balloon_by_id = chart_to_balloon_map(chart)
        updated_count = 0
        for m in prev.get("members", []):
            member_id = m.get("id")
            if member_id and member_id in balloon_by_id:
                new_value = balloon_by_id[member_id]
                if new_value != m.get("balloons"):
                    updated_count += 1
                m["balloons"] = new_value
        prev["updated_at"] = kst_now().strftime(DATETIME_FORMAT) + " (말일 확정치)"
        print(f"[보관] 확정치로 갱신된 인원: {updated_count}명")
    else:
        print(f"[경고] {prev_year}년 {prev_month}월 확정 데이터 재조회 실패 - 마지막 스냅샷 값을 그대로 보관합니다.", file=sys.stderr)

    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(prev, f, ensure_ascii=False, indent=2)
    print(f"[보관] {prev_year}년 {prev_month}월 데이터를 {archive_path} 로 보관함")


def main():
    if not MEMBERS_PATH.exists():
        print(f"[오류] {MEMBERS_PATH} 파일이 없습니다.", file=sys.stderr)
        sys.exit(1)

    with open(MEMBERS_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    members = config["members"]

    now = kst_now()
    year, month = now.year, now.month

    archive_previous_month_if_needed(year, month)

    print(f"전체 랭킹 데이터 요청 중... ({year}년 {month}월)")
    chart = fetch_chart(year, month)
    if chart is None:
        raise SystemExit(f"[오류] {year}년 {month}월 전체 랭킹 데이터를 가져오지 못했습니다.")

    balloon_by_id = chart_to_balloon_map(chart)

    print(f"전체 {len(balloon_by_id)}명의 데이터 수신 완료")

    not_found = []
    out_members = []

    for m in members:
        member_id = m.get("id")
        balloons = balloon_by_id.get(member_id, 0) if member_id else 0
        if member_id and member_id not in balloon_by_id:
            not_found.append(f"{m['nickname']}({member_id})")

        out_members.append({
            "id": member_id,
            "nickname": m["nickname"],
            "gender": m.get("gender", "m"),
            "birthdate": m.get("birthdate"),
            "role": m.get("role"),
            "team": m.get("team"),
            "balloons": balloons,
        })

    if not_found:
        print(
            f"[참고] 이번달 방송 기록이 없거나 랭킹에 없는 {len(not_found)}명은 0으로 처리됨: "
            + ", ".join(not_found[:20])
            + (" ..." if len(not_found) > 20 else ""),
            file=sys.stderr,
        )

    result = {
        "updated_at": now.strftime(DATETIME_FORMAT),
        "year": year,
        "month": month,
        "members": out_members,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"완료: {OUTPUT_PATH} 에 저장됨")


if __name__ == "__main__":
    main()
