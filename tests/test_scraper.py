"""네트워크 없이 파싱 함수만 검증한다. HTML은 docs/event-page-research.md 발췌."""

from backend.core.scraper import parse_detail, parse_list

LIST_ITEM = """
<ul>
  <li><a href="javascript:doView('6764');" class="event_thum_box">
    <div class="event_img"><img src="https://file.koreainvestment.com/Storage/customer/event/184x114_6152.png"></div>
    <div class="event_txt">
      <div class="ofh"><p class="title">국내주식 애프터마켓 이벤트</p><span class="event_ing">진행중</span></div>
      <p class="con">한투에서 48쿠폰받고 애프터 거래해요 ~</p>
      <p class="date">기간 : <span class="letter_0">2026.09.01 ~ 2026.09.30</span></p>
    </div>
  </a></li>
</ul>
"""

EMPTY_LIST = "<ul></ul>"

DETAIL_A = """
<div id="ifrmContent" style="display:none;">
  <p style="text-align: center;">
    <img alt="" src="https://file.koreainvestment.com/updata/namo/ELS.jpg" style="width: 1120px; height: 10756px;" /></p>
</div>
"""

DETAIL_C = """
<div id="ifrmContent" style="display:none;">
  <script>function init() {}</script>
  <form name="eventForm">
    <input name="event_num" type="hidden" value="6767" />
    <div class="mWrap"><div class="events_1">
      <img alt="BanKIS 국내주식 자산증대 이벤트" src="/inc/img/event/20260901_domestic_asset_promotion_event_h.png" usemap="#Map" />
    </div></div>
  </form>
</div>
"""

DETAIL_B = """
<div id="ifrmContent" style="display:none;">
  <form name="eventForm">
    <input name="EVENT_NUM" type="hidden" value="6780" />
    <div class="mWrap"><div class="events_1">
      <img alt="FY26 한가위 자산 이벤트" src="/inc/img/event/20260915_full_moon_event_h.png" usemap="#Map" />
      <div><iframe src="https://securities.koreainvestment.com/event/bankis/event_agree.html"></iframe></div>
      <div><input id="checkAgree" name="agree" type="checkbox" /></div>
      <map name="Map">
        <area alt="대상여부 조회하기" coords="180, 6305, 940, 6450" />
        <area alt="이벤트 신청하기" coords="180, 6675, 940, 6820" />
        <area alt="" coords="0, 0, 0, 0" />
      </map>
    </div></div>
  </form>
</div>
"""

DETAIL_D = """
<!--b:s-->
<form name="thisForm" method="post">
  <table><tr><td><div class="events_1">
    <img src="/event/image/nfaccount_home_underAge_20260901.png" usemap="#Map"/>
    <map name="Map"><area alt="이벤트 신청하기" coords="0, 0, 10, 10" /></map>
  </div>
  <div style="position:absolute; overflow:hidden; clip:rect(0 0 0 0) !important;">
    <div><span>BanKIS</span><p>투자의 시작, 주식 1주와 함께</p></div>
  </div>
  </td></tr></table>
</form>
<!--b:e-->
"""


def test_parse_list_item():
    (event,) = parse_list(LIST_ITEM)
    assert event["num"] == "6764"
    assert event["title"] == "국내주식 애프터마켓 이벤트"
    assert event["summary"] == "한투에서 48쿠폰받고 애프터 거래해요 ~"
    assert event["period_start"] == "2026.09.01"
    assert event["period_end"] == "2026.09.30"
    assert event["thumbnail_url"] == "https://file.koreainvestment.com/Storage/customer/event/184x114_6152.png"


def test_parse_list_empty():
    assert parse_list(EMPTY_LIST) == []


def test_parse_detail_a():
    detail = parse_detail(DETAIL_A)
    assert detail["template"] == "A"
    assert detail["image_url"] == "https://file.koreainvestment.com/updata/namo/ELS.jpg"
    assert detail["detail_title"] is None
    assert detail["actions"] == []
    assert detail["legacy_text"] is None


def test_parse_detail_c():
    detail = parse_detail(DETAIL_C)
    assert detail["template"] == "C"
    assert detail["image_url"] == (
        "https://securities.koreainvestment.com/inc/img/event/20260901_domestic_asset_promotion_event_h.png"
    )
    assert detail["detail_title"] == "BanKIS 국내주식 자산증대 이벤트"
    assert detail["actions"] == []
    assert detail["legacy_text"] is None


def test_parse_detail_b():
    detail = parse_detail(DETAIL_B)
    assert detail["template"] == "B"
    assert detail["image_url"] == (
        "https://securities.koreainvestment.com/inc/img/event/20260915_full_moon_event_h.png"
    )
    assert detail["detail_title"] == "FY26 한가위 자산 이벤트"
    assert detail["actions"] == ["대상여부 조회하기", "이벤트 신청하기"]
    assert detail["legacy_text"] is None


def test_parse_detail_d():
    detail = parse_detail(DETAIL_D)
    assert detail["template"] == "D"
    assert detail["image_url"] == (
        "https://securities.koreainvestment.com/event/image/nfaccount_home_underAge_20260901.png"
    )
    assert detail["actions"] == ["이벤트 신청하기"]
    assert "투자의 시작, 주식 1주와 함께" in detail["legacy_text"]
