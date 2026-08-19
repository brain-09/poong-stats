"""
data/latest.json 을 읽어서 docs/index.html 로 렌더링하는 스크립트.

반영된 사항:
- flat 멤버 구조(team 필드로 소속 표시)를 팀별로 묶어서 렌더링
- 직책이 '수장'/'전력외'인 사람은 합계·평균 계산에서 제외 + 빨간 배경 하이라이트
- 팀 카드는 '전체 평균' 내림차순으로 정렬
- 폰트/가운데정렬 등 디자인 개선
- 상단에는 '오늘' 생일자만, 표의 이름 옆에는 '이번 달' 생일이면 작은 표시
- 전체 멤버 중 상위 1% / 5% / 10% 별풍선 값을 배경색으로 하이라이트

실행: python scripts/generate_html.py
"""

import json
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "latest.json"
OUTPUT_PATH = ROOT / "docs" / "index.html"

EXCLUDED_ROLES = {"수장", "전력외"}


def fmt(n: int) -> str:
    return f"{n:,}"


def kst_today():
    return (datetime.now(timezone.utc) + timedelta(hours=9)).date()


def parse_birthdate(bd):
    if not bd:
        return None
    try:
        parts = bd.split("-")
        return int(parts[1]), int(parts[2])
    except (IndexError, ValueError):
        return None


def compute_percentile_tiers(members: list):
    """별풍선 값 기준 상위 1% / 5% / 10%에 해당하는 멤버의 id(nickname+team)를 반환"""
    ranked = sorted(members, key=lambda m: -m["balloons"])
    n = len(ranked)
    if n == 0:
        return {}, {}, {}

    top1_n = max(1, round(n * 0.01))
    top5_n = max(1, round(n * 0.05))
    top10_n = max(1, round(n * 0.10))

    tiers = {}
    for idx, m in enumerate(ranked):
        key = (m["nickname"], m["team"])
        if idx < top1_n:
            tiers[key] = "tier1"
        elif idx < top5_n:
            tiers[key] = "tier5"
        elif idx < top10_n:
            tiers[key] = "tier10"
    return tiers


def build_today_birthday_section(members: list, today):
    todays = [m for m in members if parse_birthdate(m.get("birthdate")) == (today.month, today.day)]
    if not todays:
        return ""
    items = "".join(
        f"<span class='bday-item'>🎉 <b>{m['nickname']}</b> <small>({m['team']})</small></span>"
        for m in todays
    )
    return f"""
    <div class="birthday-box">
      <div class="birthday-title">🎂 오늘 생일</div>
      <div class="birthday-list">{items}</div>
    </div>
    """


def build_team_card(team_name: str, members: list, current_month: int, tiers: dict):
    counted = [m for m in members if m.get("role") not in EXCLUDED_ROLES]
    males_counted = [m for m in counted if m["gender"] == "m"]
    females_counted = [m for m in counted if m["gender"] == "f"]

    male_sum = sum(m["balloons"] for m in males_counted)
    female_sum = sum(m["balloons"] for m in females_counted)
    total_sum = male_sum + female_sum
    male_avg = round(male_sum / len(males_counted)) if males_counted else 0
    female_avg = round(female_sum / len(females_counted)) if females_counted else 0
    total_avg = round(total_sum / len(counted)) if counted else 0

    males_all = sorted([m for m in members if m["gender"] == "m"], key=lambda x: -x["balloons"])
    females_all = sorted([m for m in members if m["gender"] == "f"], key=lambda x: -x["balloons"])

    def name_label(m):
        role = m.get("role")
        role_html = f"<span class='role'>{role}</span>" if role else ""
        bday = parse_birthdate(m.get("birthdate"))
        bday_html = "🎂" if bday and bday[0] == current_month else ""
        return f"{m['nickname']} {role_html} {bday_html}".strip()

    def value_class(m):
        classes = []
        if m.get("role") in EXCLUDED_ROLES:
            classes.append("excluded")
        tier = tiers.get((m["nickname"], m["team"]))
        if tier:
            classes.append(tier)
        return " ".join(classes)

    def rows(lst):
        if not lst:
            return "<tr><td colspan='2' class='empty'>-</td></tr>"
        out = []
        for m in lst:
            cls = value_class(m)
            out.append(
                f"<tr><td>{name_label(m)}</td>"
                f"<td class='num {cls}'>{fmt(m['balloons'])}</td></tr>"
            )
        return "".join(out)

    return total_avg, f"""
    <div class="team-card">
      <div class="team-title">{team_name} <span class="team-avg">전체평균 {fmt(total_avg)}</span></div>
      <div class="table-pair">
        <table>
          <thead><tr><th>남 멤버</th><th>별풍선</th></tr></thead>
          <tbody>{rows(males_all)}</tbody>
        </table>
        <table>
          <thead><tr><th>여 멤버</th><th>별풍선</th></tr></thead>
          <tbody>{rows(females_all)}</tbody>
        </table>
      </div>
      <table class="summary">
        <tr><td>남자 합계</td><td class="num">{fmt(male_sum)}</td><td>여자 합계</td><td class="num">{fmt(female_sum)}</td></tr>
        <tr><td>남자 평균</td><td class="num">{fmt(male_avg)}</td><td>여자 평균</td><td class="num">{fmt(female_avg)}</td></tr>
        <tr><td>전체 합계</td><td class="num total">{fmt(total_sum)}</td><td>전체 평균</td><td class="num total">{fmt(total_avg)}</td></tr>
        <tr><td>인원</td><td colspan="3">총 {len(members)}명 (집계 {len(counted)}명 · 수장/전력외 제외)</td></tr>
      </table>
    </div>
    """


def main():
    if not DATA_PATH.exists():
        raise SystemExit(f"[오류] {DATA_PATH} 가 없습니다. 먼저 fetch_data.py를 실행하세요.")

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    members = data["members"]
    today = kst_today()

    teams = OrderedDict()
    for m in members:
        teams.setdefault(m.get("team", "미분류"), []).append(m)

    tiers = compute_percentile_tiers(members)

    team_cards = []
    for team_name, team_members in teams.items():
        avg, html = build_team_card(team_name, team_members, data["month"], tiers)
        team_cards.append((avg, html))

    # 전체 평균 내림차순 정렬
    team_cards.sort(key=lambda x: -x[0])
    cards_html = "".join(html for _, html in team_cards)

    birthday_html = build_today_birthday_section(members, today)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>팀별 별풍선 랭킹</title>
<style>
  @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');

  * {{ box-sizing: border-box; }}

  body {{
    font-family: 'Pretendard', -apple-system, "Malgun Gothic", sans-serif;
    background: #f2f3f5;
    margin: 0;
    padding: 24px 16px;
    color: #222;
  }}
  .header {{
    display: flex;
    justify-content: center;
    gap: 24px;
    max-width: 1240px;
    margin: 0 auto 16px;
    font-size: 13px;
    color: #888;
    text-align: center;
  }}
  .birthday-box {{
    max-width: 1240px;
    margin: 0 auto 20px;
    background: linear-gradient(135deg, #fff4d6, #ffe9ec);
    border: 1px solid #f2cf8a;
    border-radius: 10px;
    padding: 12px 18px;
    text-align: center;
  }}
  .birthday-title {{
    font-weight: 700;
    margin-bottom: 6px;
    font-size: 15px;
  }}
  .birthday-list {{
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 6px 18px;
    font-size: 13px;
  }}
  .bday-item small {{ color: #999; }}

  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(440px, 1fr));
    gap: 18px;
    max-width: 1240px;
    margin: 0 auto;
  }}
  .team-card {{
    background: #fff;
    border: 1px solid #e5e6ea;
    border-radius: 12px;
    padding: 14px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }}
  .team-title {{
    font-weight: 700;
    text-align: center;
    background: #2f3542;
    color: #fff;
    padding: 10px;
    margin: -14px -14px 10px -14px;
    border-radius: 12px 12px 0 0;
    font-size: 16px;
    letter-spacing: 0.3px;
  }}
  .team-avg {{
    font-weight: 400;
    font-size: 12px;
    color: #cfd3e0;
    margin-left: 6px;
  }}
  .table-pair {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12.5px;
  }}
  th, td {{
    border: 1px solid #eceef1;
    padding: 5px 6px;
    text-align: center;
  }}
  th {{
    background: #f7f8fa;
    font-weight: 600;
    color: #555;
  }}
  td.num {{
    text-align: right;
    font-variant-numeric: tabular-nums;
    font-weight: 500;
  }}
  td.empty {{ color: #bbb; }}

  .role {{
    font-size: 10px;
    color: #d34c4c;
    border: 1px solid #f0a8a8;
    border-radius: 3px;
    padding: 0 3px;
    margin-left: 2px;
  }}

  td.excluded {{
    background: #fdeaea !important;
    color: #c0392b;
    font-weight: 700;
  }}
  td.tier1 {{ background: #ffd54f; }}
  td.tier5 {{ background: #ffe9a8; }}
  td.tier10 {{ background: #fff6dc; }}
  td.excluded.tier1, td.excluded.tier5, td.excluded.tier10 {{
    background: #fdeaea !important;
  }}

  table.summary {{ margin-top: 8px; }}
  table.summary td {{ font-size: 12px; text-align: center; }}
  table.summary td.total {{ font-weight: 700; background: #eef2ff; }}

  .legend {{
    max-width: 1240px;
    margin: 14px auto 0;
    font-size: 11.5px;
    color: #888;
    text-align: center;
  }}
  .legend span {{ margin: 0 8px; }}
  .legend .sw {{
    display: inline-block;
    width: 10px; height: 10px;
    border-radius: 2px;
    margin-right: 3px;
    vertical-align: middle;
  }}
</style>
</head>
<body>
  <div class="header">
    <span>업데이트: {data['updated_at']} (KST)</span>
    <span>{data['year']}년 {data['month']}월 기준</span>
  </div>
  {birthday_html}
  <div class="grid">
    {cards_html}
  </div>
  <div class="legend">
    <span><span class="sw" style="background:#ffd54f;"></span>상위 1%</span>
    <span><span class="sw" style="background:#ffe9a8;"></span>상위 5%</span>
    <span><span class="sw" style="background:#fff6dc;"></span>상위 10%</span>
    <span><span class="sw" style="background:#fdeaea;"></span>수장/전력외 (집계 제외)</span>
    <span>🎂 이번 달 생일</span>
  </div>
</body>
</html>
"""

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"완료: {OUTPUT_PATH} 생성됨")


if __name__ == "__main__":
    main()
