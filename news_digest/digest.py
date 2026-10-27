"""상속·증여·세금·부동산 정책 뉴스 브리핑 생성기.

네이버 뉴스 검색 API(키가 없거나 실패하면 Google 뉴스 RSS)로 최근 기사를 모으고,
부동산 정책·세금 정책·세무 칼럼이 고루 섞이도록 3~5건을 골라
카카오톡 오픈채팅방에 붙여넣을 메시지(digest.md)를 만든다.

환경 변수
  NAVER_CLIENT_ID, NAVER_CLIENT_SECRET  (선택) NAVER API HUB 애플리케이션의 Client ID / Secret
  ANTHROPIC_API_KEY                     (선택) 있으면 Claude가 기사 선별·요약
  OUTPUT_PATH                           (선택) 결과 파일 경로, 기본 digest.md
  NOTES_PATH                            (선택) 원문 대조 검증 기록 경로, 기본 notes.md
  HISTORY_PATH                          (선택) 지난 브리핑 이슈 목록(JSON), 기본 history.json. 여기 나온 기사는 다시 넣지 않는다
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


@dataclass(frozen=True)
class Category:
    name: str
    queries: list[str]
    hours: int  # 수집 기간 (칼럼은 매일 나오지 않아 더 길게)
    weights: dict[str, int]  # 제목에 들어 있으면 점수를 주는 단어 (규칙 기반 선별용)


# 주제가 한쪽으로 쏠리지 않게 섞는 기준. 출력 순서이기도 하다.
CATEGORIES = [
    Category(
        "부동산 정책",
        ["부동산 대책", "부동산 정책", "주택 공급 대책", "주택담보대출 규제", "국토교통부 주택", "토지거래허가구역"],
        hours=24,
        weights={
            "대책": 3, "정부": 2, "국토부": 2, "국토교통부": 2, "금융위": 2, "공급": 2, "규제": 2,
            "대출": 2, "토지거래허가": 2, "조정대상": 2, "투기과열": 2, "청약": 1, "재건축": 1,
            "국회": 1, "법안": 1, "부동산": 1, "주택": 1,
        },
    ),
    Category(
        "세금 정책",
        ["상속세", "증여세", "종부세", "양도세", "재산세 주택", "세법개정안"],
        hours=24,
        weights={
            "상속": 3, "증여": 3, "종부세": 3, "종합부동산세": 3, "양도세": 3, "양도소득세": 3,
            "세법": 2, "세제": 2, "취득세": 2, "재산세": 2, "공시가": 2,
            "정부": 1, "기재부": 1, "재정경제부": 1, "국회": 1, "개정": 1,
        },
    ),
    Category(
        "세무 칼럼",
        ["세무사 칼럼 부동산", "세무사 칼럼 상속", "절세 칼럼", "세무 상담 증여"],
        hours=72,
        weights={
            "칼럼": 3, "세무사": 3, "절세": 3, "Q&A": 2, "상담": 2, "알아두면": 1, "주의": 1,
            "상속": 1, "증여": 1, "양도": 1, "부동산": 1,
        },
    ),
]

# 광고·홍보성 기사 제외용
EXCLUDE_WORDS = ["분양", "견본주택", "모델하우스", "청약 접수", "세미나", "설명회", "[광고]", "[AD]", "포토"]

MAX_ITEMS = 5
MAX_PER_CATEGORY = 3  # 한 주제가 이보다 많이 뽑히지 않게 한다 (규칙 기반 선별용)
MIN_ITEMS = 3
CLAUDE_MODEL = "claude-opus-5-5"


@dataclass
class Article:
    title: str
    description: str
    url: str
    published: datetime
    category: Category
    source: str = ""  # 언론사 이름 (Google 뉴스만 제공, 네이버는 빈 값)
    related: int = 1  # 같은 사건을 다룬 기사 수 (중복 제거 후 누적)


def clean(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def fetch_google(query: str, hours: int) -> list[dict]:
    """Google 뉴스 RSS 검색. 키가 필요 없지만 공식 API는 아니다."""
    when = f"{hours // 24}d" if hours % 24 == 0 else f"{hours}h"
    params = urllib.parse.urlencode({"q": f"{query} when:{when}", "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
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


Fetcher = Callable[[str, int], list[dict]]  # (검색어, 수집 기간 시간) -> 기사 목록


def collect(fetchers: dict[str, Fetcher], now: datetime) -> list[Article]:
    articles: dict[str, Article] = {}
    succeeded = 0
    counts = dict.fromkeys(fetchers, 0)  # 출처별 수집 건수 (연결 확인용 로그)
    for category in CATEGORIES:
        since = now - timedelta(hours=category.hours)
        for name, fetch in fetchers.items():
            for query in category.queries:
                try:
                    items = fetch(query, category.hours)
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
                    articles[url] = Article(title, item["description"], url, published, category, item["source"])
                    counts[name] += 1
    print("출처별 수집: " + ", ".join(f"{n} {c}건" for n, c in counts.items()), file=sys.stderr)
    if not succeeded:
        raise RuntimeError(f"{', '.join(fetchers)} 뉴스 검색이 모두 실패했습니다.")
    return list(articles.values())


def normalize(title: str) -> str:
    title = re.sub(r"\[[^\]]*\]|\([^)]*\)", "", title)  # [단독], (종합) 등 말머리 제거
    return re.sub(r"[^0-9A-Za-z가-힣]", "", title)


def words(title: str) -> set[str]:
    """제목의 두 글자 이상 단어. 조사 차이를 줄이려고 앞 3글자만 쓴다."""
    title = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", title)
    return {w[:3] for w in re.findall(r"[0-9A-Za-z가-힣]{2,}", title)}


def same_story(a: str, b: str) -> bool:
    if SequenceMatcher(None, normalize(a), normalize(b)).ratio() > 0.6:
        return True
    # 표현이 달라도 핵심 단어(인물·기관·사건)가 많이 겹치면 같은 사건으로 본다
    wa, wb = words(a), words(b)
    return len(wa & wb) >= 3 and len(wa & wb) / min(len(wa), len(wb)) >= 0.4


TRACKING_PARAMS = {"ref", "input", "from", "sid", "utm_source", "utm_medium", "utm_campaign"}


def canonical_url(url: str) -> str:
    """같은 기사인데 추적용 파라미터만 다른 주소를 같게 본다."""
    parts = urllib.parse.urlsplit(url.strip())
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query) if k.lower() not in TRACKING_PARAMS]
    host = parts.netloc.lower().removeprefix("www.")
    return f"{host}{parts.path.rstrip('/')}?{urllib.parse.urlencode(sorted(query))}"


def load_history(path: str, today: datetime) -> tuple[set[str], list[str]]:
    """지난 브리핑(오늘 것 제외)에 나간 기사 주소와 제목.

    파일은 `gh issue list --json body,createdAt` 결과다. 오늘 이미 올린 브리핑을 다시 만들 때
    오늘 기사까지 빠지지 않도록 오늘(KST) 만든 이슈는 건너뛴다.
    """
    try:
        with open(path, encoding="utf-8") as f:
            issues = json.load(f)
    except (OSError, ValueError):
        return set(), []
    urls: set[str] = set()
    titles: list[str] = []
    for issue in issues:
        created = datetime.fromisoformat(issue["createdAt"].replace("Z", "+00:00")).astimezone(KST)
        if created.date() >= today.date():
            continue
        body = issue.get("body") or ""
        urls |= {canonical_url(u) for u in re.findall(r"https?://\S+", body)}
        titles += re.findall(r"^\d+\. (.+)$", body, re.M)
    return urls, titles


def drop_already_sent(articles: list[Article], urls: set[str], titles: list[str]) -> list[Article]:
    kept = [
        a for a in articles
        if canonical_url(a.url) not in urls and not any(same_story(a.title, t) for t in titles)
    ]
    print(f"지난 브리핑과 겹쳐 제외: {len(articles) - len(kept)}건", file=sys.stderr)
    return kept


def dedupe(articles: list[Article]) -> list[Article]:
    """같은 사건을 다룬 기사는 가장 이른 기사 하나만 남긴다."""
    kept: list[Article] = []
    for art in sorted(articles, key=lambda a: a.published):
        for k in kept:
            if same_story(art.title, k.title):
                k.related += 1
                break
        else:
            kept.append(art)
    return kept


def score(art: Article) -> float:
    s = sum(w for word, w in art.category.weights.items() if word in art.title)
    return s + min(art.related, 10) * 0.5  # 여러 언론사가 다룬 사건일수록 중요


def short(text: str, limit: int = 90) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def display_title(title: str) -> str:
    return re.sub(r"^(\[[^\]]*\]\s*)+|\s*\((종합|상보|속보)\)$", "", title)


def by_category_order(picks: list[tuple[Article, str, str]]) -> list[tuple[Article, str, str]]:
    return sorted(picks, key=lambda p: CATEGORIES.index(p[0].category))


def pick_by_rules(candidates: list[Article]) -> list[tuple[Article, str, str]]:
    """주제마다 가장 좋은 기사를 하나씩 먼저 넣고, 나머지는 점수 순으로 채운다 (한 주제는 MAX_PER_CATEGORY까지)."""
    ranked = [a for a in sorted(candidates, key=lambda a: (score(a), a.published), reverse=True) if score(a) > 1]
    chosen = [best for c in CATEGORIES if (best := next((a for a in ranked if a.category is c), None))]
    for a in ranked:
        if len(chosen) >= MAX_ITEMS:
            break
        if a not in chosen and sum(x.category is a.category for x in chosen) < MAX_PER_CATEGORY:
            chosen.append(a)
    return by_category_order([(a, display_title(a.title), short(a.description)) for a in chosen])


def ask_claude_json(prompt: str, effort: str) -> list[dict]:
    """Claude에게 묻고 응답에서 JSON 배열을 꺼낸다."""
    import anthropic

    response = anthropic.Anthropic().beta.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=8000,
        output_config={"effort": effort},
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
    return json.loads(match.group(0))


def match_title(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def pick_by_claude(candidates: list[Article], sent_titles: list[str]) -> list[tuple[Article, str, str]]:
    ranked: list[Article] = []
    for category in CATEGORIES:  # 분류마다 상위 25건씩 후보로 보낸다
        ranked += sorted((a for a in candidates if a.category is category), key=score, reverse=True)[:25]
    listing = "\n".join(
        f"[K{i:03d}] <{a.category.name}> [{a.published.astimezone(KST):%m/%d %H:%M}] (관련기사 {a.related}건) {a.title}"
        + (f" - {a.source}" if a.source else "")
        + (f"\n   {a.description}" if a.description else "")
        for i, a in enumerate(ranked)
    )
    prompt = f"""아래는 최근 나온 한국 뉴스 후보입니다. <분류>는 검색 기준으로 붙인 것이라 틀릴 수 있습니다.
부동산·세금에 관심 있는 일반인이 모인 오픈채팅방에 공유할 기사를 {MIN_ITEMS}~{MAX_ITEMS}개 골라 주세요.

구성
- 주제가 한쪽으로 쏠리지 않게 아래 세 가지를 적당히 섞어 주세요. 정해진 비율은 없고,
  그날 중요한 소식이 많은 쪽이 더 많아도 되지만 한 가지로만 채우지는 마세요.
  - 부동산 정책: 정부·국회의 주택 공급, 대출 규제, 규제지역, 청약 제도 등 (세금 이야기가 아닌 것)
  - 세금 정책: 상속세·증여세·종부세·양도세·재산세 등 세금 제도와 세법 개정
  - 세무 칼럼: 세무사·전문가가 쓴 칼럼이나 절세 정보
- 같은 사건은 하나만, 단순 시황·광고·분양 홍보·세무법인 홍보성 기사는 제외하세요.
- 관련 기사 수가 많은(여러 언론이 다룬) 소식을 우선하세요.
- 아래 "최근 브리핑에 나간 소식"과 같은 내용은 고르지 마세요. 다른 언론사 기사이거나
  여러 소식을 묶은 기사여도, 새로 알려진 사실 없이 같은 내용이면 제외합니다.

각 기사마다 짧은 제목(30자 이내)과 핵심 내용 한 문장 요약(60자 이내)을 쓰세요.
요약은 후보에 적힌 제목·설명만 근거로 하고, 없는 내용을 추측하지 마세요. (이후 원문과 대조해 검증합니다)
설명이 없는 기사는 제목에서 알 수 있는 사실만 풀어 쓰세요.
이모지는 쓰지 마세요.

JSON 배열만 출력하세요. 형식:
[{{"id": "K000", "source_title": "후보 목록의 기사 제목을 그대로 복사", "category": "부동산 정책", "title": "...", "summary": "..."}}]
id는 후보 앞의 [K000] 같은 번호, source_title은 그 후보의 제목을 한 글자도 바꾸지 말고 복사하세요.
category는 {", ".join(c.name for c in CATEGORIES)} 중 하나로, 기사 내용에 맞게 다시 판단해 쓰세요.

최근 브리핑에 나간 소식
{chr(10).join(f"- {t}" for t in sent_titles) or "- (없음)"}

후보
{listing}"""

    names = {c.name: c for c in CATEGORIES}
    picks = []
    for p in ask_claude_json(prompt, effort="low")[:MAX_ITEMS]:
        m = re.fullmatch(r"K(\d+)", str(p.get("id", "")).strip())
        art = ranked[int(m.group(1))] if m and int(m.group(1)) < len(ranked) else None
        source_title = str(p.get("source_title", ""))
        # 번호를 한 칸 잘못 짚으면 제목과 다른 기사의 링크가 붙는다. 복사한 제목으로 다시 확인한다.
        if art is None or match_title(source_title, art.title) < 0.8:
            best = max(ranked, key=lambda a: match_title(source_title, a.title))
            if match_title(source_title, best.title) < 0.8:
                print(f"[warn] 고른 기사를 찾지 못해 뺌: {p.get('id')} {source_title}", file=sys.stderr)
                continue
            print(f"[warn] 번호가 제목과 달라 제목 기준으로 바로잡음: {p.get('id')} -> {source_title}", file=sys.stderr)
            art = best
        if any(art is q[0] for q in picks):
            continue
        art.category = names.get(p.get("category"), art.category)
        picks.append((art, p["title"].strip(), p["summary"].strip()))
    return by_category_order(picks)


def fetch_article_text(url: str, hint: str) -> str:
    """기사 페이지 본문 텍스트. hint(네이버 발췌문) 근처를 잘라 본문 위주로 돌려준다."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (news-digest)"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read(2_000_000)
        charset = resp.headers.get_content_charset()
    if not charset:
        m = re.search(rb'charset=["\']?([A-Za-z0-9_-]+)', raw[:5000])
        charset = m.group(1).decode() if m else "utf-8"
    if charset.lower() in ("euc-kr", "ks_c_5601-1987"):
        charset = "cp949"
    page = raw.decode(charset, errors="replace")
    page = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>|<!--.*?-->", " ", page)
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page))).strip()
    anchor = text.find(hint[:15]) if len(hint) >= 15 else -1
    start = max(anchor - 1500, 0) if anchor >= 0 else 0
    return text[start : start + 8000]


def verify_with_source(picks: list[tuple[Article, str, str]]) -> tuple[list[tuple[Article, str, str]], list[str]]:
    """Claude가 쓴 제목·요약을 기사 원문과 대조해 인물·직함·숫자·날짜를 바로잡는다.

    원문을 열 수 없거나 검증에 실패한 기사는 지어낸 내용이 없도록 원래 제목과 네이버 발췌문을 그대로 쓴다.
    돌려주는 notes는 사람이 확인할 수 있게 이슈에 함께 올리는 검증 기록이다.
    """
    sources: dict[int, str] = {}
    for i, (art, _, _) in enumerate(picks):
        try:
            sources[i] = fetch_article_text(art.url, art.description)
        except Exception as e:
            print(f"[warn] 원문을 열 수 없음 {art.url}: {e}", file=sys.stderr)

    fallback = lambda art: (art, display_title(art.title), short(art.description))  # noqa: E731
    results: dict[int, dict] = {}
    if sources:
        blocks = "\n\n".join(
            f"[{i}]\n제목 후보: {picks[i][1]}\n요약 후보: {picks[i][2]}\n원래 기사 제목: {picks[i][0].title}\n원문: {text}"
            for i, text in sources.items()
        )
        prompt = f"""아래 각 기사에 대해 "제목 후보"와 "요약 후보"를 "원문"과 한 글자씩 대조해 검증하세요.

확인할 것: 사람 이름, 직함·소속(장관/차관, 의원 소속 정당 등), 기관명, 숫자와 단위(억/조/%/명), 날짜, 법안·제도 이름.
- 원문에 근거가 없거나 원문과 다른 내용이 있으면 원문에 맞게 고치세요.
- 원문에서 확인할 수 없는 내용은 빼세요. 추측으로 채우지 마세요.
- 고친 뒤에도 제목은 30자 이내, 요약은 한 문장 60자 이내로, 이모지 없이 쓰세요.
- 원문이 기사 본문이 아니라 목록·오류 페이지 등이라 검증할 수 없으면 ok를 false로 하세요.
- 원문이 "원래 기사 제목"이나 제목·요약 후보와 다른 사건을 다룬 기사이면 고치지 말고 ok를 false로 하세요.

JSON 배열만 출력하세요. 형식:
[{{"index": 0, "ok": true, "title": "...", "summary": "...", "fixes": "고친 내용을 '틀린 것 → 맞는 것'으로, 없으면 빈 문자열"}}]

{blocks}"""
        try:
            results = {int(r["index"]): r for r in ask_claude_json(prompt, effort="medium")}
        except Exception as e:
            print(f"[warn] 원문 대조 검증 실패: {e}", file=sys.stderr)

    verified, notes = [], []
    for i, pick in enumerate(picks):
        art = pick[0]
        r = results.get(i)
        if r and r.get("ok") and r.get("title") and r.get("summary"):
            verified.append((art, r["title"].strip(), r["summary"].strip()))
            fixes = (r.get("fixes") or "").strip()
            notes.append(f"{i + 1}번: 원문 대조 완료" + (f" (수정: {fixes})" if fixes else ""))
        else:
            verified.append(fallback(art))
            why = "원문을 열 수 없어" if i not in sources else "원문으로 검증하지 못해"
            notes.append(f"{i + 1}번: {why} 기사 원래 제목과 발췌문을 그대로 사용")
    return verified, notes


def render(picks: list[tuple[Article, str, str]], today: datetime) -> str:
    # 카카오톡에 그대로 붙여넣으므로 이모지는 쓰지 않는다
    lines = [f"[{today:%m/%d}({WEEKDAYS[today.weekday()]}) 상속·증여·부동산 세금 뉴스]", ""]
    if not picks:
        lines += ["오늘은 눈에 띄는 관련 뉴스가 없었어요.", ""]
    for i, (art, title, summary) in enumerate(picks, start=1):
        lines.append(f"{i}. {title}")
        if summary:
            lines.append(f"- {summary}")
        lines += [f"{art.source + ' ' if art.source else ''}{art.url}", ""]
    lines.append("좋은 하루 보내세요.")
    return "\n".join(lines)


def main() -> None:
    now = datetime.now(KST)
    client_id = os.environ.get("NAVER_CLIENT_ID", "").strip()
    client_secret = os.environ.get("NAVER_CLIENT_SECRET", "").strip()
    articles: list[Article] | None = None
    # 네이버를 우선 쓴다 (기사 원래 주소가 와서 링크가 짧다). 키가 없거나 네이버가 모두 실패하면 Google로 대신한다.
    if client_id and client_secret:
        try:
            articles = collect({"Naver": lambda q, _hours: fetch_naver(q, client_id, client_secret)}, now)
        except RuntimeError as e:
            print(f"[warn] {e} Google 뉴스로 대신합니다.", file=sys.stderr)
    if articles is None:
        try:
            articles = collect({"Google": fetch_google}, now)
        except RuntimeError as e:  # 빈 브리핑을 올리는 대신 워크플로를 실패시켜 알림이 가게 한다
            sys.exit(str(e))
    sent_urls, sent_titles = load_history(os.environ.get("HISTORY_PATH", "history.json"), now)
    candidates = drop_already_sent(dedupe(articles), sent_urls, sent_titles)
    print(f"후보 기사 {len(candidates)}건", file=sys.stderr)

    picks: list[tuple[Article, str, str]] = []
    notes: list[str] = []
    if candidates and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            picks = pick_by_claude(candidates, sent_titles)
        except Exception as e:
            print(f"[warn] Claude 선별 실패, 규칙 기반으로 대체: {e}", file=sys.stderr)
        if picks:
            picks, notes = verify_with_source(picks)
    if not picks:
        # 규칙 기반은 기사 제목과 발췌문을 그대로 쓰므로 따로 검증하지 않는다
        picks = pick_by_rules(candidates)

    message = render(picks, now)
    with open(os.environ.get("OUTPUT_PATH", "digest.md"), "w", encoding="utf-8") as f:
        f.write(message + "\n")
    with open(os.environ.get("NOTES_PATH", "notes.md"), "w", encoding="utf-8") as f:
        f.write("".join(f"- {n}\n" for n in notes))
    print(message)
    print("\n".join(notes), file=sys.stderr)


if __name__ == "__main__":
    main()
