// 감정평가 견적서 PDF 생성 (하이테크 양식, output/의 기존 견적서와 같은 모양)
// 사용: node make_estimate.mjs estimates/<이름>.json output/견적서_<이름>.pdf
// 입력 예시는 estimates/ 참고. 금액(원), travel=여비, expense=실비, rate=0.8/1.0/1.2(생략 시 1.0)
// 지분평가는 share 추가 (estimates/신림동1431-20_30%지분_5.43억.json 참고)
// 글꼴: fonts/NanumGothic-Regular.ttf, fonts/NanumGothic-Bold.ttf (README 참고)
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || "playwright");

const here = dirname(fileURLToPath(import.meta.url));
const inp = JSON.parse(readFileSync(process.argv[2], "utf8"));
const out = resolve(process.argv[3]);

// 감정평가 보수기준 요율표 [하한, 상한, 1만분의], 최저 25만원, 천원 미만 절사
const BANDS = [[5e7, 5e8, 11], [5e8, 1e9, 9], [1e9, 5e9, 8], [5e9, 1e10, 7], [1e10, 5e10, 6],
  [5e10, 1e11, 5], [1e11, 3e11, 4], [3e11, 6e11, 3], [6e11, 1e12, 2], [1e12, Infinity, 1]];
// extra: 지분평가 등 할증 배율. 요율표 수수료에 곱한 뒤 천원 미만 절사한다.
function fee(value, mult, extra = 1) {
  let acc = 250000;
  for (const [lo, hi, r] of BANDS) { if (value <= lo) break; acc += (Math.min(value, hi) - lo) * r / 10000 * mult; }
  return Math.floor(Math.round(acc * extra) / 1000) * 1000;
}
const won = n => n.toLocaleString("ko-KR");
const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");

const rate = inp.rate ?? 1.0;
const rateLabel = { 0.8: "하한요율", 1: "기준요율", 1.2: "상한요율" }[rate];
// share: 지분평가 {"ratio": 0.3, "label": "30%", "fraction": "3/10", "feeMult": 1.2}. 기초가액은 지분 해당액.
const share = inp.share;
const base = share ? Math.round(inp.value * share.ratio) : inp.value;
const f = fee(base, rate, share?.feeMult ?? 1);
const supply = Math.floor((f + inp.travel + inp.expense) / 1000) * 1000;
const vat = Math.floor(supply * 0.1);
const total = supply + vat;
const man = Math.round(total / 1e4);
const eok = v => `${(v / 1e8).toLocaleString("ko-KR")}억원`;

const items = inp.items.map((it, i) => `<tr><td>${esc(it.cat)}</td><td class="l">${esc(inp.address)}</td><td>${esc(it.type)}</td><td>${esc(it.area)}${share ? `<br><span style="white-space:nowrap">(지분 ${esc(share.fraction)})</span>` : ""}</td>` +
  (i === 0 ? `<td class="r" rowspan="${inp.items.length}">${won(base)}</td>` : "") + `</tr>`).join("");
const opinions = ["본 탁상감정 결과는 실거래가격 및 평가전례에 기초한 개략적 금액으로서, 현장조사 시 감정평가 금액이 변동될 수 있습니다."];
if (share) opinions.push(`예상감정평가액은 전체 ${won(inp.value)}원 중 ${share.label} 지분 해당액입니다.`);
opinions.push(`정식 감정평가 의뢰 시, 예상 소요일은 약 ${inp.period ?? "5~7일"}(영업일 기준)입니다.`);
const logo = "data:image/png;base64," + readFileSync(resolve(here, "assets/hitech_logo_print.png")).toString("base64");
const font = w => resolve(here, `fonts/NanumGothic-${w}.ttf`);

const html = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>
@font-face { font-family: NG; src: url(file://${font("Regular")}); font-weight: 400; }
@font-face { font-family: NG; src: url(file://${font("Bold")}); font-weight: 700; }
@page { size: A4; margin: 15mm 18mm 14mm; }
* { box-sizing: border-box; }
body { margin: 0; font-family: NG; font-size: 9.8pt; color: #111; }
.page { height: 267mm; display: flex; flex-direction: column; }
h1 { text-align: center; font-size: 22pt; font-weight: 700; margin: 4mm 0 3mm; }
h1 span { text-decoration: underline; text-underline-offset: 5px; text-decoration-thickness: 2px; }
.docno { text-align: right; font-size: 9pt; font-weight: 700; margin-bottom: 1.5mm; }
table { width: 100%; border-collapse: collapse; }
td, th { border: 1px solid #222; padding: 1.9mm 2.5mm; font-weight: 400; }
th { background: #d9d9d9; font-weight: 700; }
.info th { width: 22%; text-align: center; letter-spacing: .5em; }
.info th.n { letter-spacing: 0; }
.info tr.sep td, .info tr.sep th { border-bottom-width: 2px; }
.bar { margin: 5mm 0 2mm; font-weight: 700; font-size: 11pt; padding-left: 3mm; border-left: 4px solid #1f4e9c; line-height: 1.1; }
.grid th { text-align: center; }
.grid td { text-align: center; }
.grid td.l { text-align: left; }
.grid td.r, .fee td.r { text-align: right; }
.opinion { border: 1px solid #222; padding: 2.5mm 3mm; line-height: 1.75; }
.opinion p { margin: 0; }
.fee th { text-align: left; width: 18%; }
.fee td.r { width: 24%; }
.fee tr.sep td, .fee tr.sep th { border-bottom-width: 2px; }
.fee tr.total td { font-weight: 700; }
.foot { margin-top: auto; display: flex; justify-content: space-between; align-items: flex-end; font-size: 9.5pt; line-height: 1.9; }
.foot b { font-size: 10.5pt; }
.foot img { width: 42mm; }
</style></head><body><div class="page">
<h1><span>(${esc(inp.kind ?? "부동산")}) 감정평가 견적서</span></h1>
<div class="docno">${esc(inp.docno)}</div>
<table class="info">
<tr><th>의뢰처</th><td>${esc(inp.client ?? "-")}</td></tr>
<tr class="sep"><th>담당자</th><td>하이테크감정평가법인 이민수 감정평가사</td></tr>
<tr><th>소재지</th><td>${esc(inp.address)}</td></tr>
<tr><th class="n">예상감정평가액</th><td>${share ? `${eok(base)} (전체 ${eok(inp.value)} 중 ${esc(share.label)} 지분)` : `${eok(inp.value)}${inp.items.length > 1 ? " (토지·건물 일괄)" : ""}`}</td></tr>
<tr><th class="n">예상수수료</th><td>${man.toLocaleString("ko-KR")}만원</td></tr>
</table>
<div class="bar">탁상감정결과</div>
<table class="grid">
<tr><th style="width:9%"></th><th>소재지</th><th style="width:20%">구분</th><th style="width:15%">면적(m2)</th><th style="width:21%">예상감정평가액(원)</th></tr>
${items}
</table>
<div class="bar">탁상감정 의견</div>
<div class="opinion">${opinions.map((o, i) => `<p>${i + 1}. ${esc(o)}</p>`).join("")}</div>
<div class="bar">예상수수료</div>
<table class="fee">
<tr class="sep"><th>기초가액</th><td class="r">${won(base)}</td><td>= 예상 감정평가액${share ? ` (${esc(share.label)} 지분)` : ""}</td></tr>
<tr><th>= 평가수수료</th><td class="r">${won(f)}</td><td>${share ? `= 기초가액 × ${rateLabel} × ${share.feeMult} (지분평가)` : `= 기초가액 × 적용요율 (${rateLabel} 적용)`}</td></tr>
<tr><th>+ 여비</th><td class="r">${won(inp.travel)}</td><td>${esc(inp.travelNote)}</td></tr>
<tr class="sep"><th>+ 실비</th><td class="r">${won(inp.expense)}</td><td>${esc(inp.expenseNote ?? "공부발급비, 사진촬영비")}</td></tr>
<tr><th>= 공급가액</th><td class="r">${won(supply)}</td><td>= 평가수수료 + 여비 + 실비 (백원 단위 절사)</td></tr>
<tr><th>+ 부가가치세</th><td class="r">${won(vat)}</td><td>= 공급가액 × 10%</td></tr>
<tr class="total"><th>예상수수료</th><td class="r">${won(total)}</td><td>= 공급가액 + 부가가치세</td></tr>
</table>
<div class="foot"><div>서울특별시 강남구 영동대로 511 트레이드타워 45층 2호<br><b>하이테크감정평가법인 주식회사</b><br>Tel) 02-6401-0706&nbsp;&nbsp;&nbsp;Fax) 02-6971-9586<br>국민은행 532001-01-294849 하이테크감정평가법인(주)</div><img src="${logo}" alt=""></div>
</div></body></html>`;

const htmlPath = join(tmpdir(), `estimate-${process.pid}.html`);
writeFileSync(htmlPath, html);
const browser = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {});
const page = await browser.newPage();
await page.goto("file://" + htmlPath);
await page.evaluate(() => document.fonts.ready);
await page.pdf({ path: out, format: "A4", preferCSSPageSize: true, printBackground: true });
await browser.close();
console.log(JSON.stringify({ base, fee: f, supply, vat, total, man }));
