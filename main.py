import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ------------------------------------------------------------
# 1. 페이지 기본 설정
# ------------------------------------------------------------
st.set_page_config(
    page_title="날짜별 박스오피스",
    page_icon="🎬",
    layout="wide",
)

st.title("🎬 날짜별 박스오피스")
st.caption("KOBIS 영화관입장권통합전산망 일별 박스오피스")


# ------------------------------------------------------------
# 2. 한국 시간 기준으로 오늘과 어제 날짜 계산
#    Streamlit Cloud 서버 시간이 한국 시간이 아닐 수 있으므로
#    Asia/Seoul 시간대를 직접 지정합니다.
# ------------------------------------------------------------
KST = ZoneInfo("Asia/Seoul")
today_kst = datetime.now(KST).date()
yesterday_kst = today_kst - timedelta(days=1)


# ------------------------------------------------------------
# 3. 조회 날짜 선택
#    오늘 데이터는 아직 집계 전일 수 있으므로
#    달력에서 선택할 수 있는 가장 늦은 날짜를 '어제'로 제한합니다.
# ------------------------------------------------------------
selected_date = st.date_input(
    "조회할 날짜를 선택하세요",
    value=yesterday_kst,
    max_value=yesterday_kst,
    help="오늘 데이터는 아직 집계 전이므로 어제까지만 선택할 수 있습니다.",
)

# KOBIS API는 날짜를 yyyymmdd 형식으로 받습니다.
target_dt = selected_date.strftime("%Y%m%d")

# 화면에는 보기 좋은 형식으로 표시합니다.
display_date = selected_date.strftime("%Y년 %m월 %d일")
st.subheader(f"{display_date} 박스오피스")


# ------------------------------------------------------------
# 4. KOBIS API 호출 함수
#    같은 날짜와 같은 인증키로 다시 조회하면
#    약 1시간 동안 저장된 결과를 재사용합니다.
# ------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def get_boxoffice(target_date: str, api_key: str):
    url = (
        "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
        "boxoffice/searchDailyBoxOfficeList.json"
    )

    params = {
        "key": api_key,
        "targetDt": target_date,
    }

    # 네트워크가 너무 오래 멈추는 것을 막기 위해 timeout을 지정합니다.
    response = requests.get(url, params=params, timeout=10)

    # HTTP 4xx, 5xx 오류가 있으면 예외를 발생시킵니다.
    response.raise_for_status()

    # JSON 응답으로 변환합니다.
    data = response.json()

    # KOBIS는 인증키 오류 등이 있어도 HTTP 상태코드 200을 보내고
    # 대신 faultInfo 상자를 넣는 경우가 있으므로 별도로 검사합니다.
    if "faultInfo" in data:
        fault = data.get("faultInfo", {})
        message = fault.get("message", "KOBIS API에서 오류가 발생했습니다.")
        raise ValueError(f"KOBIS 오류: {message}")

    # 정상 응답 안에서 영화 목록을 꺼냅니다.
    boxoffice_result = data.get("boxOfficeResult", {})
    movie_list = boxoffice_result.get("dailyBoxOfficeList", [])

    # 빈 목록도 그대로 돌려보냅니다.
    # 화면에서 사용자가 이해하기 쉬운 안내 문구를 보여 주기 위함입니다.
    return movie_list


# ------------------------------------------------------------
# 5. 비밀 금고(secrets)에서 인증키 읽기
#    인증키를 코드에 직접 적지 않습니다.
# ------------------------------------------------------------
try:
    api_key = st.secrets["KOBIS_KEY"]
except KeyError:
    st.error("KOBIS_KEY가 설정되어 있지 않습니다.")
    st.info(
        "Streamlit Cloud의 앱 설정에서 Secrets에 "
        'KOBIS_KEY = "발급받은_인증키" 형식으로 등록해 주세요.'
    )
    st.stop()


# ------------------------------------------------------------
# 6. API 요청
# ------------------------------------------------------------
try:
    with st.spinner("박스오피스 정보를 불러오는 중입니다..."):
        movie_list = get_boxoffice(target_dt, api_key)

except requests.exceptions.Timeout:
    st.error("KOBIS 서버의 응답 시간이 너무 오래 걸렸습니다.")
    st.info("잠시 후 다시 시도하거나 인터넷 연결 상태를 확인해 주세요.")
    st.stop()

except requests.exceptions.RequestException as e:
    st.error("KOBIS API 요청에 실패했습니다.")
    st.info(
        "인터넷 연결, KOBIS 서버 상태, 요청 주소가 올바른지 확인해 주세요."
    )
    st.caption(f"오류 정보: {e}")
    st.stop()

except ValueError as e:
    st.error(str(e))
    st.info(
        "KOBIS 인증키가 올바른지, API 이용 상태에 문제가 없는지 확인해 주세요."
    )
    st.stop()

except Exception as e:
    st.error("데이터를 처리하는 중 예상하지 못한 오류가 발생했습니다.")
    st.info("Secrets의 KOBIS_KEY 설정과 KOBIS API 응답 상태를 확인해 주세요.")
    st.caption(f"오류 정보: {e}")
    st.stop()


# ------------------------------------------------------------
# 7. 선택한 날짜의 영화 목록이 비어 있는 경우
# ------------------------------------------------------------
if not movie_list:
    st.warning("그날은 아직 집계 전입니다.")
    st.info("다른 날짜를 선택해 보세요.")
    st.stop()


# ------------------------------------------------------------
# 8. 표와 그래프에 사용할 데이터 정리
#    KOBIS의 숫자 값은 문자열이므로 실제 숫자형으로 변환합니다.
# ------------------------------------------------------------
df = pd.DataFrame(movie_list)

# 필요한 열만 사용합니다.
df = df[
    [
        "rank",
        "rankInten",
        "movieNm",
        "openDt",
        "audiCnt",
        "audiAcc",
        "scrnCnt",
    ]
].copy()

# 문자열 숫자를 실제 숫자형으로 변환합니다.
# 이렇게 해야 숫자 크기대로 정확히 정렬하고 그래프를 그릴 수 있습니다.
numeric_columns = ["rank", "rankInten", "audiCnt", "audiAcc", "scrnCnt"]

for column in numeric_columns:
    df[column] = pd.to_numeric(
        df[column],
        errors="coerce",
    ).fillna(0).astype(int)

# 순위 기준으로 정렬합니다.
df = df.sort_values("rank").reset_index(drop=True)


# ------------------------------------------------------------
# 9. 누적 관객 100만 명 초과 영화에 트로피 표시
# ------------------------------------------------------------
def add_trophy(movie_name, audience_total):
    if audience_total > 1_000_000:
        return f"{movie_name} 🏆"
    return movie_name


df["movieNmDisplay"] = df.apply(
    lambda row: add_trophy(row["movieNm"], row["audiAcc"]),
    axis=1,
)


# ------------------------------------------------------------
# 10. 전날 대비 순위 증감 표시
#     양수: 순위 상승 → ↑
#     음수: 순위 하락 → ↓
#     0: 변동 없음 → ―
# ------------------------------------------------------------
def make_rank_change(rank_change):
    if rank_change > 0:
        return f"↑ {rank_change}"
    if rank_change < 0:
        return f"↓ {abs(rank_change)}"
    return "―"


df["rankChangeDisplay"] = df["rankInten"].apply(make_rank_change)


# ------------------------------------------------------------
# 11. 1위 영화 표시
# ------------------------------------------------------------
first_movie = df.iloc[0]

st.markdown(f"### 🥇 1위: {first_movie['movieNmDisplay']}")

col1, col2, col3 = st.columns(3)

col1.metric(
    label="당일 관객수",
    value=f"{first_movie['audiCnt']:,}명",
)

col2.metric(
    label="누적 관객수",
    value=f"{first_movie['audiAcc']:,}명",
)

col3.metric(
    label="스크린수",
    value=f"{first_movie['scrnCnt']:,}개",
)

st.divider()


# ------------------------------------------------------------
# 12. 전체 박스오피스 표
# ------------------------------------------------------------
st.markdown("### 일별 박스오피스 순위")

# 화면에 보여 줄 열을 따로 만듭니다.
table_df = df[
    [
        "rank",
        "rankChangeDisplay",
        "movieNmDisplay",
        "openDt",
        "audiCnt",
        "audiAcc",
        "scrnCnt",
    ]
].copy()

table_df = table_df.rename(
    columns={
        "rank": "순위",
        "rankChangeDisplay": "순위 변동",
        "movieNmDisplay": "영화명",
        "openDt": "개봉일",
        "audiCnt": "관객수",
        "audiAcc": "누적관객",
        "scrnCnt": "스크린수",
    }
)

# 표에 보이는 숫자는 천 단위 쉼표를 넣어 읽기 쉽게 만듭니다.
# 원본 df의 값은 여전히 숫자형이므로 정렬과 그래프에는 문제가 없습니다.
table_df["관객수"] = table_df["관객수"].map(lambda x: f"{x:,}")
table_df["누적관객"] = table_df["누적관객"].map(lambda x: f"{x:,}")
table_df["스크린수"] = table_df["스크린수"].map(lambda x: f"{x:,}")


# 순위 변동 열에 색상을 적용합니다.
# ↑ 는 빨간색, ↓ 는 파란색으로 표시합니다.
def color_rank_change(value):
    text = str(value)

    if text.startswith("↑"):
        return "color: #d32f2f; font-weight: 700;"
    if text.startswith("↓"):
        return "color: #1976d2; font-weight: 700;"

    return "color: #666666;"


styled_table = table_df.style.map(
    color_rank_change,
    subset=["순위 변동"],
)

st.dataframe(
    styled_table,
    use_container_width=True,
    hide_index=True,
)


# ------------------------------------------------------------
# 13. 관객수 상위 5편 막대그래프
#     실제 숫자형 audiCnt를 기준으로 정렬합니다.
# ------------------------------------------------------------
st.markdown("### 관객수 상위 5편")

top5 = (
    df.sort_values("audiCnt", ascending=False)
    .head(5)
    [["movieNmDisplay", "audiCnt"]]
    .rename(
        columns={
            "movieNmDisplay": "영화명",
            "audiCnt": "관객수",
        }
    )
    .set_index("영화명")
)

st.bar_chart(top5)


# ------------------------------------------------------------
# 14. 하단 안내
# ------------------------------------------------------------
st.caption(
    f"조회 기준일: {display_date} · "
    "같은 날짜의 API 응답은 약 1시간 동안 캐시됩니다."
)
