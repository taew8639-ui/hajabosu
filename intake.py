"""접수 화면. 하자를 발견한 사람이 내용을 적으면 DB의 접수 테이블에 미처리로 저장된다.

실행:  streamlit run intake.py --server.port 8502
저장만 한다. 해석·판정은 run.py가 한다. 이때 발견일이 접수일이 된다.
"""
from datetime import date

import pandas as pd
import streamlit as st

import db

st.set_page_config(page_title="하자 접수", layout="centered")
st.title("하자 접수")
st.caption("적은 내용은 접수 테이블에 미처리로 저장됩니다. 발견일이 접수일로 쓰입니다.")

with st.form("접수", clear_on_submit=True):
    발견일 = st.date_input("발견일 (= 접수일)", value=date.today())
    접수자 = st.text_input("접수자")
    부서 = st.text_input("부서")
    위치 = st.text_input("위치", placeholder="예: 2층 화장실")
    내용 = st.text_area("내용", placeholder="무엇이 어떻게 문제인지 적어 주세요.", height=140)
    보냄 = st.form_submit_button("접수하기")

if 보냄:
    if not 위치.strip() or not 내용.strip():
        st.error("위치와 내용은 꼭 적어야 합니다.")
    else:
        try:
            번호 = db.접수_추가(발견일, 접수자.strip(), 부서.strip(), 위치.strip(), 내용.strip())
            st.success(f"접수되었습니다. (접수 id {번호}, 처리 대기)")
        except Exception as e:
            st.error(f"저장하지 못했습니다: {type(e).__name__}")

st.subheader("접수 내역")
try:
    내역 = db.접수_읽기()
except Exception as e:
    st.error(f"접수 내역을 읽지 못했습니다: {type(e).__name__}")
    st.stop()
if 내역:
    표 = pd.DataFrame(내역, columns=db.접수_열).fillna("")
    st.dataframe(표.sort_values("id", ascending=False), width="stretch", hide_index=True)
    st.caption(f"전체 {len(표)}건, 미처리 {int((표['처리상태'] == '미처리').sum())}건")
else:
    st.write("아직 접수가 없습니다.")
