#!/usr/bin/env python3
"""감정평가사사무소 경율 — 감정평가서 생성기.

사용법:
    python3 build.py data/sample_commercial.json            # output/<감정서번호>.html, .pdf 생성
    python3 build.py data/sample_commercial.json --html-only

데이터(JSON)의 입력값으로 시점수정치, 가치형성요인 비교치, 비준가액,
수익가액을 계산해 감정서 전체(표지~사진첨부용지)를 만듭니다.
"""
import argparse
import base64
import json
import math
import mimetypes
import subprocess
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------- 숫자/글자 변환
def won(n):
    """정수 금액에 천 단위 쉼표."""
    if n is None:
        return "-"
    return f"{int(round(n)):,}"


def num(n, digits=None):
    if n is None or n == "":
        return "-"
    if digits is None:
        s = f"{n:,}"
        return s
    return f"{n:,.{digits}f}"


def area(n):
    """면적: 불필요한 0 없이 표기 (46.2, 1,818.9, 29.656)."""
    if n is None:
        return "-"
    s = f"{n:,.4f}".rstrip("0").rstrip(".")
    return s


_DIGITS = "영일이삼사오육칠팔구"
_SMALL = ["", "십", "백", "천"]
_BIG = ["", "만", "억", "조"]


def korean_amount(n):
    """150000000 -> '일억오천만'."""
    n = int(n)
    if n == 0:
        return "영"
    out = []
    big = 0
    while n > 0:
        chunk = n % 10000
        if chunk:
            s = ""
            for i in range(3, -1, -1):
                d = (chunk // (10 ** i)) % 10
                if d:
                    s += _DIGITS[d] + _SMALL[i]
            out.append(s + _BIG[big])
        n //= 10000
        big += 1
    return "".join(reversed(out))


def round_to(x, unit, mode="round"):
    if not unit:
        return x
    if mode == "floor":
        return math.floor(x / unit) * unit
    return round(x / unit) * unit


def dotted(d):
    """'2025-09-17' -> '2025. 09. 17'."""
    y, m, dd = d.split("-")
    return f"{y}. {m}. {dd}"


def long_date(d):
    y, m, dd = d.split("-")
    return f"{y}년 {m}월 {dd}일"


def nl2br(s):
    from markupsafe import Markup, escape
    return Markup("<br>".join(escape(s).split("\n"))) if s else ""


def img_src(path, base):
    """이미지 파일을 data URI로 넣어 PDF/HTML 하나로 완결되게 함."""
    if not path:
        return ""
    p = (base / path) if not Path(path).is_absolute() else Path(path)
    if not p.exists():
        print(f"[경고] 이미지 없음: {p}", file=sys.stderr)
        return ""
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


# ---------------------------------------------------------------- 계산
def compute(d):
    sc = d["sales_comparison"]
    inc = d.get("income")
    calc = {}

    tm = sc["time"]
    t = 1.0
    terms = []
    if tm.get("method") == "index":
        # 시점수정치: 기준시점 지수 / 거래시점 지수
        t = tm["base_index"] / tm["trade_index"]
    for q in ([] if tm.get("method") == "index" else tm["quarters"]):
        # 시점수정치: Π(1 + 분기수익률 × 경과일수/분기일수)
        r = q["rate"] / 100
        if q["days"] == q["total"]:
            terms.append(f"(1+{r:.4f})".replace("+0.0000", "+0"))
            t *= 1 + r
        else:
            terms.append(f"(1+{r:.4f}*{q['days']}/{q['total']})".replace("+0.0000*", "+0*"))
            t *= 1 + r * q["days"] / q["total"]
    time_factor = round(t, 5)
    calc["time_factor"] = time_factor
    calc["time_pct"] = f"{(time_factor - 1) * 100:.3f}%"
    calc["time_formula"] = "*".join(terms)

    # 가치형성요인 비교치 (누계)
    v = 1.0
    for f in sc["factors"]:
        v *= f["rate"]
    value_factor = round(v, 3)
    calc["value_factor"] = value_factor

    selected = next(x for x in sc["trades"] if x["no"] == sc["selected"])
    calc["selected"] = selected

    # 비준단가·비준가액 (물건별)
    rows = []
    total_area = 0
    total_value = 0
    for u in d["units"]:
        raw_unit = (selected["unit"] * sc["situation_factor"] * time_factor
                    * sc.get("region_factor", 1.0) * value_factor)
        unit_price = round_to(raw_unit, sc.get("unit_round", 10000))
        computed = unit_price * u["area"]
        value = round_to(computed, sc.get("value_round", 1000000), "floor")
        rows.append({"unit": u, "case_unit": selected["unit"], "raw_unit": raw_unit, "unit_price": unit_price,
                     "computed": computed, "value": value})
        total_area += u["area"]
        total_value += value
    calc["sc_rows"] = rows
    calc["sc_total_area"] = total_area
    calc["sc_total"] = total_value

    calc["final"] = total_value
    calc["final_korean"] = korean_amount(total_value)
    calc["income"] = None
    if not inc:
        return calc

    # 수익환원법
    a = inc["applied"]
    deposit_income = (a.get("deposit") or 0) * inc.get("deposit_yield", 0) / 100
    annual_rent = (a.get("monthly") or 0) * 12
    annual_mgmt = (a.get("mgmt") or 0) * 12
    pgi = deposit_income + annual_rent + annual_mgmt
    vl = pgi * inc["vacancy_rate"] / 100
    other = 0
    egi = pgi - vl + other
    oe = egi * inc["opex_rate"] / 100
    noi = egi - oe
    inc_value = round_to(noi / (inc["cap_rate"] / 100), inc.get("value_round", 1000), "floor")
    vs = inc["vacancy_stats"]["values"]
    calc["income"] = dict(deposit_income=deposit_income, annual_rent=annual_rent,
                          annual_mgmt=annual_mgmt, pgi=pgi, vl=vl, other=other, egi=egi,
                          oe=oe, noi=noi, value=inc_value,
                          vacancy_avg=sum(vs) / len(vs))

    # 최종 감정평가액 = 거래사례비교법 시산가액
    calc["final"] = total_value
    calc["final_korean"] = korean_amount(total_value)
    return calc


# ---------------------------------------------------------------- 빌드
def build(data_path: Path, html_only=False):
    d = json.loads(data_path.read_text(encoding="utf-8"))
    calc = compute(d)
    base = data_path.parent.parent  # appraisal_report/

    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=True,
                      trim_blocks=True, lstrip_blocks=True)
    env.filters.update(won=won, num=num, area=area, dotted=dotted, long_date=long_date,
                       nl2br=nl2br, korean=korean_amount)
    env.globals["img"] = lambda p: img_src(p, base)

    html = env.get_template("report.html.j2").render(d=d, c=calc)
    out_dir = HERE / "output"
    out_dir.mkdir(exist_ok=True)
    stem = d["report"]["number"]
    html_path = out_dir / f"{stem}.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"HTML: {html_path}")

    print(f"감정평가액: {won(calc['final'])}원 ({calc['final_korean']}원정)")
    print(f"  시점수정치 {calc['time_factor']}, 가치형성요인 {calc['value_factor']}"
          + (f", 수익가액 {won(calc['income']['value'])}원" if calc["income"] else ""))

    if not html_only:
        pdf_path = out_dir / f"{stem}.pdf"
        subprocess.run(["node", str(HERE / "to_pdf.js"), str(html_path), str(pdf_path)], check=True)
        print(f"PDF : {pdf_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("data", nargs="?", default=str(HERE / "data" / "sample_commercial.json"))
    ap.add_argument("--html-only", action="store_true")
    args = ap.parse_args()
    build(Path(args.data).resolve(), args.html_only)
