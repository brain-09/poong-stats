# poong-stats

풍투데이(poong.today)에서 팀별 멤버들의 이번 달 별풍선 데이터를 6시간마다 자동으로
가져와서 표 페이지(`docs/index.html`)를 갱신하는 프로젝트입니다. 달이 바뀌면 그 이전
달 데이터는 자동으로 보관되어 `docs/archive/YYYY-MM.html`에서 볼 수 있고,
`SINGLE_TEAM_PAGES`에 지정한 팀은 `docs/teams/`에 그 팀만 담은 단독 페이지도 생성됩니다.

## 폴더 구조

```
poong-stats/
├── data/
│   ├── members.json      ← 팀-멤버 목록 (직접 관리하는 파일)
│   ├── latest.json        ← 이번 달 크롤링 결과 (자동 생성)
│   └── archive/
│       └── YYYY-MM.json   ← 지난 달들의 스냅샷 (자동 생성, 그 당시 팀 구성 그대로 보존)
├── scripts/
│   ├── fetch_data.py      ← poong.today API 호출 + 월 전환 시 확정치 재조회 후 보관
│   └── generate_html.py   ← latest.json/archive → index/archive/teams html 생성
├── docs/
│   ├── index.html         ← 이번 달 전체 표 (GitHub Pages가 이 폴더를 서빙)
│   ├── archive/
│   │   └── YYYY-MM.html   ← 지난 달 전체 표
│   ├── teams/
│   │   ├── {팀이름}.html            ← 팀 단독 페이지 (이번 달)
│   │   └── {팀이름}__YYYY-MM.html   ← 팀 단독 페이지 (지난 달)
│   └── logos/
│       └── {팀이름}.webp  ← 팀 로고 (있으면 자동 표시, 없으면 텍스트만)
└── .github/workflows/
    └── update.yml          ← 6시간마다 자동 실행 설정
```

## 과거 데이터는 어떻게 보존되나요

`members.json`은 팀/인원이 계속 바뀌는 파일이라, 단순히 "그때의 별풍선 숫자"만 저장하면
나중에 "그때는 누가 어느 팀이었는지"를 알 수 없게 됩니다. 그래서 `fetch_data.py`는
매번 실행될 때 이번 달 멤버 각각의 **팀/성별/직책/생일까지 통째로** `data/latest.json`에
같이 저장합니다.

달이 바뀌는 시점(예: 8월→9월로 넘어가는 첫 실행)에는, 마지막 스냅샷을 그냥 복사하지 않고
**그 달(8월) 기준으로 API를 한 번 더 호출**해 확정된 별풍선 값으로 갱신한 뒤
`data/archive/2026-08.json`으로 보관합니다 (풍투데이가 월말 데이터를 다음 달 초에
한 번 더 갱신하는 경우가 있어서). 팀/성별/직책 등 "그 당시 소속 정보"는 재조회 API가
알려주지 않으므로 기존 스냅샷 값을 그대로 유지합니다.

## 팀별 순위와 전달 대비 변동

전체 페이지에서 각 팀은 "전체 평균" 기준으로 정렬되고, 팀 이름 옆에 전달 대비
순위 변동이 함께 표시됩니다 (▲상승 / ▼하락 / - 동일 / NEW 신규). 비교할 전달 데이터가
아직 없으면(아카이브가 없으면) 표시되지 않습니다.

## 팀별 단독 페이지 (`docs/teams/`)

`scripts/generate_html.py` 상단의 `SINGLE_TEAM_PAGES` 리스트에 있는 팀만
`docs/teams/{팀이름}.html` (이번 달) + `docs/teams/{팀이름}__YYYY-MM.html` (지난 달)로
따로 생성됩니다. 다른 팀도 단독 페이지가 필요하면 이 리스트에 이름만 추가하면 됩니다.

```python
SINGLE_TEAM_PAGES = ["캄몬스타즈"]
```

## 팀 로고 (`docs/logos/`)

`docs/logos/{팀이름}.webp` 파일이 있으면 표 상단 팀 이름 옆에 자동으로 로고가 붙습니다.
파일명은 `members.json`의 `team` 값과 정확히 일치해야 합니다. 파일이 없는 팀은
그냥 텍스트만 표시되며 오류가 나지 않습니다.

## 최초 설정 (한 번만 하면 됨)

### 1. 이 폴더 전체를 GitHub 저장소(poong-stats)에 업로드

로컬에 git이 있다면:
```bash
cd poong-stats
git init
git add .
git commit -m "init"
git branch -M main
git remote add origin https://github.com/본인아이디/poong-stats.git
git push -u origin main
```

또는 GitHub 웹사이트에서 "Add file → Upload files"로 폴더 내용을 그대로 드래그해서 올려도 됩니다.
(`.github` 폴더는 숨김 폴더라 드래그 업로드 시 누락되기 쉬우니, GitHub 웹의
"Create new file"에서 `.github/workflows/update.yml` 경로로 직접 만드는 것도 방법입니다.)

### 2. GitHub Pages 활성화

1. 저장소 → **Settings** → **Pages**
2. **Source**를 `Deploy from a branch`로 설정
3. Branch: `main`, 폴더: `/docs` 선택 후 저장
4. 몇 분 후 `https://본인아이디.github.io/poong-stats/` 로 접속 가능

### 3. 워크플로우 쓰기 권한 확인

1. 저장소 → **Settings** → **Actions** → **General**
2. 맨 아래 **Workflow permissions**에서 **Read and write permissions** 선택 후 저장
   (이게 없으면 Actions가 자동으로 커밋/푸시를 못 합니다)

## 멤버 관리 (팀/인원이 바뀔 때)

`data/members.json`은 flat 구조입니다. 멤버 한 명이 배열의 항목 하나이고,
그 안에 `team` 필드로 소속을 표시합니다.

```json
{
  "members": [
    {
      "id": "poong.today의 SOOP ID",
      "nickname": "표시할 닉네임",
      "gender": "m 또는 f",
      "birthdate": "YYYY-MM-DD (모르면 null)",
      "role": "수장 / 전력외 (없으면 이 줄 자체를 생략 가능)",
      "team": "소속 팀 이름"
    }
  ]
}
```

- `id`는 `https://poong.today/broadcast/여기부분` 의 마지막 부분(SOOP ID)입니다.
- `role`이 `수장` 또는 `전력외`인 사람은 표에서 빨간 배경으로 표시되고, 팀 합계/평균/상위% 계산에서 제외됩니다.
- 이 팀에 새로 추가된 사람/팀은 전체 페이지에 **자동으로** 반영됩니다. 단, `docs/teams/` 단독 페이지가 필요하면 `SINGLE_TEAM_PAGES`에 별도로 추가해야 합니다.
- `birthdate`는 이름 옆 🎂 표시에 쓰입니다. 모르면 `null`.
- 수정 후 GitHub에 커밋/푸시하면 다음 자동 실행(또는 수동 실행) 때부터 반영됩니다.
- **이미 지나간 과거 달의 페이지(`docs/archive/*.html`, `docs/teams/*__YYYY-MM.html`)는 이 파일을 고쳐도 영향받지 않습니다** — 과거 데이터는 각 시점의 스냅샷(`data/archive/*.json`)에서만 읽어오기 때문입니다.

## 수동으로 즉시 갱신하고 싶을 때

저장소 → **Actions** 탭 → **Update poong stats** 워크플로우 선택 → **Run workflow** 버튼

## 와이고수 게시글에 넣는 법

와이고수 에디터가 `<iframe>` 태그를 그대로 두면:
```html
<iframe src="https://본인아이디.github.io/poong-stats/" width="100%" height="2000" frameborder="0"></iframe>
```

에디터가 iframe을 필터링해서 지워버리는 경우, `srcdoc` + meta refresh로 우회할 수 있습니다:
```html
<div style="max-width:1000px;margin:20px auto;">
  <iframe width="100%" height="1000" frameborder="0" scrolling="no" srcdoc="&lt;meta http-equiv='refresh' content='0;url=https://본인아이디.github.io/poong-stats/'&gt;"></iframe>
</div>
```

특정 팀 하나만 올리고 싶으면 URL을 그 팀 페이지로 바꾸면 됩니다:
```
url=https://본인아이디.github.io/poong-stats/teams/캄몬스타즈.html
```

높이는 팀 개수/레이아웃에 맞게 조절하세요.

## 로컬 테스트

```bash
python scripts/fetch_data.py
python scripts/generate_html.py
# docs/index.html, docs/archive/*.html, docs/teams/*.html 을 브라우저로 열어서 확인
```

## 참고

- 데이터 출처: poong.today (`static.poong.today/chart/get` 월간 전체 랭킹 API, 1회 호출로 전체 멤버 처리)
- 별풍선 값이 0이거나 직책이 수장/전력외인 멤버는 팀 합계·평균·상위 1%/5%/10% 계산에서 제외됩니다.
- 실행 주기는 KST 기준 오전 9시 / 오후 3시 / 오후 9시 / 새벽 3시 (6시간마다)입니다.
