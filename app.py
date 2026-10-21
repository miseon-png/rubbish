import streamlit as st
import pandas as pd
import numpy as np
import datetime
import random
import math
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="폐기물 관리 대장", layout="wide")

st.title("폐기물 관리 대장")

# 초기 설정
year = 2026
month = 10
num_days = 31
# 구글 시트 주소
SHEET_URL = "https://docs.google.com/spreadsheets/d/1iQmVbmKtyhNv80k7jqdalyaCX9At01Lju6bJM6aVkBk/edit"

st.sidebar.header("설정")
prev_unhandled = st.sidebar.number_input("전월 미처리량(Kg)", min_value=0, value=100, step=10)
# 단가 입력란 추가
unit_price = st.sidebar.number_input("1통 처리 단가(원)", min_value=0, value=50000, step=1000)

if 'bucket_inputs' not in st.session_state:
    st.session_state.bucket_inputs = [0] * num_days

# 통수량 입력을 위한 데이터 프레임 생성
df_input = pd.DataFrame({
    "일자": [f"{month}월 {i:02d}일" for i in range(1, num_days + 1)],
    "통수량": st.session_state.bucket_inputs
})

st.subheader("위탁처리 통수량 입력")
st.write("각 일자별로 처리한 통수(1통=120kg)를 입력하세요.")
edited_df = st.data_editor(df_input, num_rows="fixed", use_container_width=True)

if st.button("계산하기", type="primary"):
    bucket_counts = edited_df["통수량"].tolist()
    current_stock = prev_unhandled
    last_process_day = 0
    daily_generated = [0] * num_days
    
    # [기존과 동일한 역산 분배 로직]
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
                    w = 2.0 if date_obj.weekday() == 4 else 1.0 # 금요일 2배
                    random_factor = random.uniform(0.85, 1.15)
                    weights.append(w * random_factor)
                
                total_weight = sum(weights)
                allocated = [math.floor(needed_gen * (w / total_weight)) for w in weights]
                
                remainder = needed_gen - sum(allocated)
                allocated[-1] += remainder
                
                for idx, d in enumerate(days_chunk):
                    daily_generated[d - 1] += allocated[idx]
            
            last_process_day = i + 1

    # 결과 테이블 생성
    cum_generated = 0
    cum_processed = 0
    final_data = []
    
    total_buckets_month = 0
    
    for i in range(num_days):
        gen = daily_generated[i]
        cum_generated += gen
        
        buckets = int(bucket_counts[i])
        proc = buckets * 120
        cum_processed += proc
        total_buckets_month += buckets
        
        final_data.append({
            "발생일자": f"{month}월 {i+1:02d}일",
            "성상": "비가식 야채",
            "일일 발생량(Kg)": gen,
            "누계 발생량(Kg)": cum_generated + prev_unhandled,
            "처리방법": "사료용(재사용)" if buckets > 0 else "",
            "운반자": "두안균" if buckets > 0 else "",
            "처리자": "토림" if buckets > 0 else "",
            "통수량": buckets if buckets > 0 else "",
            "일일 처리량(Kg)": proc if proc > 0 else "",
            "누계 처리량(Kg)": cum_processed if cum_processed > 0 else ""
        })

    result_df = pd.DataFrame(final_data)
    st.session_state.result_df = result_df
    st.session_state.total_buckets_month = total_buckets_month
    st.session_state.total_price = total_buckets_month * unit_price
    
    st.subheader("계산 결과")
    st.dataframe(result_df, use_container_width=True, hide_index=True)

# 구글 시트 저장 버튼 및 로직
if 'result_df' in st.session_state:
    st.markdown("---")
    st.subheader("월 마감 및 구글 시트 저장")
    st.write(f"**{month}월 총 처리 통수:** {st.session_state.total_buckets_month}통")
    st.write(f"**{month}월 총 청구 금액:** {st.session_state.total_price:,}원")
    
    if st.button("구글 시트에 저장하기 (월마감 탭)"):
        try:
            # Streamlit Secrets에서 구글 서비스 계정 인증 정보 가져오기
            secret_dict = st.secrets["gcp_service_account"]
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            creds = Credentials.from_service_account_info(secret_dict, scopes=scopes)
            client = gspread.authorize(creds)
            
            # 시트 열기
            doc = client.open_by_url(SHEET_URL)
            
            # '월마감' 탭이 없으면 생성, 있으면 열기
            try:
                worksheet = doc.worksheet("월마감")
            except gspread.exceptions.WorksheetNotFound:
                worksheet = doc.add_worksheet(title="월마감", rows="100", cols="20")
                # 헤더 추가
                worksheet.append_row(["년도", "월", "총 처리 통수", "단가", "총 청구 금액", "저장 일시"])
            
            # 데이터 추가 (Append)
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            worksheet.append_row([
                year, 
                f"{month}월", 
                st.session_state.total_buckets_month, 
                unit_price, 
                st.session_state.total_price, 
                now_str
            ])
            
            st.success("구글 시트 '월마감' 탭에 데이터가 성공적으로 저장되었습니다!")
            
        except Exception as e:
            st.error(f"구글 시트 저장 중 오류가 발생했습니다. 인증 정보(Secrets) 설정을 확인해주세요.\n에러 내용: {e}")
