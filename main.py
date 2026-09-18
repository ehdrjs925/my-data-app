import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ------------------------------------------------------------
# 1. 페이지 기본 설정
# ------------------------------------------------------------
st.set_page_config(
    page_title="어제의 박스오피스",
    page_icon="🎬",
    layout="wide",
)

st.title("🎬 어제의 박스오피스")
st.caption("KOBIS 영화관입장권통합전산망 일별 박스오피스")

# ------------------------------------------------------------
# 2. 한국 시간 기준으로 '어제' 날짜 계산
#    배포 서버가 한국 시간이 아니어도 정확하게 계산하기 위해
#    Asia/Seoul 시간대를 직접 지정합니다.
# ------------------------------------------------------------
KST = ZoneInfo("Asia/Seoul")
today_kst = datetime.now(KST).date()
yesterday_kst = today_kst - timedelta(days=1)

# KOBIS API는 날짜를 yyyymmdd 형식으로 받습니다.
target_dt = yesterday_kst.strftime("%Y%m%d")

# 화면에는 보기 좋은 형식으로 표시합니다.
display_date = yesterday_kst.strftime("%Y년 %m월 %d일")
st.subheader(f"{display_date} 박스오피스")

# ------------------------------------------------------------
# 3. KOBIS API 호출 함수
#    같은 날짜를 다시 조회하면 1시간 동안 저장된 결과를 사용합니다.
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

    # 네트워크가 오래 멈추는 것을 막기 위해 timeout을 지정합니다.
    response = requests.get(url, params=params, timeout=10)

    # 일반적인 HTTP 오류를 확인합니다.
    response.raise_for_status()

    # JSON 응답으로 변환합니다.
    data = response.json()

    # KOBIS는 인증키 오류 등이 있어도 HTTP 200을 보내고
    # 대신 faultInfo를 넣어 주는 경우가 있으므로 따로 검사합니다.
    if "faultInfo" in data:
        fault = data.get("faultInfo", {})
        message = fault.get("message", "KOBIS API에서 오류가 발생했습니다.")
        raise ValueError(f"KOBIS 오류: {message}")

    # 정상 응답 안에서 영화 목록을 꺼냅니다.
    boxoffice_result = data.get("boxOfficeResult", {})
    movie_list = boxoffice_result.get("dailyBoxOfficeList", [])

    # 목록이 비어 있으면 화면에 안내할 수 있도록 오류를 발생시킵니다.
    if not movie_list:
        raise ValueError("조회된 영화 목록이 없습니다.")

    return movie_list


# ------------------------------------------------------------
# 4. 비밀 금고(secrets)에서 인증키 읽기
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
# 5. API 요청
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
        "KOBIS 인증키가 올바른지, 조회 날짜에 데이터가 존재하는지, "
        "API 이용 상태에 문제가 없는지 확인해 주세요."
    )
    st.stop()

except Exception as e:
    st.error("데이터를 처리하는 중 예상하지 못한 오류가 발생했습니다.")
    st.info("Secrets의 KOBIS_KEY 설정과 KOBIS API 응답 상태를 확인해 주세요.")
    st.caption(f"오류 정보: {e}")
    st.stop()

# ------------------------------------------------------------
# 6. 표에 사용할 데이터 정리
#    KOBIS의 숫자 값은 문자열이므로 숫자로 변환합니다.
# ------------------------------------------------------------
df = pd.DataFrame(movie_list)

# 필요한 열만 사용합니다.
df = df[
    ["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]
].copy()

# 문자열 숫자를 실제 숫자형으로 변환합니다.
numeric_columns = ["rank", "audiCnt", "audiAcc", "scrnCnt"]

for column in numeric_columns:
    df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0).astype(int)

# 순위 기준으로 정렬합니다.
df = df.sort_values("rank").reset_index(drop=True)

# ------------------------------------------------------------
# 7. 1위 영화 표시
# ------------------------------------------------------------
first_movie = df.iloc[0]

st.markdown(f"### 🥇 1위: {first_movie['movieNm']}")

col1, col2, col3 = st.columns(3)

col1.metric(
    label="어제 관객수",
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
# 8. 전체 박스오피스 표
# ------------------------------------------------------------
st.markdown("### 일별 박스오피스 순위")

table_df = df.rename(
    columns={
        "rank": "순위",
        "movieNm": "영화명",
        "openDt": "개봉일",
        "audiCnt": "관객수",
        "audiAcc": "누적관객",
        "scrnCnt": "스크린수",
    }
)

st.dataframe(
    table_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "순위": st.column_config.NumberColumn(format="%d"),
        "관객수": st.column_config.NumberColumn(format="%,d"),
        "누적관객": st.column_config.NumberColumn(format="%,d"),
        "스크린수": st.column_config.NumberColumn(format="%,d"),
    },
)

# ------------------------------------------------------------
# 9. 관객수 상위 5편 막대그래프
#    숫자형으로 바꾼 audiCnt를 기준으로 다시 정렬합니다.
# ------------------------------------------------------------
st.markdown("### 관객수 상위 5편")

top5 = (
    df.sort_values("audiCnt", ascending=False)
    .head(5)
    [["movieNm", "audiCnt"]]
    .rename(columns={"movieNm": "영화명", "audiCnt": "관객수"})
    .set_index("영화명")
)

st.bar_chart(top5)

st.caption(
    f"조회 기준일: {display_date} · "
    "같은 날짜의 API 응답은 약 1시간 동안 캐시됩니다."
)
# my-data-app
