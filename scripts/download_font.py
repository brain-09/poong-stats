"""
docs/fonts/PretendardVariable.woff2 파일을 최초 1회만 CDN에서 받아 레포 안에
self-host해두는 스크립트. 이미 파일이 있으면 아무것도 안 하고 바로 종료하므로
4시간마다 도는 워크플로우에서 매번 실행돼도 안전하다 (실제 다운로드는 딱 1번뿐).

CDN 링크를 <link>로 직접 거는 대신 폰트 파일을 레포에 넣어 같은 도메인(GitHub
Pages)에서 서빙하면, 외부 CDN 왕복 시간이 없어져서 페이지 로드시 폰트가 늦게
적용되며 깜빡이는 현상(FOUT)이 크게 줄어든다.

폰트 파일의 정확한 경로를 하드코딩하지 않고, 공식 CSS 파일 안에서 실제 파일
경로를 정규식으로 뽑아 상대경로 -> 절대 URL로 변환해서 받는다. Pretendard
배포 구조가 모노레포라 버전이 바뀌면 경로가 달라질 수 있는데, 이렇게 하면
CDN이 실제로 안내하는 경로를 그대로 따라가므로 버전이 바뀌어도(CSS_URL의
버전 태그만 맞으면) 안전하게 최신 파일을 받는다.

실행: python scripts/download_font.py
"""

import re
import sys
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "docs" / "fonts"
FONT_PATH = FONT_DIR / "PretendardVariable.woff2"
CSS_URL = "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css"
HEADERS = {"User-Agent": "poong-stats-bot/1.0 (+https://brain-09.github.io/poong-stats/)"}
TIMEOUT_SEC = 30


def main():
    if FONT_PATH.exists():
        print(f"[건너뜀] {FONT_PATH} 이미 있음 - 다운로드 생략")
        return

    print(f"[조회] {CSS_URL} 에서 실제 폰트 파일 경로 확인 중...")
    req = Request(CSS_URL, headers=HEADERS)
    with urlopen(req, timeout=TIMEOUT_SEC) as resp:
        css = resp.read().decode("utf-8")

    match = re.search(r"url\(['\"]?([^'\")]+\.woff2)['\"]?\)", css)
    if not match:
        print("[오류] CSS 안에서 .woff2 경로를 찾지 못함 - Pretendard 배포 구조가 바뀐 것 같음",
              file=sys.stderr)
        sys.exit(1)

    font_url = urljoin(CSS_URL, match.group(1))
    print(f"[다운로드] {font_url}")

    req2 = Request(font_url, headers=HEADERS)
    with urlopen(req2, timeout=TIMEOUT_SEC) as resp:
        font_bytes = resp.read()

    if len(font_bytes) < 10_000:
        # 정상적인 가변폰트 파일이면 최소 수백 KB는 되어야 함 - 너무 작으면
        # HTML 에러 페이지 같은 걸 잘못 받은 것일 가능성이 높아 저장을 막는다.
        print(f"[오류] 받은 파일이 너무 작음 ({len(font_bytes)} bytes) - 저장하지 않음",
              file=sys.stderr)
        sys.exit(1)

    FONT_DIR.mkdir(parents=True, exist_ok=True)
    with open(FONT_PATH, "wb") as f:
        f.write(font_bytes)
    print(f"[완료] {FONT_PATH} 저장됨 ({len(font_bytes):,} bytes)")


if __name__ == "__main__":
    main()
