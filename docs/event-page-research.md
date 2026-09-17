# 한국투자증권 이벤트 페이지 사전 리서치

조사일: 2026-09-17. 대상: `https://securities.koreainvestment.com/main/customer/notice/Event.jsp` 진행중 이벤트(gubun=i), 영업점(CUSTGUBUN=01)·뱅키스(CUSTGUBUN=02) 전 페이지 34건.

## 1. 현재 스크래퍼(`lib/scraper.js`) 선행검사

| 항목 | 결과 |
|---|---|
| 이벤트 수 | 20 (01: 10건, 02: 10건) |
| 상세 조회 실패 | 0 |
| 이미지 저장 | 20 / 20 |
| 텍스트 본문 | 1 (6780 — `"대상여부를 확인해주세요."`, 위젯 안내문) |
| 담당부서 | 20건 전부 null |
| 소요 시간 | 15.2초 (목록 2 + 상세 20 + 이미지 20 다운로드, 순차) |

**결함: 목록 1페이지만 읽는다.** 실제 진행중 이벤트는 영업점 13건, 뱅키스 25건, 합집합 34건이다. 현재 구현은 각 탭의 첫 10건만 수집해 14건을 놓치고, 01/02 중복 병합도 1페이지 안에서는 겹치는 건이 없어 `targets`가 두 개인 사례가 0건이다(2페이지까지 읽으면 4건 겹침).

## 2. 목록 페이지

### 2.1 탭·파라미터
| 파라미터 | 값 | 의미 |
|---|---|---|
| `gubun` | `i` / `v` / `t` | 진행중 이벤트 / 당첨자 발표 / 지난 이벤트 |
| `CUSTGUBUN` | `00` / `01` / `02` | 전체 / 영업점계좌 / 뱅키스계좌 |
| `cmd` | `TF04gb010001` | 목록 조회 (페이지 이동 시) |
| `currentPage` | 1.. | 페이지 번호 |
| `userRowsPerPage` | 10/15/20/30/50 | **쿼리로 넘겨도 무시됨**(`?userRowsPerPage=50` → 10건). `setRowsPerPage(this, 2, 'doSearch')`가 쿠키에 저장하는 방식으로 추정 |

"연금(DC/IRP)" 대상 탭은 없다. 연금 이벤트(6754, 6744, 6743, 6137 등)는 01·02 양쪽 목록에 함께 실린다.

### 2.2 페이지네이션
```html
<div class="pager">
  <a class="btn first disabled">처음으로</a> <a class="btn prev disabled">이전으로</a>
  <span class="num"><a class="on"><span class='hidden'>현재페이지</span>1</a> <a onclick="goPage('2');return false;">2</a></span>
  <a class="btn next disabled">다음으로</a> <a class="btn end disabled">마지막으로</a>
</div>
```
```js
function goPage(page) {
  document.searchForm.currentPage.value = page;
  document.searchForm.cmd.value = "TF04gb010001";
  document.searchForm.submit();   // method="get" action="?"
}
```
→ `?gubun=i&cmd=TF04gb010001&currentPage=N&CUSTGUBUN=XX` GET으로 그대로 재현된다. 마지막 페이지 다음은 항목 0건이 오므로 "빈 페이지가 나올 때까지" 또는 `.pager .num a` 개수로 종료 판단.

| 탭 | 페이지 수 | 건수 | 총 |
|---|---|---|---|
| 01 영업점 | 2 | 10 + 3 | 13 |
| 02 뱅키스 | 3 | 10 + 10 + 5 | 25 |
| 00 전체 | 4 | 10+10+10+4 | 34 (= 13 + 25 − 4 중복) |

01∩02 중복: **6754, 6744, 6743, 6137** (모두 연금 관련). 전체(00)에만 있는 이벤트는 없다 → 01·02 두 탭만 읽으면 전체를 덮는다.

### 2.3 항목 구조
```html
<li><a href="javascript:doView('6764');" class="event_thum_box">
  <div class="event_img"><img src="https://file.koreainvestment.com/Storage/customer/event/184x114_6152.png"></div>
  <div class="event_txt">
    <div class="ofh"><p class="title">국내주식 애프터마켓 이벤트</p><span class="event_ing">진행중</span></div>
    <p class="con">한투에서 48쿠폰받고 애프터 거래해요 ~</p>
    <p class="date">기간 : <span class="letter_0">2026.09.01 ~ 2026.09.30</span></p>
  </div>
</a></li>
```
상태 배지는 `gubun=i`에서 전부 `진행중`, `gubun=t`에서 전부 `종료`(같은 `.event_ing` 클래스). 정렬은 게시번호 내림차순이 아니다(6764가 6780보다 앞). 규칙은 미확인(추정: 관리자 지정 순서).

## 3. 상세 페이지

### 3.1 URL
`doView(num)`은 `searchForm`(GET)에 `cmd=TF04gb010002`, `num`을 채워 submit한다. 등가 GET:
```
/main/customer/notice/Event.jsp?gubun=i&cmd=TF04gb010002&num=<NUM>&currentPage=1&CUSTGUBUN=<01|02>
```
`gubun=v`로 바꾸면 당첨자 발표 게시물이 나오므로 `gubun=i`를 유지해야 한다. `CUSTGUBUN`은 01/02 어느 쪽으로 열어도 같은 본문(확인: 6754를 01로 열었을 때와 02 목록의 6754 동일 이미지).

### 3.2 본문 주입 메커니즘
본문은 페이지 안의 숨김 div에 있고, 하위 iframe이 부모 DOM에서 복사해 렌더링한다.
```html
<div id="ifrmContent" style="display:none;">  ...본문 HTML...  </div>
<iframe id="innerCtntIfm" src="/tfcommon/include/innerContent.jsp" ...></iframe>
```
`/tfcommon/include/innerContent.jsp`:
```js
document.write( parent.document.getElementById('ifrmContent').innerHTML );
jQuery(window).load(function(){
  jQuery(window.parent.document).find('#innerCtntIfm').css('height', jQuery(document).height()+'px');
});
```
→ 서버 응답 HTML에 본문이 이미 들어 있으므로 JS 실행 없이 `#ifrmContent`만 파싱하면 된다.

### 3.3 템플릿 분류 (34건)

| 유형 | 컨테이너 | 특징 | 건수 | num |
|---|---|---|---|---|
| A 단순 이미지 | `#ifrmContent > p > img` | script 없음, `updata/namo/*.jpg` 1장, `style="width:1120px;height:NNNNpx"` 명시 | 7 | 6733 6734 6735 6736 6777 6778 6779 |
| C 레이어형 | `#ifrmContent > form[name=eventForm] .events_1 > img[usemap]` | jQuery 로드 + `init(){}`, 이미지 1장, 신청 위젯 없음 | 6 | 6137 6719 6730 6753 6754 6767 6772 (6719는 area 1개) |
| B 인터랙티브 | C 구조 + 동의 iframe·체크박스·`<map>`·ajax 신청 스크립트 | `loginCheck()`/`validCheck()`/`getCano()`, 일부는 `<style>`·`<title>` 포함 | 19 | 6728 6731 6738 6739 6741 6743 6744 6745 6751 6757 6759 6762 6763 6764 6765 6766 6771 6780 (6780·6741·6731·6728은 계좌선택 위젯 포함) |
| D 구형 | `#ifrmContent` **없음**. `<!--b:s-->` 뒤 `form[name=thisForm] > table > .events_1 > img` | 신청 스크립트가 `<head>`에 있음, 이미지가 `/event/image/*.png`, **숨김 텍스트 전사본 포함** | 2 | 2432 6518 |

현재 스크래퍼는 `#ifrmContent` 기준이라 D형 2건은 이미지·본문 모두 null이 된다.

A형 골격:
```html
<div id="ifrmContent" style="display:none;">
  <p style="text-align: center;">
    <img alt="" src="https://file.koreainvestment.com/updata/namo/[2624774]ELS 이벤트 페이지(1120).jpg" style="width: 1120px; height: 10756px;" /></p>
</div>
```
C형 골격 (6767):
```html
<div id="ifrmContent" style="display:none;">
  <script src="/inc_renewal/plugins/jquery/jquery-3.7.1.js"></script><script src="/tfcommon/renewal/js/uilib.js"></script>
  <script>function init() {}</script>
  <form name="eventForm">
    <input name="event_num" type="hidden" value="6767" />
    <div class="mWrap"><div class="events_1">
      <img alt="BanKIS 국내주식 자산증대 이벤트" src="/inc/img/event/20260901_domestic_asset_promotion_event_h.png" usemap="#Map" />
    </div></div>
  </form>
</div>
```
B형 골격 (6780, 발췌):
```html
<div id="ifrmContent" style="display:none;">
  <meta ...><script src=".../jquery-3.7.1.js"></script><script src="/tfcommon/js/prototype.js"></script>
  <style> .custom-select{...} </style> <title>FY26 한가위 자산 이벤트</title>
  <script> var checkYn="N"; function loginCheck(num){ ...ajax POST /event/Event_Check.jsp... } ... </script>
  <form name="eventForm">
    <input name="cmd" type="hidden" /><input name="EVENT_NUM" type="hidden" value="6780" /><input name="BANKIS_EVNT_KIND_CD" type="hidden" value="..." />
    <div class="mWrap"><div class="events_1">
      <img alt="FY26 한가위 자산 이벤트" src="/inc/img/event/20260915_full_moon_event_h.png" usemap="#Map" />
      <div style="position:absolute; top:...">
        <iframe src="https://securities.koreainvestment.com/event/bankis/event_agree_20250228_pension.html" title="개인정보 수집,이용,제공 동의서"></iframe></div>
      <div style="position:absolute; ..."><input id="checkAgree" name="agree" type="checkbox" />
        <label for="agree" style="...clip:rect(0, 0, 0, 0) !important">고유식별정보 수집 동의</label></div>
      <div style="display:none;"><select id="CANO" name="CANO"></select></div>
      <div class="custom-select" id="customSelect" style="position:absolute; ...">
        <div class="custom-options" onclick="javascript:alert('대상여부를 확인해주세요.')">대상여부를 확인해주세요.</div></div>
      <map name="Map">
        <area alt="대상여부 조회하기" coords="180, 6305, 940, 6450" onclick="loginCheck('1');return false;" />
        <area alt="이벤트 신청하기" coords="180, 6675, 940, 6820" onclick="loginCheck('2');return false;" />
      </map>
    </div></div>
  </form>
</div>
```
D형 골격 (6518, 발췌):
```html
<!--b:s-->
<form name="thisForm" method="post"><input type="hidden" name="BANKIS_EVNT_KIND_CD" value="90"/>
  <table><div><div class="events_1">
    <img src="/event/image/nfaccount_home_underAge_20260901.png" usemap="#Map"/>
    ... 체크박스 / 동의 iframe / #customSelect / <map> ...
  </div>
  <div style="position:absolute; overflow:hidden; ... clip:rect(0 0 0 0) !important;">
    <div><span>BanKIS</span><p>투자의 시작, 주식 1주와 함께</p><h2>나도 이제 대한민국 대표 회사 주주다</h2>
      <dl><dt>기간</dt><dd>21년 11월 01일 ~ 12월 31일</dd><dt>대상</dt><dd>...</dd></dl></div>
  </div>
  <div style="... clip:rect(0 0 0 0) !important;">
    <div><h3>이벤트 유의사항</h3><h4>공통 유의사항</h4><ul><li>...</li></ul> ... </div>
  </div>
  </div></table>
</form>
<!--b:e-->
```

### 3.4 이미지 구성
- **34건 전부 본문 이미지 1장**. 이미지 페이지네이션·분할(여러 장 이어붙임)은 없다.
- 가로는 전부 **1120px**. 세로 분포:

| 유형 | 세로 px | 파일 크기 |
|---|---|---|
| A (`updata/namo/*.jpg`) | 7,175 ~ 14,064 | 1.2 ~ 3.9 MB |
| B/C (`/inc/img/event/*_h.png`, 6741만 .jpg) | 10,545 ~ 29,482 | 0.9 ~ 5.5 MB |
| D (`/event/image/*.png`) | 17,735 / 22,175 | 1.3 / 1.8 MB |

전체: 최소 7,175 / 중앙값 ≈ 15,600 / 최대 29,482 (6757). 파일 크기 합계 ≈ 67 MB.

- URL 패턴 3종. A형만 절대 URL이고(`file.koreainvestment.com` 또는 `file.truefriend.com` — 같은 CDN의 구 도메인), 나머지는 사이트 상대경로.
- `usemap="#Map"`은 B/C/D형(27건)에 있고, `<area>`의 `alt`가 버튼 텍스트다: `이벤트 신청하기`, `대상여부 조회하기`, `마케팅활용동의하기`, `계좌개설하기`, `청약중인 ELS/ELB 보러가기`, `OpenAPI 바로가기` 등. `coords`의 y값이 버튼의 이미지 내 위치(예: 6780 신청 버튼 y=6675~6820). C형 중 6754·6767·6772·6753·6730·6137은 `usemap`이 있어도 `<map>`이 없다.
- 이미지 안에 상세 조건·유의사항이 전부 들어 있고 HTML에는 텍스트가 없다(D형 제외).

### 3.5 텍스트 본문
- A/B/C형: 이벤트 내용 텍스트 없음. `.text()`로 나오는 것은 위젯 문구(`대상여부를 확인해주세요.`, 동의 라벨)와 `<title>`(B형 일부: `FY26 한가위 자산 이벤트`, `2026 금융 드림팀 시즌2`, `IRP·개인연금 이벤트`)뿐.
- D형 2건: `clip:rect(0 0 0 0)` 숨김 div 2개(175자 + 2,087자)에 배너 내용의 접근성 전사본(제목·기간·대상·혜택·유의사항)이 있다. 단 6518·2432 둘 다 **동일 텍스트**이며 기간이 `21년 11월 01일 ~ 12월 31일`로 이미지(2026.09)와 다르다 → 갱신되지 않은 옛 전사본으로 추정. 참고용으로만 저장하고 사실로 쓰면 안 된다.
- `<img alt>`: B/C/D형은 alt에 이벤트명이 있고(예: `BanKIS FY26 국내 주식선물달러선물 거래 활성화 이벤트`), A형은 빈 문자열.

### 3.6 담당부서
34건 전부 `<!-- 담당자 -->` 와 `<!--b:e-->` 사이가 공백이다. 채워진 사례 없음.
```html
    <!-- 담당자 -->
    (빈 줄)
<!--b:e-->
```

## 4. 요청 조건
| 항목 | 결과 |
|---|---|
| User-Agent | 없어도 200 + 목록 정상(180,557 bytes 동일). `curl/8.0`도 동일 |
| 쿠키/세션 | 불필요 |
| 인코딩 | `text/html; charset=utf-8` |
| 응답 크기 | 목록 ≈ 180 KB, 상세 ≈ 162 ~ 182 KB (공통 GNB·푸터 포함) |
| 응답 시간 | 목록 94 ~ 166 ms, 상세 90 ~ 121 ms |
| 봇 차단 | 각 페이지 `<head>`에 난독화 스크립트(`var VtdnL = {...}`, `alert('threat detected!!!')`)가 있으나 GET 응답 자체는 완전함. 실제 차단 동작은 미확인 |

## 5. 시사점

1. **페이지네이션 필수.** `currentPage`를 1부터 올려 항목 0건까지 읽어야 34건이 된다(현재 20건). 01·02 두 탭이면 충분하고 00은 불필요. 중복 4건은 num 병합으로 `targets` 2개가 된다.
2. **D형 처리.** `#ifrmContent`가 없으면 `<!--b:s-->…<!--b:e-->` 구간(또는 `form[name=thisForm] .events_1`)으로 fallback. 이미지 URL은 상대경로 3종을 모두 `new URL(src, BASE)`로 절대화하면 된다.
3. **이벤트당 이미지 1장, 세로 7k~30k px.** 타일 분할은 세로 기준. 1120×1500이면 최대 20조각(6757), 중앙값 11조각. 1120×2000이면 최대 15조각 — 글자 크기가 큰 배너(1120px 폭 기준 본문 글자 ≈ 30~40px)라 2000px 타일도 판독 가능할 것으로 추정. 조각 경계에서 문장이 잘리므로 100~200px 오버랩을 두는 편이 안전. MCP image content 1건에 타일 하나씩, 이미지 1장을 여러 호출로 나눠 보낼 설계가 필요(base64 1.5~5.5 MB를 한 응답에 넣기 어려움).
4. **재다운로드 기준은 URL.** 같은 num이라도 이미지가 교체되면 파일명이 바뀐다(namo 업로드 파일명·`/inc/img/event/YYYYMMDD_*` 날짜 포함). URL이 같으면 재분석 불필요. 파일 크기(Content-Length)나 해시를 함께 저장하면 같은 URL 덮어쓰기까지 잡을 수 있다(추정: 발생 빈도 낮음).
5. **텍스트 필드 정책.** A/B/C형은 저장할 텍스트가 없으므로 `detail_text`는 `<img alt>` + B형 `<title>` 정도만 의미가 있다. 위젯 문구(`대상여부를 확인해주세요.`, `custom-options`)는 제외. D형 숨김 전사본은 `stale 가능` 표시로 별도 컬럼에 두는 것이 낫다.
6. **버튼 메타.** `<map><area alt>`는 이벤트의 참여 방식(신청/대상조회/계좌개설 링크)을 알려주는 유일한 구조화 텍스트라 저장 가치가 있다.
7. **담당부서는 현재 데이터로는 얻을 수 없다.** 스키마에 두되 NULL 전제로.
8. **상태·종료 판정.** 목록 배지는 탭에 종속(`gubun=i`면 항상 진행중)이라 상태 컬럼은 "어느 탭에서 보였나"와 `period_end`로 계산하는 편이 정확. 목록에서 사라진 건은 `gubun=t`(지난 이벤트)에서 재확인 가능.
9. **부하.** 34건 전체 스크랩 = 요청 5(목록) + 34(상세) + 34(이미지 ≈ 67 MB). 이미지는 URL 변경 시에만 받으면 정기 실행 부하는 HTML 39건 ≈ 7 MB 수준.

## 6. 이미지 메타데이터 추출 설계

실측: 6767(C형, 20,190px → 11타일), 6780(B형, 16,520px → 9타일), 6777(A형, 10,756px → 6타일)을 모델이 직접 읽음. 본문 글자(약 30~40px)는 1120×2000 안팎의 타일에서 선명하게 판독된다. 고정 높이로 자르면 문장이 경계에서 잘리므로(6767 타일 2 하단 "※ 순입고액은 1천만 단위로…") 분할 위치를 여백 행으로 옮기는 전략을 §6.6에서 확정했다.

### 6.1 배너 내용의 공통 구조
세 유형 모두 같은 순서로 구성된다.

| 구간 | 내용 | 예 (6767 국내주식 자산입고) |
|---|---|---|
| 헤더 | 기간(짧은 표기), 제목, 헤드라인 혜택 | `26.9.1~10.30`, `최대 421만원 혜택 *조건 충족시` |
| 기간 박스 | 신청 기간 + 부가 기간(자산유지 등) | `신청 2026.9.1(화)~10.30(금) (자산유지: 2026.11.30일까지)` |
| 혜택 블록 ×N | `[혜택 n]` 제목, 리워드, 조건 목록, 한도, 빨간 글씨 감액·제외 조건, 예시 | `순입고 1천만원당 4만원, 최대 400만원(잔고 유지 필수)` / `50명 추첨(총 100명 대상)` |
| 참여 방법 | 단계(01·02·03), 신청 경로, QR | `한국투자앱 → 혜택`, "별도 신청 없이 자동 참여"(6777) |
| 대상·제외 | 계좌 관리점, 상품 계좌 범위, 동의서 | `관리점이 영업점인 계좌만 신청 가능`, `IRP·개인연금 계좌 내 가입분 제외`(6780) |
| 유의사항 | 10~20개 불릿: 세금(제세공과금 22%), 지급 시기, 잔고 유지, 경품 변경 | `종료 후 2개월 이내 추첨`, `1인당 최대 갤럭시 워치 울트라 2(약 97만원)` |
| 푸터 | 준법감시인 심사필 번호 + 유효기간, 고객센터 | `제2026-1704호(2026.09.01~2026.10.30)`, `1544-5000` |

B형은 이미지 중간에 실제 위젯(동의 iframe, `대상 조회하기`·`이벤트 참여하기` 버튼)이 겹쳐지는 자리가 여백으로 비어 있다(6780 타일 3). HTML의 `<map><area alt>`와 대응된다.

### 6.2 저장 구조: 전사(transcript)와 구조화(analysis)를 분리
비전 작업(비쌈, 타일 단위)과 구조화 작업(쌈, 텍스트만)을 나눈다. 전사를 남겨두면 스키마를 바꿔도 이미지를 다시 읽지 않고 재구조화할 수 있고, 전문 검색(FTS)에도 그대로 쓸 수 있다.

```
event_images   id, event_num, url, local_path, width, height, bytes, sha256, tile_count,
               status: pending → transcribing → transcribed → analyzed | failed
image_tiles    image_id, idx, y0, y1, overlap(0|150), text, transcribed_at  -- 타일별 원문 전사, 절단 위치는 §6.6
image_analysis image_id, schema_version, summary, json, analyzed_at -- 이미지당 1행
FTS5           tiles.text + analysis.summary
```

에이전트 흐름(MCP):
1. `get_pending_tiles(limit=2)` → 진행 중인 이미지의 다음 타일부터 image content로 반환(타일당 JPEG q80 ≈ 150~300 KB). 응답에 `image_id, tile_idx/total, y0-y1, event_title` 포함.
2. `save_tile_text(image_id, idx, text)` — 보이는 글자를 그대로 전사. 여백 절단이 성공한 타일(`overlap=0`)은 중복이 없고, 폴백으로 겹쳐 자른 타일만 응답에 `overlap=150`을 표시해 "상단의 중복 줄은 생략"하도록 tool 설명에 명시.
3. 마지막 타일이 저장되면 status=`transcribed`. `get_transcript(image_id)`로 전체 텍스트를 받아 6.3 스키마로 구조화 → `save_analysis(image_id, json, summary)`. 백엔드는 pydantic으로 검증 후 `analyzed`.
4. `list_events`는 `pending_image_count`를 함께 돌려주고, tool 설명에 "pending이 있으면 1~3을 먼저 수행"을 명시.

비용 추정: 타일 1장 ≈ 1.5k 토큰(모델 측 리사이즈 후) → 이미지 1장 4~15타일 ≈ 6~22k, 34건 초기 전량 ≈ 40~50만 토큰. 정기 실행에서는 URL이 바뀐 이미지만 다시 든다.

### 6.3 구조화 스키마 (`schema_version: 1`)
```json
{
  "title": "국내주식 자산입고 이벤트 한투로 가져오기",
  "tagline": "최대 421만원 혜택 *조건 충족시",
  "periods": [
    {"type": "신청", "start": "2026-09-01", "end": "2026-10-30"},
    {"type": "자산유지", "start": null, "end": "2026-11-30"}
  ],
  "targets": {
    "account_types": ["뱅키스"],
    "customer_types": ["전체"],
    "conditions": ["타사에서 국내주식 입고", "이벤트 기간 내 1천만원 이상 거래"]
  },
  "max_benefit_krw": 4210000,
  "benefits": [
    {
      "name": "순입고 리워드",
      "reward_type": "현금",
      "reward": "순입고 1천만원당 4만원",
      "reward_amount_krw": 4000000,
      "conditions": ["순입고 = 총 타사입고 - 총 타사출고 - 당사 타명의계좌출고", "이벤트 기간 내 1천만원 이상 거래 필수", "잔고 유지 필수"],
      "cap": "최대 400만원",
      "lottery": null,
      "caveats": ["뱅키스계좌 외 영업점계좌 이체도 감액 대상", "매도 후 출금 시 순출금액만큼 차감"],
      "examples": ["순입고 1,250만원 + 거래 1천만원 이상 → 4만원"]
    },
    {
      "name": "추첨 경품",
      "reward_type": "추첨",
      "reward": "50명 추첨 (총 100명 대상)",
      "reward_amount_krw": null,
      "conditions": [],
      "cap": null,
      "lottery": {"winners": 100, "note": "50명 × 2회"},
      "caveats": [],
      "examples": []
    }
  ],
  "participation": {
    "requires_application": true,
    "auto_enroll": false,
    "channels": ["한국투자앱 → 혜택"],
    "steps": ["뱅키스 계좌 준비(미보유 시 비대면 개설)", "거래 증권사에 출고 요청", "뱅키스로 거래"],
    "consents": ["개인정보 수집·이용·제공 동의"]
  },
  "products": ["국내주식"],
  "payout": {"timing": null, "method": null},
  "exclusions": ["IRP·개인연금 계좌 내 가입분"],
  "tax_note": "총 수령금액 5만원 초과 시 제세공과금(22%) 당사 부담, 기타소득 귀속",
  "notes": ["ETF 거래비용 별도", "정상수수료 0.0130527%~0.0140527%"],
  "compliance": {"number": "제2026-1704호", "valid_from": "2026-09-01", "valid_to": "2026-10-30"},
  "contact": "1544-5000",
  "confidence": {"overall": 0.9, "unreadable": []}
}
```
(6767 타일 0·2·5·10만 읽고 채운 예시라 일부 값은 비어 있다. 6780의 `대상 조회하기` 위젯 문구처럼 HTML `<area alt>`와 겹치는 항목은 `participation.channels`에 합친다.)

통제 어휘 — 질의("영업점 고객대상 이벤트", "ELS 이벤트")에 바로 매칭되도록 자유 문장이 아니라 고정값을 쓴다.
- `periods[].type`: 신청 | 거래 | 자산유지 | 지급 | 추첨 | 공모
- `targets.account_types`: 영업점 | 뱅키스 | 연금(IRP·DC·개인연금)
- `targets.customer_types`: 전체 | 신규 | 휴면 | 기존 | 미성년
- `benefits[].reward_type`: 현금 | 쿠폰 | 상품권 | 경품 | 수수료할인 | 추첨 | 축하금
- `products`: 국내주식 | 해외주식 | 선물옵션 | ELS·ELB | 펀드 | 채권 | RP | ISA | 연금 | 계좌개설 | OpenAPI

### 6.4 필드 우선순위와 충돌 규칙
- **대상(`targets.account_types`)**: 목록 탭(CUSTGUBUN)이 1차 진실이고 이미지 값은 보강. 둘이 다르면 탭 값을 유지하고 이미지 값은 `targets.conditions`에 문장으로 남긴다(예: 6780은 01·02 양쪽 탭이지만 이미지에는 "관리점이 영업점인 계좌만").
- **기간**: 목록 `.date`가 신청 기간, 이미지의 추가 기간(자산유지·지급)은 `periods[]`에만 있다. 목록과 이미지의 신청 기간이 다르면 `confidence.unreadable`에 기록하고 목록 값을 쓴다.
- **금액**: `max_benefit_krw`, `reward_amount_krw`는 원 단위 정수. "약 97만원 상당" 같은 환산치는 `reward` 문장에 두고 숫자 필드는 null.
- **유의사항**: 전문은 `image_tiles.text`에 있으므로 `notes`에는 답변에 쓸 5개 내외만 요약.
- `summary`(200자 내외): 대상 + 핵심 혜택 + 기간 한 문장. `list_events` 응답에 이 필드만 실어 토큰을 아낀다.

### 6.5 결정 사항 요약
| 항목 | 값 | 근거 |
|---|---|---|
| 타일 | 목표 2000px, 여백 행에서 절단(1600~2400), 실패 시 150 오버랩 폴백 | §6.6 — 3장 26개 절단점 전부 여백에 안착, 문장 잘림 0 |
| 포맷 | JPEG q80 | 타일당 150~300 KB, PNG 대비 1/5 |
| 호출당 타일 수 | 1~3 | 응답 크기 ≤ 1 MB 유지 |
| 저장 단위 | 타일 전사 + 이미지당 JSON 1개 + summary | 재구조화·FTS·토큰 절약 |
| 재분석 트리거 | 이미지 URL 또는 sha256 변경 | §5-4 |
| 스키마 검증 | pydantic, `schema_version` 컬럼 | 스키마 변경 시 전사만으로 재생성 |

### 6.6 타일 분할 전략: 여백 행 절단
배너는 섹션 사이에 단색 띠(여백)가 반드시 있으므로, 고정 높이 대신 목표 높이 근처에서 가장 "잉크가 없는" 행을 골라 자른다. 오버랩이 필요 없어져 중복 전사가 사라지고 타일 수도 같다.

알고리즘 (Pillow + numpy):
```
g = grayscale(image)
score[y] = std(g[y, :]) + mean(|g[y, :] - g[y-1, :]|)   # 행이 단색이고 윗행과 같으면 0
y = 0
while height - y > 2400:
    후보 = [y+1600, y+2400)
    cut = 후보 중 20px 띠 평균 score가 최소인 곳의 중앙
    tiles.append((y, cut)); y = cut
tiles.append((y, height))
```
- 배경색이 흰색·남색·회색 어느 것이든 "균일한 띠"면 0점이라 색 가정이 없다.
- 폴백: 후보 구간의 최소 score가 임계값(예: 2.0)을 넘으면 여백이 없는 것이므로 `y+2000`에서 자르고 다음 타일을 150px 겹쳐 시작(`overlap=150`).
- 모델 측 리사이즈(긴 변 1568px) 기준으로 2400px 타일은 글자가 약 0.65배가 되지만 30px 본문은 여전히 판독됐다(6767 타일 2, 2388px). 2400을 상한으로 둔다.

실측 결과 (3장, 절단점 26개):

| num | 높이 | 타일 수 | 타일 높이 | 절단점 score |
|---|---|---|---|---|
| 6767 | 20,190 | 11 | 1610 ~ 2388 | 전부 0.0 |
| 6780 | 16,520 | 9 | 1610 ~ 2365 | 전부 0.0 |
| 6777 | 10,756 | 6 | 1616 ~ 2037 | 0.0 ×4, 2.5 ×1 (연한 그라데이션 배경, 글자 없음) |

6767에서 고정 절단 시 잘렸던 "※ 순입고액은…" 문장은 여백 절단에서 [혜택 1] 박스와 함께 타일 2 안에 온전히 들어가고, 타일 3은 [혜택 2] 제목부터 시작한다.

추가로 검토했으나 채택하지 않은 것:
- **좌우 여백 크롭**: 배너 양옆 약 80px가 빈 공간이지만 토큰 절감이 10% 미만이라 생략.
- **타일 축소(1120 → 840px)**: 토큰은 약 40% 줄지만 유의사항의 28px 글자가 리사이즈 후 15px 이하가 되어 오독 위험. 채택 안 함.
- **섹션 제목 검출로 의미 단위 분할**: `[혜택 n]` 같은 헤더를 찾으려면 OCR이 선행돼야 해 순환. 여백 절단만으로 실측상 섹션 경계에 맞아떨어짐.

## 7. 요약 정보 블록 조사와 스키마 v2 (2026-09-17, 진행중 20건 전수)

추출 목표를 네 항목(기간·대상·대상 상품/계좌·실적 인정)으로 좁히고, 이 정보가 배너 상단에 모여 있는지 진행중 34건 중 최근 20건의 상단 4,000px(57타일)을 전부 읽어 확인했다. 원시 기록은 `docs/survey-ongoing-20.json`.

### 7.1 결과
| 항목 | 값 |
|---|---|
| 정보 블록 발견 | 20/20 |
| 4,000px 안에 완전 포함 | 20/20 |
| 블록 시작 y | 1,400 ~ 1,800 (중앙값 1,700) |
| 블록 끝 y | 2,275 ~ 3,450 (중앙값 2,400; 4항목 블록만 3,300 이상) |
| 기간·대상 라벨이 블록 안에 있음 | 20/20 |
| 대상 상품/계좌 존재 | 9/20 (블록 안 6, 첫 섹션 3) |
| 실적 인정 존재 | 라벨 있음 7/20(전부 블록 안), 라벨 없는 문장까지 12/20 |
| 대상 판정(제목+이미지만으로) | 영업점 4 · 뱅키스 15 · 연금 1 · 미상 0 |

라벨 원문 빈도:

| 필드 | 라벨 | 건수 |
|---|---|---|
| 기간 | 이벤트 기간 | 18 (6767은 `신청 :`/`자산유지 :` 하위 줄) |
| 기간 | 참가 신청 + 대회 기간 / 이벤트 신청 기간 + 챌린지 기간 | 1 / 1 |
| 대상 | 참여대상 / 이벤트 대상 / 대상 고객 / 참가 대상 | 16 / 2 / 1 / 1 |
| 상품·계좌 (블록) | 대상 상품 2, 대상 계좌+대상 시장 1, 실적기준›대상 종목 1, 챌린지 내용›대상 1, 참여조건 1 | 6 |
| 상품·계좌 (첫 섹션) | `대상계좌`/`대상상품` 칩 또는 문장 | 3 |
| 실적 인정 (블록) | 실적 인정 2, 실적기준+참여방법 1, 실적 조건 1, 참여조건 3 | 7 |
| 실적 인정 (첫 섹션, 라벨 없음) | 문장형 | 5 |

블록은 항상 타일 0의 끝과 타일 1에 걸친다(2,000px 절단이 블록 경계 근처). 대상 밑의 `#해시태그`·회색 소문·칩이 곧 조건/제외 목록이다.

### 7.2 v2가 못 담은 케이스와 대응
| 케이스 | 예 | 대응 |
|---|---|---|
| 자격 판정 기간(신청 기간과 별개) | 6766/6765 "4.1~8.31 무거래", 6771 "7월~8/21 거래 5천만원 이하" | `periods[].type`에 `자격판정` 추가 |
| `참여조건` 라벨의 다의성 | 6771=자격, 6764=절차, 6751=상품 범위 | 라벨이 아니라 내용으로 분류. 자격→`target.conditions`, 절차→`criteria.performance`, 상품→`criteria.products` |
| `챌린지 기간` | 6753 | `대회`로 매핑 |
| 판정·지급일이 그래픽·각주에만 | 6757 EARLY 8/31·FINAL 9/30, 2432 "5영업일 내 지급" | `periods[].type` `지급`, 없으면 생략(전체 분석 v1의 몫) |
| 대상 시장·시간대 | 6778 16~20시, 6764 15:40~20:00 | `criteria.text` 문장으로 |
| 블록 밖 정보가 대상을 좁힘 | 6759 히어로 "ISA 중개형", 6745 "최초신규" 배지 | 상단 4,000px 전체를 보고 판단하도록 안내문에 명시 |
| 이미지·목록 표기 불일치 | 6757 8.19 vs 8.18, 6751 연도 없음 | 날짜는 목록 값 우선, 이미지 값이 다르면 `notes`에 기록 |
| 블록 직후 무관한 표 | 6765 필요 이수 시간 | 블록 끝을 정확히 자를 필요 없음 — 4,000px 고정 |

### 7.3 확정: 요약 추출 스키마 v2
이미지 1장 = 상단 4,000px 타일 2~3장 = MCP 호출 1회. 전체 전사(§6)는 별도 2단계로 남긴다.
```json
{
  "title": "국내주식 자산입고 이벤트 한투로 가져오기",
  "periods": [
    {"type": "신청", "start": "2026-09-01", "end": "2026-10-30"},
    {"type": "자산유지", "start": null, "end": "2026-11-30"}
  ],
  "target": {
    "text": "BanKIS 주식계좌(01) 보유 고객",
    "account_types": ["뱅키스"],
    "evidence": "BanKIS 주식계좌(01) 보유 고객 / #영업점 계좌 제외",
    "customer_types": ["전체"],
    "conditions": ["이벤트 신청", "마케팅 동의 필수"],
    "exclusions": ["영업점 계좌"]
  },
  "criteria": {
    "text": "대상 종목 국내주식(KOSPI·KOSDAQ·K-OTC·코넥스, ETF·ETN·ELW 제외) / 순입고금액 = 기간 내 총입고-총출고, 순출금 감액",
    "accounts": ["위탁계좌(01)"],
    "products": ["국내주식"],
    "performance": "1천만원 이상 타사대체 순입고 + 1천만원 이상 거래 + 11/30까지 자산유지",
    "source": "block"
  },
  "notes": ["이미지 기간 표기 8.19 vs 목록 8.18"],
  "block_found": true
}
```
- `periods[].type`: 신청 | 자격판정 | 대회 | 자산유지 | 지급 — 필수 1개 이상, 목록 기간은 `신청`.
- `target.account_types`: 영업점 | 뱅키스 | 연금 | 전체 | 미상 — **목록 탭이 아니라 제목·이미지 문구만으로** 판단하고 근거를 `evidence`에 남긴다. `customer_types`: 전체 | 신규 | 휴면 | 기존 | 미성년.
- `criteria`: 상품/계좌/실적을 한 필드로. `text`가 본체이고 `accounts`·`products`·`performance`는 있을 때만. 없으면 `criteria: null`. `source`: block | first_section.
- `products` 어휘는 v1과 같다(국내주식 | 해외주식 | 선물옵션 | ELS·ELB | 펀드 | 채권 | RP | ISA | 연금 | 계좌개설 | OpenAPI).
- `block_found=false`면 v1 전체 전사 경로로 폴백.

### 7.4 파이프라인 결정
| 항목 | 값 |
|---|---|
| 요약 타일 | `plan_tiles` 결과 중 `y0 < 4000`인 타일(2~3장), JPEG q75 |
| 호출 | `get_summary_tiles(limit=1)` → 이미지 1장의 타일 전부 + 목록 메타(제목·기간) → `save_summary(image_id, json)` |
| 상태 | `pending → summarized`(v2 저장) → `analyzed`(v1까지 저장, 선택) |
| 대상 필터 | `events.targets`(탭 기반)를 버리고 `image_summary.account_types`를 쓴다. 크롤링은 `CUSTGUBUN=00` 하나 |
| 우선순위 | 진행중 이벤트 먼저, 그다음 `period_end` 내림차순 |
| 모델 | 4필드 요약은 Sonnet급으로 충분(라벨 읽기 + 짧은 구조화) |
