"""Streamlit demo chat UI. Needs the API running.

Run:  uv run streamlit run app/ui/streamlit_app.py
"""

import os

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Service Desk Assistant", page_icon="🛟")
st.title("🛟 Service Desk Assistant")
st.caption("Swiss {ai} Weeks · Swiss Life challenge")

if "history" not in st.session_state:
    st.session_state.history = []

for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("meta"):
            st.caption(msg["meta"])

if prompt := st.chat_input("Describe your issue…"):
    st.session_state.history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            try:
                r = httpx.post(f"{API_URL}/chat", json={"message": prompt}, timeout=120)
                if r.status_code == 200:
                    data = r.json()
                    answer = data["answer"]
                    sources = ", ".join(s["source"] for s in data["sources"]) or "none"
                    meta = f"served by **{data['provider']}** ({data['model']}) · sources: {sources}"
                else:
                    answer, meta = f"⚠️ API error {r.status_code}: {r.text}", ""
            except httpx.HTTPError as e:
                answer, meta = f"⚠️ Could not reach API at {API_URL}: {e}", ""
        st.markdown(answer)
        if meta:
            st.caption(meta)
    st.session_state.history.append({"role": "assistant", "content": answer, "meta": meta})
