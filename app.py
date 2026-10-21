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
tab1, tab2, tab3, tab4 = st.tabs(["📝 입력", "📋 리스트 조회", "🖨️ 양식 출력", "💰 월 마감"])

# --- 탭 1: 데이터 입력 ---
with tab1:
    st.header("1. 통수 입력")
    
    col1, col2, col3 = st.columns(3)
    year = col1.number_input("년도", value=2026, step=1)
    month = col2.number_input("월", value=10, min_value=1, max_value=12, step=1)
    num_days = calendar.monthrange(year, month)[1]
    
    prev_unhandled = col3.number_input("전월 미처리량(Kg)", min_value=0, value=100, step=10)
    
    st.info("💡 **팁:** 기존에 구글 시트에 저장해둔 이번 달 데이터가 있다면 먼저 불러오세요.")
    
    if 'bucket_inputs' not in st.session_state or st.session_state.get('current_month') != month or st.session_state.get('current_year') != year:
        st.session_state.bucket_inputs = [0] * num_days
        st.session_state.current_month = month
        st.session_state.current_year = year

    sheet_name = f"DB_{year}_{month:02d}"

    if st.button("☁️ 구글시트에서 이번 달 기존 입력값 불러오기"):
        if client:
            try:
                doc = client.open_by_url(SHEET_URL)
                worksheet = doc.worksheet(sheet_name)
                records = worksheet.get_all_records()
                
                loaded_buckets = []
                for idx in range(num_days):
                    if idx < len(records):
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

    st.markdown("---")
    st.subheader("📌 특정 날짜 통수 입력")
    
    input_col1, input_col2, input_col3 = st.columns([2, 2, 1])
    
    with input_col1:
        selected_date = st.date_input(
            "날짜 선택", 
            value=datetime.date(year, month, 1),
            min_value=datetime.date(year, month, 1),
            max_value=datetime.date(year, month, num_days)
        )
    
    with input_col2:
        input_buckets = st.number_input("처리 통수(1통=120kg)", min_value=0, value=0, step=1)
        
    with input_col3:
        st.write("")
        st.write("")
        if st.button("➕ 입력 적용", use_container_width=True):
            day_idx = selected_date.day - 1
            st.session_state.bucket_inputs[day_idx] = input_buckets
            st.success(f"{selected_date.strftime('%Y년 %m월 %d일')}에 {input_buckets}통이 입력되었습니다.")

    st.write("▼ **현재 입력된 통수 내역** (이번 달)")
    entered_data = []
    for d in range(num_days):
        if st.session_state.bucket_inputs[d] > 0:
            entered_data.append({"일자": f"{month}월 {d+1:02d}일", "입력된 통수": st.session_state.bucket_inputs[d]})
            
    if entered_data:
        st.table(pd.DataFrame(entered_data))
    else:
        st.info("현재 입력된 통수가 없습니다. 날짜를 선택하여 통수를 입력해주세요.")

    st.markdown("---")
    if st.button("🚀 계산 및 구글시트에 전체 저장 (업데이트)", type="primary", use_container_width=True):
        bucket_counts = st.session_state.bucket_inputs
        current_stock = prev_unhandled
        last_process_day = 0
        daily_generated = [0] * num_days
        
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
                    allocated[-1] += needed_gen - sum(allocated) 
                    
                    for idx, d in enumerate(days_chunk):
                        daily_generated[d - 1] += allocated[idx]
                
                last_process_day = i + 1

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
                f"{year}-{month:02d}-{i+1:02d}", 
                "비가식 야채",                    
                gen,                             
                cum_generated + prev_unhandled,  
                "사료용(재사용)" if buckets > 0 else "", 
                "두안균" if buckets > 0 else "",         
                "토림" if buckets > 0 else "",           
                buckets if buckets > 0 else "",          
                proc if proc > 0 else "",                
                cum_processed if cum_processed > 0 else "" 
            ])

        result_df = pd.DataFrame(final_data, columns=[
            "발생일자", "성상", "일일 발생량(Kg)", "누계 발생량(Kg)", "처리방법", "운반자", "처리자", "통수량", "일일 처리량(Kg)", "누계 처리량(Kg)"
        ])
        
        if client:
            try:
                doc = client.open_by_url(SHEET_URL)
                try:
                    worksheet = doc.worksheet(sheet_name)
                    worksheet.clear() 
                except gspread.exceptions.WorksheetNotFound:
                    worksheet = doc.add_worksheet(title=sheet_name, rows="100", cols="20")
                
                worksheet.update([result_df.columns.values.tolist()] + result_df.values.tolist())
                st.success(f"✅ 구글 시트 '{sheet_name}' 탭에 {month}월 데이터 전체가 성공적으로 저장(업데이트)되었습니다!")
            except Exception as e:
                st.error(f"저장 실패: {e}")
        else:
            st.warning("구글 시트에 연결되지 않아 저장되지 않았습니다.")


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


# --- 탭 3: 대장 양식 출력 (PDF) ---
with tab3:
    st.header("3. 대장 양식 출력 및 PDF 저장")
    st.write("요청하신 공식 문서 양식 템플릿입니다. 아래 버튼을 눌러 양식을 생성하고 PDF로 인쇄/저장할 수 있습니다.")
    
    if st.button("🖨️ 대장 양식 생성하기", type="primary"):
        if client:
            try:
                doc = client.open_by_url(SHEET_URL)
                worksheet = doc.worksheet(f"DB_{year}_{month:02d}")
                df_print = pd.DataFrame(worksheet.get_all_records())
                
                # 합계 및 미처리량 계산
                if len(df_print) > 0:
                    first_row_cum = pd.to_numeric(str(df_print.iloc[0]['누계 발생량(Kg)']).replace('','0'))
                    first_row_daily = pd.to_numeric(str(df_print.iloc[0]['일일 발생량(Kg)']).replace('','0'))
                    dynamic_prev = int(first_row_cum - first_row_daily)
                else:
                    dynamic_prev = 0
                    
                sum_gen = pd.to_numeric(df_print['일일 발생량(Kg)'].replace('', 0)).sum()
                sum_buckets = pd.to_numeric(df_print['통수량'].replace('', 0)).sum()
                sum_proc = pd.to_numeric(df_print['일일 처리량(Kg)'].replace('', 0)).sum()

                # HTML/CSS 양식 템플릿 제작 (이미지와 100% 동일한 구조)
                html_template = f'''
                <!DOCTYPE html>
                <html lang="ko">
                <head>
                <meta charset="UTF-8">
                <title>폐기물 관리 대장</title>
                <style>
                    @page {{ size: A4 landscape; margin: 15mm; }}
                    body {{ font-family: 'Malgun Gothic', dotum, sans-serif; font-size: 11px; color: black; }}
                    .header-container {{ display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 10px; }}
                    .title {{ font-size: 32px; font-weight: bold; letter-spacing: 2px; }}
                    .sign-table {{ border-collapse: collapse; text-align: center; font-size: 12px; }}
                    .sign-table th, .sign-table td {{ border: 1px solid black; width: 60px; }}
                    .sign-table th {{ padding: 2px; font-weight: normal; }}
                    .sign-table td {{ height: 45px; }}
                    .main-table {{ width: 100%; border-collapse: collapse; text-align: center; }}
                    .main-table th, .main-table td {{ border: 1px solid black; padding: 4px; }}
                    .main-table th {{ font-weight: bold; background-color: white; }}
                    .border-thick {{ border: 2px solid black !important; }}
                    .dotted-row td {{ border-top: 1px dotted black; border-bottom: 1px dotted black; }}
                </style>
                </head>
                <body onload="window.print()">
                    <div class="header-container">
                        <div class="title">폐기물 관리 대장</div>
                        <table class="sign-table border-thick">
                            <tr><th>작성</th><th>검토</th><th>승인</th></tr>
                            <tr><td></td><td></td><td></td></tr>
                        </table>
                    </div>
                    <table class="main-table border-thick">
                        <tr>
                            <th colspan="2">발생월</th>
                            <th colspan="3">{year}년 {month}월</th>
                            <th colspan="2">작성주기</th>
                            <th colspan="2">발생 시</th>
                            <th colspan="2">작성자</th>
                            <th colspan="2">이미선</th>
                        </tr>
                        <tr>
                            <th colspan="4">발생내역</th>
                            <th colspan="3">자체처리</th>
                            <th colspan="6">위탁처리</th>
                        </tr>
                        <tr>
                            <th rowspan="2" style="width:10%;">발생일자</th>
                            <th rowspan="2" style="width:8%;">성상</th>
                            <th colspan="2">폐기물발생량(Kg)</th>
                            <th rowspan="2" style="width:9%;">처리방법</th>
                            <th colspan="2">처리량(Kg)</th>
                            <th rowspan="2" style="width:9%;">처리방법</th>
                            <th rowspan="2" style="width:7%;">운반자</th>
                            <th rowspan="2" style="width:7%;">처리자</th>
                            <th colspan="3">처리량(Kg)</th>
                        </tr>
                        <tr>
                            <th style="width:5%;">일일</th>
                            <th style="width:6%;">누계</th>
                            <th style="width:5%;">일일</th>
                            <th style="width:6%;">누계</th>
                            <th style="width:5%;">통수량</th>
                            <th style="width:5%;">일일</th>
                            <th style="width:6%;">누계</th>
                        </tr>
                        <tr class="dotted-row">
                            <td style="font-weight:bold;">전월 미처리량</td>
                            <td></td>
                            <td></td>
                            <td>{dynamic_prev if dynamic_prev > 0 else ''}</td>
                            <td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td>
                        </tr>
                '''
                
                # 데이터 행 추가
                for _, row in df_print.iterrows():
                    date_val = str(row['발생일자'])
                    if '-' in date_val:
                        y, m, d = date_val.split('-')
                        date_str = f"{y}년 {m}월 {d}일"
                    else:
                        date_str = date_val

                    daily_gen = row['일일 발생량(Kg)']
                    daily_gen_str = int(daily_gen) if daily_gen != '' and int(daily_gen) > 0 else ''
                    
                    html_template += f'''<tr class="dotted-row">
                        <td>{date_str}</td>
                        <td>{row['성상']}</td>
                        <td>{daily_gen_str}</td>
                        <td>{row['누계 발생량(Kg)']}</td>
                        <td></td><td></td><td></td>
                        <td>{row['처리방법']}</td>
                        <td>{row['운반자']}</td>
                        <td>{row['처리자']}</td>
                        <td>{row['통수량']}</td>
                        <td>{row['일일 처리량(Kg)']}</td>
                        <td>{row['누계 처리량(Kg)']}</td>
                    </tr>'''

                html_template += f'''
                        <tr>
                            <td colspan="2" style="font-weight:bold;">전체 합계</td>
                            <td>{int(sum_gen) if sum_gen > 0 else '-'}</td>
                            <td>-</td>
                            <td></td>
                            <td>-</td>
                            <td>-</td>
                            <td></td>
                            <td></td>
                            <td></td>
                            <td>{int(sum_buckets) if sum_buckets > 0 else '0'}</td>
                            <td>{int(sum_proc) if sum_proc > 0 else '0'}</td>
                            <td>-</td>
                        </tr>
                    </table>
                </body>
                </html>
                '''
                
                st.session_state.html_content = html_template
                st.session_state.html_filename = f"폐기물관리대장_{year}년_{month}월.html"
                
            except Exception as e:
                st.error("데이터를 불러오는 데 실패했습니다. 먼저 [입력] 탭에서 데이터를 저장해주세요.")
                
    # 다운로드 버튼 영역
    if 'html_content' in st.session_state:
        st.markdown("---")
        st.success("✅ 문서 렌더링 완료! 아래 버튼을 눌러 양식을 다운로드하세요.")
        
        st.download_button(
            label="📥 인쇄용 대장 다운로드 (클릭하여 열면 PDF 저장 창이 열립니다)",
            data=st.session_state.html_content,
            file_name=st.session_state.html_filename,
            mime="text/html",
            use_container_width=True
        )
        
        st.info('''
        💡 **PDF 저장 및 출력 방법 가이드:** 
        1. 위 버튼을 눌러 `.html` 파일을 다운로드합니다.
        2. 다운로드된 파일을 더블클릭하여 인터넷 브라우저(크롬, 엣지 등)로 엽니다.
        3. 문서가 열림과 동시에 **자동으로 인쇄 설정 창**이 나타납니다.
        4. 대상(프린터) 옵션에서 **'PDF로 저장'**을 선택하면 A4 가로 사이즈로 완벽하게 맞춰진 PDF 파일이 저장됩니다.
        ''')


# --- 탭 4: 월 마감 정산 ---
with tab4:
    st.header("4. 업체 월 마감 정산")
    st.write("위탁 처리 업체와의 정산을 위한 월별 금액 합계 및 기록을 진행합니다.")
    
    unit_price = st.number_input("1통 처리 단가(원)", min_value=0, value=50000, step=1000)
    
    if st.button("💰 현재 달 정산 내역 계산하기"):
        if client:
            try:
                doc = client.open_by_url(SHEET_URL)
                worksheet = doc.worksheet(f"DB_{year}_{month:02d}")
                df_print = pd.DataFrame(worksheet.get_all_records())
                
                total_buckets = pd.to_numeric(df_print['통수량'].replace('', 0)).sum()
                total_price = total_buckets * unit_price
                
                st.markdown("---")
                st.subheader(f"✅ {year}년 {month}월 마감 요약")
                st.write(f"- **총 처리 통수:** {int(total_buckets)}통")
                st.write(f"- **총 청구 금액:** {int(total_price):,}원")
                
                st.session_state.pending_month = month
                st.session_state.pending_year = year
                st.session_state.pending_buckets = int(total_buckets)
                st.session_state.pending_price = int(total_price)
                
            except Exception as e:
                st.error("먼저 [입력] 탭에서 데이터를 저장한 후 마감을 진행해주세요.")
                
    if 'pending_buckets' in st.session_state:
        if st.button("💾 이 정산 내역을 구글시트 [월마감] 탭에 최종 기록하기"):
            try:
                doc = client.open_by_url(SHEET_URL)
                try:
                    ws_closing = doc.worksheet("월마감")
                except gspread.exceptions.WorksheetNotFound:
                    ws_closing = doc.add_worksheet(title="월마감", rows="100", cols="20")
                    ws_closing.append_row(["년도", "월", "총 처리 통수", "단가(원)", "총 청구 금액(원)", "저장 일시"])
                
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ws_closing.append_row([
                    st.session_state.pending_year, 
                    f"{st.session_state.pending_month}월", 
                    st.session_state.pending_buckets, 
                    unit_price, 
                    st.session_state.pending_price, 
                    now_str
                ])
                st.success("✅ 구글 시트 '월마감' 탭에 금액 정산 내역이 성공적으로 등록되었습니다!")
                
            except Exception as e:
                st.error(f"월마감 저장 중 오류 발생: {e}")
