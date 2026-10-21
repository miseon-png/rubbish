import streamlit as st
import pandas as pd
import datetime
import random
import math
import calendar
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="폐기물 관리 대장 자동화", layout="wide")
st.title("♻️ 폐기물 관리 대장 시스템")

# 구글 시트 주소
SHEET_URL = "https://docs.google.com/spreadsheets/d/1iQmVbmKtyhNv80k7jqdalyaCX9At01Lju6bJM6aVkBk/edit"

# --- 구글 시트 연동 함수 ---
@st.cache_resource
def get_gspread_client():
    try:
        secret_dict = st.secrets["gcp_service_account"]
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = Credentials.from_service_account_info(secret_dict, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        return None

client = get_gspread_client()

# --- 탭 구성 ---
tab1, tab2, tab3 = st.tabs(["📝 데이터 입력", "📋 폐기물 처리 리스트 조회", "🖨️ 양식 출력 및 월마감"])

# --- 탭 1: 데이터 입력 ---
with tab1:
    st.header("1. 매일/매주 통수량 입력")
    
    col1, col2, col3 = st.columns(3)
    year = col1.number_input("년도", value=2026, step=1)
    month = col2.number_input("월", value=10, min_value=1, max_value=12, step=1)
    num_days = calendar.monthrange(year, month)[1]
    
    prev_unhandled = col3.number_input("전월 미처리량(Kg)", min_value=0, value=100, step=10)
    
    st.info("💡 **팁:** 기존에 구글 시트에 저장해둔 이번 달 데이터가 있다면 먼저 불러오세요.")
    
    # 세션 상태 초기화
    if 'bucket_inputs' not in st.session_state or st.session_state.get('current_month') != month:
        st.session_state.bucket_inputs = [0] * num_days
        st.session_state.current_month = month

    sheet_name = f"DB_{year}_{month:02d}"

    # 기존 데이터 불러오기 버튼
    if st.button("☁️ 구글시트에서 이번 달 기존 입력값 불러오기"):
        if client:
            try:
                doc = client.open_by_url(SHEET_URL)
                worksheet = doc.worksheet(sheet_name)
                records = worksheet.get_all_records()
                
                # 통수량만 추출하여 입력창에 반영
                loaded_buckets = []
                for idx in range(num_days):
                    if idx < len(records):
                        # 통수량이 빈칸이면 0으로 처리
                        val = records[idx].get("통수량", 0)
                        loaded_buckets.append(int(val) if val != "" else 0)
                    else:
                        loaded_buckets.append(0)
                        
                st.session_state.bucket_inputs = loaded_buckets
                st.success(f"{month}월 기존 데이터를 성공적으로 불러왔습니다!")
                st.rerun()
            except gspread.exceptions.WorksheetNotFound:
                st.warning("아직 이번 달에 저장된 데이터(시트)가 없습니다. 새로 입력을 시작하세요.")
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")
        else:
            st.error("구글 시트 인증에 실패했습니다. Secrets 설정을 확인하세요.")

    # 통수량 입력을 위한 데이터 프레임
    df_input = pd.DataFrame({
        "일자": [f"{month}월 {i:02d}일" for i in range(1, num_days + 1)],
        "통수량": st.session_state.bucket_inputs
    })

    st.write("▼ 각 일자별 처리한 **통수(1통=120kg)**를 입력/수정하세요.")
    edited_df = st.data_editor(df_input, num_rows="fixed", use_container_width=True)

    if st.button("🚀 계산 및 구글시트에 전체 저장 (업데이트)", type="primary"):
        bucket_counts = edited_df["통수량"].tolist()
        current_stock = prev_unhandled
        last_process_day = 0
        daily_generated = [0] * num_days
        
        # 역산 분배 로직 (금요일 2배, 15% 랜덤 오차)
        for i in range(num_days):
            buckets = int(bucket_counts[i])
            if buckets > 0:
                process_kg = buckets * 120
                days_chunk = list(range(last_process_day + 1, i + 2))
                needed_gen = process_kg - current_stock
                
                if needed_gen < 0:
                    needed_gen = 0
                    current_stock -= process_kg
                else:
                    current_stock = 0
                    
                if needed_gen > 0:
                    weights = []
                    for d in days_chunk:
                        date_obj = datetime.date(year, month, d)
                        w = 2.0 if date_obj.weekday() == 4 else 1.0
                        weights.append(w * random.uniform(0.85, 1.15))
                    
                    total_weight = sum(weights)
                    allocated = [math.floor(needed_gen * (w / total_weight)) for w in weights]
                    allocated[-1] += needed_gen - sum(allocated) # 자투리 보정
                    
                    for idx, d in enumerate(days_chunk):
                        daily_generated[d - 1] += allocated[idx]
                
                last_process_day = i + 1

        # 결과 생성
        cum_generated = 0
        cum_processed = 0
        final_data = []
        
        for i in range(num_days):
            gen = daily_generated[i]
            cum_generated += gen
            
            buckets = int(bucket_counts[i])
            proc = buckets * 120
            cum_processed += proc
            
            final_data.append([
                f"{year}-{month:02d}-{i+1:02d}", # 0: 발생일자
                "비가식 야채",                    # 1: 성상
                gen,                             # 2: 일일발생량
                cum_generated + prev_unhandled,  # 3: 누계발생량
                "사료용(재사용)" if buckets > 0 else "", # 4: 처리방법
                "두안균" if buckets > 0 else "",         # 5: 운반자
                "토림" if buckets > 0 else "",           # 6: 처리자
                buckets if buckets > 0 else "",          # 7: 통수량
                proc if proc > 0 else "",                # 8: 일일처리량
                cum_processed if cum_processed > 0 else "" # 9: 누계처리량
            ])

        result_df = pd.DataFrame(final_data, columns=[
            "발생일자", "성상", "일일 발생량(Kg)", "누계 발생량(Kg)", "처리방법", "운반자", "처리자", "통수량", "일일 처리량(Kg)", "누계 처리량(Kg)"
        ])
        
        # 구글 시트에 업데이트
        if client:
            try:
                doc = client.open_by_url(SHEET_URL)
                try:
                    worksheet = doc.worksheet(sheet_name)
                    worksheet.clear() # 기존 데이터 덮어쓰기 위해 초기화
                except gspread.exceptions.WorksheetNotFound:
                    worksheet = doc.add_worksheet(title=sheet_name, rows="100", cols="20")
                
                # 데이터프레임을 리스트로 변환하여 시트에 업데이트
                worksheet.update([result_df.columns.values.tolist()] + result_df.values.tolist())
                st.success(f"✅ 구글 시트 '{sheet_name}' 탭에 {month}월 데이터 전체가 성공적으로 저장(업데이트)되었습니다!")
            except Exception as e:
                st.error(f"저장 실패: {e}")
        else:
            st.warning("구글 시트에 연결되지 않아 저장되지 않았습니다. 화면에는 계산 결과만 표시됩니다.")


# --- 탭 2: 리스트 조회 ---
with tab2:
    st.header("2. 폐기물 처리 리스트 확인")
    st.write("구글 시트에 저장된 상세 데이터를 조회합니다.")
    
    col_v1, col_v2 = st.columns(2)
    view_year = col_v1.number_input("조회 년도", value=2026, step=1, key="v_year")
    view_month = col_v2.number_input("조회 월", value=10, min_value=1, max_value=12, step=1, key="v_month")
    
    if st.button("📊 시트에서 리스트 불러오기"):
        if client:
            try:
                doc = client.open_by_url(SHEET_URL)
                v_sheet_name = f"DB_{view_year}_{view_month:02d}"
                worksheet = doc.worksheet(v_sheet_name)
                df_view = pd.DataFrame(worksheet.get_all_records())
                st.dataframe(df_view, use_container_width=True)
            except gspread.exceptions.WorksheetNotFound:
                st.warning(f"{view_year}년 {view_month}월의 데이터가 구글 시트에 존재하지 않습니다.")
            except Exception as e:
                st.error(f"불러오기 실패: {e}")
        else:
            st.error("API 연동 설정을 확인해주세요.")


# --- 탭 3: 양식 출력 및 월마감 ---
with tab3:
    st.header("3. 대장 양식 출력 및 월마감 정산")
    unit_price = st.number_input("1통 처리 단가(원)", min_value=0, value=50000, step=1000)
    
    if st.button("🖨️ 현재 달 양식 출력 생성하기"):
        if client:
            try:
                doc = client.open_by_url(SHEET_URL)
                worksheet = doc.worksheet(f"DB_{year}_{month:02d}")
                df_print = pd.DataFrame(worksheet.get_all_records())
                
                # 빈 문자열을 숫자로 변환할 때 에러 방지
                total_buckets = pd.to_numeric(df_print['통수량'].replace('', 0)).sum()
                total_price = total_buckets * unit_price
                
                st.subheader(f"📄 {year}년 {month}월 폐기물 관리 대장")
                st.dataframe(df_print, use_container_width=True, hide_index=True)
                
                st.markdown("---")
                st.subheader("💰 월 마감 정산 내역")
                st.write(f"- **이번 달 총 처리 통수:** {int(total_buckets)}통")
                st.write(f"- **이번 달 총 청구 금액:** {int(total_price):,}원")
                
                st.session_state.pending_month = month
                st.session_state.pending_buckets = int(total_buckets)
                st.session_state.pending_price = int(total_price)
                
            except Exception as e:
                st.error("먼저 [입력 탭]에서 데이터를 저장한 후 출력해주세요.")
                
    if 'pending_buckets' in st.session_state:
        if st.button("💾 이 내역을 구글시트 [월마감] 탭에 최종 기록하기"):
            try:
                doc = client.open_by_url(SHEET_URL)
                try:
                    ws_closing = doc.worksheet("월마감")
                except gspread.exceptions.WorksheetNotFound:
                    ws_closing = doc.add_worksheet(title="월마감", rows="100", cols="20")
                    ws_closing.append_row(["년도", "월", "총 처리 통수", "단가(원)", "총 청구 금액(원)", "저장 일시"])
                
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ws_closing.append_row([
                    year, 
                    f"{st.session_state.pending_month}월", 
                    st.session_state.pending_buckets, 
                    unit_price, 
                    st.session_state.pending_price, 
                    now_str
                ])
                st.success("✅ 구글 시트 '월마감' 탭에 금액 정산이 등록되었습니다!")
                
            except Exception as e:
                st.error(f"월마감 저장 중 오류 발생: {e}")
