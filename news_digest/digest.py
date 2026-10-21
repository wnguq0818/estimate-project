"""상속·증여·세금·부동산 정책 뉴스 브리핑 생성기.

Google 뉴스 RSS(와 키가 있으면 네이버 뉴스 검색 API)로 최근 기사를 모으고,
중요한 3~5건을 골라 카카오톡 오픈채팅방에 붙여넣을 메시지(digest.md)를 만든다.

환경 변수
  NAVER_CLIENT_ID, NAVER_CLIENT_SECRET  (선택) NAVER API HUB 애플리케이션의 Client ID / Secret
  ANTHROPIC_API_KEY                     (선택) 있으면 Claude가 기사 선별·요약
  LOOKBACK_HOURS                        (선택) 수집 기간, 기본 24시간
  OUTPUT_PATH                           (선택) 결과 파일 경로, 기본 digest.md
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime

KST = timezone(timedelta(hours=9))
WEEKDAYS = "월화수목금토일"

# 뉴스 검색어. 검색 출처마다 검색어별로 최근 기사를 가져온다.
QUERIES = [
    "상속세",
    "증여세",
    "종부세",
    "양도세",
    "취득세 부동산",
    "재산세 주택",
    "부동산 대책",
    "부동산 정책",
    "세법개정안",
    "세제개편",
]

# 제목에 들어 있으면 점수를 주는 단어 (규칙 기반 선별용)
TITLE_WEIGHTS = {
    "상속": 3, "증여": 3, "종부세": 3, "종합부동산세": 3, "양도세": 3, "양도소득세": 3,
    "세법": 2, "세제": 2, "취득세": 2, "재산세": 2, "공시가": 2,
    "대책": 2, "정부": 1, "국토부": 1, "국토교통부": 1, "기재부": 1, "재정경제부": 1,
    "국회": 1, "개정": 1, "부동산": 1, "주택": 1,
}

# 광고·홍보성 기사 제외용
EXCLUDE_WORDS = ["분양", "견본주택", "모델하우스", "청약 접수", "세미나", "설명회", "[광고]", "[AD]", "포토"]

MAX_ITEMS = 5
MIN_ITEMS = 3
CLAUDE_MODEL = "claude-opus-5-5"


@dataclass
class Article:
    title: str
    description: str
    url: str
    published: datetime
    query: str
    source: str = ""  # 언론사 이름 (Google 뉴스만 제공)
    related: int = 1  # 같은 사건을 다룬 기사 수 (중복 제거 후 누적)


def clean(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def fetch_google(query: str) -> list[dict]:
    """Google 뉴스 RSS 검색. 키가 필요 없지만 공식 API는 아니다."""
    params = urllib.parse.urlencode({"q": f"{query} when:1d", "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
    req = urllib.request.Request(
        f"https://news.google.com/rss/search?{params}",
        headers={"User-Agent": "Mozilla/5.0 (news-digest)"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        root = ET.fromstring(resp.read())
    items = []
    for item in root.iter("item"):
        source = (item.findtext("source") or "").strip()
        title = clean(item.findtext("title") or "")
        if source and title.endswith(f" - {source}"):  # 제목 끝의 " - 언론사" 제거
            title = title[: -len(source) - 3]
        items.append({
            "title": title,
            "description": "",  # RSS 설명란은 제목 반복이라 쓰지 않는다
            "url": item.findtext("link") or "",
            "pubDate": item.findtext("pubDate") or "",
            "source": source,
        })
    return items


def fetch_naver(query: str, client_id: str, client_secret: str) -> list[dict]:
    # 네이버 개발자센터 검색 API는 2026-07-31 신규 발급이 끝나 NAVER API HUB(네이버 클라우드)로 호출한다.
    # 파라미터와 응답 형식은 기존 개발자센터 API와 같다.
    params = urllib.parse.urlencode({"query": query, "display": 100, "sort": "date"})
    req = urllib.request.Request(
        f"https://naverapihub.apigw.ntruss.com/search/v1/news?{params}",
        headers={"X-NCP-APIGW-API-KEY-ID": client_id, "X-NCP-APIGW-API-KEY": client_secret},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        items = json.load(resp).get("items", [])
    return [
        {
            "title": clean(item["title"]),
            "description": clean(item["description"]),
            "url": item.get("originallink") or item["link"],
            "pubDate": item["pubDate"],
            "source": "",
        }
        for item in items
    ]


def collect(fetchers: dict[str, Callable[[str], list[dict]]], since: datetime) -> list[Article]:
    articles: dict[str, Article] = {}
    succeeded = 0
    for name, fetch in fetchers.items():
        for query in QUERIES:
            try:
                items = fetch(query)
                succeeded += 1
            except Exception as e:  # 검색어 하나가 실패해도 나머지는 계속
                print(f"[warn] {name} '{query}' 검색 실패: {e}", file=sys.stderr)
                continue
            for item in items:
                try:
                    published = parsedate_to_datetime(item["pubDate"])
                except (TypeError, ValueError):
                    continue
                url, title = item["url"], item["title"]
                if published < since or not url or url in articles:
                    continue
                if any(w in title for w in EXCLUDE_WORDS):
                    continue
                articles[url] = Article(title, item["description"], url, published, query, item["source"])
    if not succeeded:  # 빈 브리핑을 올리는 대신 워크플로를 실패시켜 알림이 가게 한다
        sys.exit("모든 뉴스 검색이 실패했습니다.")
    return list(articles.values())


def normalize(title: str) -> str:
    title = re.sub(r"\[[^\]]*\]|\([^)]*\)", "", title)  # [단독], (종합) 등 말머리 제거
    return re.sub(r"[^0-9A-Za-z가-힣]", "", title)


def dedupe(articles: list[Article]) -> list[Article]:
    """제목이 비슷한 기사는 같은 사건으로 보고 가장 이른 기사 하나만 남긴다."""
    kept: list[Article] = []
    for art in sorted(articles, key=lambda a: a.published):
        norm = normalize(art.title)
        for k in kept:
            if SequenceMatcher(None, norm, normalize(k.title)).ratio() > 0.6:
                k.related += 1
                break
        else:
            kept.append(art)
    return kept


def score(art: Article) -> float:
    s = sum(w for word, w in TITLE_WEIGHTS.items() if word in art.title)
    return s + min(art.related, 10) * 0.5  # 여러 언론사가 다룬 사건일수록 중요


def short(text: str, limit: int = 90) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def pick_by_rules(candidates: list[Article]) -> list[tuple[Article, str, str]]:
    ranked = sorted(candidates, key=lambda a: (score(a), a.published), reverse=True)
    return [
        (a, re.sub(r"^(\[[^\]]*\]\s*)+|\s*\((종합|상보|속보)\)$", "", a.title), short(a.description))
        for a in ranked[:MAX_ITEMS]
        if score(a) > 1
    ]


def pick_by_claude(candidates: list[Article]) -> list[tuple[Article, str, str]]:
    import anthropic

    ranked = sorted(candidates, key=score, reverse=True)[:60]
    listing = "\n".join(
        f"{i}. [{a.published.astimezone(KST):%m/%d %H:%M}] (관련기사 {a.related}건) {a.title}"
        + (f" - {a.source}" if a.source else "")
        + (f"\n   {a.description}" if a.description else "")
        for i, a in enumerate(ranked)
    )
    prompt = f"""아래는 최근 24시간 동안 나온 한국 뉴스 후보입니다.
부동산·세금에 관심 있는 일반인이 모인 오픈채팅방에 공유할 기사를 {MIN_ITEMS}~{MAX_ITEMS}개 골라 주세요.

선별 기준
- 상속세·증여세·종부세·양도세·취득세 등 세금, 세법 개정, 정부 부동산 정책에 직접 관련된 기사
- 같은 사건은 하나만, 단순 시황·광고·지역 개발 홍보성 기사는 제외
- 관련 기사 수가 많은(여러 언론이 다룬) 소식을 우선

각 기사마다 짧은 제목(30자 이내)과 핵심 내용 한 문장 요약(60자 이내)을 쓰세요.
요약은 후보에 적힌 제목·설명만 근거로 하고, 없는 내용을 추측하지 마세요.
설명이 없는 기사는 제목에서 알 수 있는 사실만 풀어 쓰세요.
관련 기사가 {MIN_ITEMS}개보다 적으면 있는 만큼만 고르세요.

JSON 배열만 출력하세요. 형식: [{{"index": 0, "title": "...", "summary": "..."}}]

후보
{listing}"""

    client = anthropic.Anthropic()
    response = client.beta.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4000,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude가 요청을 거절했습니다")
    text = "".join(b.text for b in response.content if b.type == "text")
    match = re.search(r"\[.*\]", text, re.S)
    if not match:
        raise ValueError(f"JSON 응답을 찾지 못했습니다: {text[:200]}")
    picks = []
    for p in json.loads(match.group(0))[:MAX_ITEMS]:
        idx = int(p["index"])
        if 0 <= idx < len(ranked):
            picks.append((ranked[idx], p["title"].strip(), p["summary"].strip()))
    return picks


def render(picks: list[tuple[Article, str, str]], today: datetime) -> str:
    keycaps = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    lines = [f"📰 {today:%m/%d}({WEEKDAYS[today.weekday()]}) 상속·증여·부동산 세금 뉴스", ""]
    if not picks:
        lines += ["오늘은 눈에 띄는 관련 뉴스가 없었어요.", ""]
    for i, (art, title, summary) in enumerate(picks):
        lines.append(f"{keycaps[i]} {title}")
        if summary:
            lines.append(f"→ {summary}")
        lines += [f"🔗 {art.source + ' ' if art.source else ''}{art.url}", ""]
    lines.append("좋은 하루 보내세요 😊")
    return "\n".join(lines)


def main() -> None:
    fetchers: dict[str, Callable[[str], list[dict]]] = {"Google": fetch_google}
    client_id = os.environ.get("NAVER_CLIENT_ID", "").strip()
    client_secret = os.environ.get("NAVER_CLIENT_SECRET", "").strip()
    if client_id and client_secret:
        fetchers["Naver"] = lambda q: fetch_naver(q, client_id, client_secret)

    now = datetime.now(KST)
    since = now - timedelta(hours=int(os.environ.get("LOOKBACK_HOURS", "24")))
    candidates = dedupe(collect(fetchers, since))
    print(f"후보 기사 {len(candidates)}건", file=sys.stderr)

    picks: list[tuple[Article, str, str]] = []
    if candidates and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            picks = pick_by_claude(candidates)
        except Exception as e:
            print(f"[warn] Claude 선별 실패, 규칙 기반으로 대체: {e}", file=sys.stderr)
    if not picks:
        picks = pick_by_rules(candidates)

    message = render(picks, now)
    with open(os.environ.get("OUTPUT_PATH", "digest.md"), "w", encoding="utf-8") as f:
        f.write(message + "\n")
    print(message)


if __name__ == "__main__":
    main()
