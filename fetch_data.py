"""
풍고(poonggo.com) 공식 API를 사용해서, members.json에 등록된 멤버들의 이번달
별풍선 합계와 방송시간(초)을 뽑아 data/latest.json 으로 저장하는 스크립트.

이 API는 풍고 운영진에게 정식으로 이용 허가를 받아 사용 중이며 (문의 회신 기준),
ids 파라미터에 아이디를 콤마로 최대 300개까지 묶어 한 번에 조회할 수 있다.
운영진 안내에 따라 별도 rate limit은 없지만 서버 부담을 줄이기 위해 자동 실행
주기(몇 시간에 1회) 자체를 캐싱/버퍼링 수단으로 삼고, 요청 횟수를 최소화한다
(멤버가 300명을 넘지 않는 한 이번달 조회는 딱 1번의 API 호출로 끝난다).

달이 바뀐 첫 실행에서는, 이전 달을 단순 복사하지 않고 그 달 기준으로 API를
한 번 더 호출해 확정된 별풍선 값으로 갱신한 뒤 data/archive/YYYY-MM.json 으로
보관한다.

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

POONGGO_MONTHLY_URL = "https://poonggo.com/api/monthly"
IDS_PER_REQUEST = 300  # 풍고 API가 허용하는 최대 아이디 개수

TIMEOUT_SEC = 30
MAX_RETRIES = 3
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# 풍고 쪽에서 요청을 구분할 수 있도록, 자동화된 요청임을 정직하게 밝히는 User-Agent
# (사전에 정식으로 이용 허가를 받은 상태이므로 브라우저로 위장하지 않음)
REQUEST_HEADERS = {
    "User-Agent": "poong-stats-bot/1.0 (+https://brain-09.github.io/poong-stats/)",
    "Accept": "application/json",
}


def _to_int(value) -> int:
    """풍고 API가 숫자를 문자열로 줄 수도 있어서, 어떤 형태로 오든 안전하게 정수로 변환.
    콤마가 섞여 있거나(예: "301,480") 비어있거나 None이어도 0으로 처리."""
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(str(value).replace(",", "").strip() or 0)
    except (ValueError, TypeError):
        return 0


def kst_now():
    return datetime.now(timezone.utc) + timedelta(hours=9)


def _chunked(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def fetch_poonggo_monthly(year: int, month: int, ids: list):
    """
    풍고 월별 API를 호출해 {SOOP아이디: {"balloons": 별풍선합계, "broadcast_seconds": 방송시간(초)}}
    딕셔너리를 반환한다. ids가 300개를 넘으면 여러 번 나눠서 호출한다. 실패 시 None 반환.
    """
    if not ids:
        return {}

    date_str = f"{year:04d}-{month:02d}-01"
    data_by_id = {}

    for chunk in _chunked(ids, IDS_PER_REQUEST):
        ids_param = ",".join(chunk)
        url = f"{POONGGO_MONTHLY_URL}?date={date_str}&ids={ids_param}"
        req = Request(url, headers=REQUEST_HEADERS)

        last_err = None
        parsed = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                with urlopen(req, timeout=TIMEOUT_SEC) as resp:
                    raw = resp.read().decode("utf-8")
                    parsed = json.loads(raw)
                    break
            except (URLError, HTTPError, TimeoutError) as e:
                last_err = e
                print(f"[경고] 풍고 API 요청 실패 (시도 {attempt}/{MAX_RETRIES}): {e}", file=sys.stderr)
            except json.JSONDecodeError as e:
                last_err = e
                print(f"[경고] 풍고 API 응답 파싱 실패 (시도 {attempt}/{MAX_RETRIES}): {e}", file=sys.stderr)

        if parsed is None:
            print(f"[오류] 풍고 API 조회 실패 ({date_str}, {len(chunk)}명분): {last_err}", file=sys.stderr)
            return None

        # 응답이 배열이거나, {"data": [...]} 같은 형태로 감싸져 있을 수 있어 둘 다 처리
        entries = parsed if isinstance(parsed, list) else parsed.get("data", parsed.get("list", []))

        for entry in entries:
            member_id = entry.get("id")
            if member_id:
                data_by_id[member_id] = {
                    "balloons": _to_int(entry.get("amt")),
                    "broadcast_seconds": _to_int(entry.get("broadTime")),
                }

    return data_by_id


def archive_previous_month_if_needed(new_year: int, new_month: int, all_ids: list):
    """
    기존 data/latest.json이 있고, 그 안의 연/월이 이번에 새로 가져올 연/월과 다르면
    (=달이 바뀌었으면) 그 이전 달을 보관한다.

    풍고 데이터가 월말 이후 갱신될 가능성에 대비해, 단순히 마지막 스냅샷을 복사하지
    않고 지난달 기준으로 API를 한 번 더 호출해 확정된 별풍선 값으로 갱신한 뒤 보관한다.
    팀/성별/직책 등 '그 당시 소속 정보'는 기존 스냅샷 값을 그대로 유지한다.
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
    data_by_id = fetch_poonggo_monthly(prev_year, prev_month, all_ids)

    if data_by_id is not None:
        updated_count = 0
        for m in prev.get("members", []):
            member_id = m.get("id")
            if member_id and member_id in data_by_id:
                new_data = data_by_id[member_id]
                if new_data["balloons"] != m.get("balloons") or new_data["broadcast_seconds"] != m.get("broadcast_seconds"):
                    updated_count += 1
                m["balloons"] = new_data["balloons"]
                m["broadcast_seconds"] = new_data["broadcast_seconds"]
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
    all_ids = [m["id"] for m in members if m.get("id")]

    now = kst_now()
    year, month = now.year, now.month

    archive_previous_month_if_needed(year, month, all_ids)

    print(f"풍고 API 요청 중... ({year}년 {month}월, {len(all_ids)}명)")
    data_by_id = fetch_poonggo_monthly(year, month, all_ids)
    if data_by_id is None:
        raise SystemExit(f"[오류] {year}년 {month}월 데이터를 가져오지 못했습니다.")

    print(f"전체 {len(data_by_id)}명의 데이터 수신 완료")

    not_found = []
    out_members = []

    for m in members:
        member_id = m.get("id")
        member_data = data_by_id.get(member_id) if member_id else None
        if member_id and member_data is None:
            not_found.append(f"{m['nickname']}({member_id})")

        out_members.append({
            "id": member_id,
            "nickname": m["nickname"],
            "gender": m.get("gender", "m"),
            "birthdate": m.get("birthdate"),
            "role": m.get("role"),
            "team": m.get("team"),
            "balloons": member_data["balloons"] if member_data else 0,
            "broadcast_seconds": member_data["broadcast_seconds"] if member_data else 0,
        })

    if not_found:
        print(
            f"[참고] 이번달 데이터가 없는 {len(not_found)}명은 0으로 처리됨: "
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
