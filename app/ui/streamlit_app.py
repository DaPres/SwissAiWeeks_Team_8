"""TriageMate analyst console — the stage demo.

Input:  the FastAPI backend (API_URL). Nothing is computed here; the console only renders.
Output: analyst decisions (approve / edit / reject) posted back with reason, edit distance
        and dwell time, which drive the metrics page and future few-shot examples.
Three views: Queue (priority-sorted with badges), Review (ticket + AI panel + trace),
Metrics, plus a "paste an email" box for live demos.
Failure mode it prevents: a demo that shows an answer without showing WHY, and analyst
decisions that vanish instead of becoming feedback.

Run: uv run streamlit run app/ui/streamlit_app.py
"""

import os
import time

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
API_URL = os.getenv("API_URL", "http://localhost:8000")
TIMEOUT = 300

PRIORITY_COLOUR = {"highest": "#b3261e", "high": "#e8590c", "medium": "#b08900",
                   "low": "#2f6f4f", "lowest": "#5b6770"}
BADGE_LABEL = {"injection": "🛑 injection", "unclear": "❓ unclear", "title_mismatch": "🔀 title≠body",
               "duplicate": "🔁 duplicate", "spam": "🚫 spam", "low_confidence": "⚠️ low confidence"}

st.set_page_config(page_title="TriageMate", page_icon="🛟", layout="wide")


def api_get(path: str, **params):
    try:
        r = httpx.get(f"{API_URL}{path}", params=params, timeout=TIMEOUT)
        return r.json() if r.status_code == 200 else None
    except httpx.HTTPError:
        return None


def api_post(path: str, payload: dict):
    try:
        r = httpx.post(f"{API_URL}{path}", json=payload, timeout=TIMEOUT)
        return (r.json(), None) if r.status_code == 200 else (None, f"{r.status_code}: {r.text[:300]}")
    except httpx.HTTPError as e:
        return None, f"cannot reach API at {API_URL}: {e}"


def badge_row(badges: list[str]) -> str:
    if not badges:
        return "✅ clean"
    out = []
    for b in badges:
        if b.startswith("duplicate_of:"):
            out.append(f"🔁 duplicate of {b.split(':', 1)[1]}")
        else:
            out.append(BADGE_LABEL.get(b, b))
    return " · ".join(out)


def priority_chip(p: str) -> str:
    return (f"<span style='background:{PRIORITY_COLOUR.get(p, '#666')};color:#fff;padding:2px 8px;"
            f"border-radius:10px;font-size:0.8em;font-weight:600'>{p.upper()}</span>")


# --- header ---------------------------------------------------------------------------

health = api_get("/health")
c1, c2 = st.columns([3, 1])
with c1:
    st.title("🛟 TriageMate")
    st.caption("Triage co-pilot for operational service desks · Swiss {ai} Weeks · Swiss Life challenge")
with c2:
    if health:
        st.success(f"API up · {health['tickets']:,} tickets")
    else:
        st.error(f"API unreachable\n{API_URL}")
        st.stop()

view = st.sidebar.radio("View", ["Queue", "Review", "Paste a ticket", "Metrics"])
st.sidebar.divider()
st.sidebar.caption("Priority comes from the organisers' 5×5 matrix computed **in code**. "
                   "Team comes from a catalogue lookup. The model never decides either.")

# --- queue ----------------------------------------------------------------------------

if view == "Queue":
    st.subheader("Triage queue — highest priority first")
    items = api_get("/queue", limit=100) or []
    if not items:
        st.info("Nothing triaged yet. Run `uv run python scripts/dry_run.py 20` or use **Paste a ticket**.")
    for it in items:
        col = st.columns([1.1, 2.4, 2.2, 1.5, 1.2, 1.1])
        col[0].markdown(priority_chip(it["priority"]), unsafe_allow_html=True)
        col[1].markdown(f"**{it['ticket_id']}** · {it['service']}")
        col[2].markdown(badge_row(it["badges"]))
        col[3].markdown(f"`{it['resolution']}`")
        col[4].markdown(f"conf **{it['confidence']:.2f}**")
        if col[5].button("Review", key=f"go-{it['ticket_id']}"):
            st.session_state["ticket_id"] = it["ticket_id"]
            st.session_state["opened_at"] = time.time()
            st.rerun()
        if it["decision"]:
            col[1].caption(f"↳ analyst: {it['decision']}")

# --- review ---------------------------------------------------------------------------

elif view == "Review":
    ids = [i["ticket_id"] for i in (api_get("/queue", limit=100) or [])]
    if not ids:
        st.info("Nothing triaged yet.")
        st.stop()
    current = st.session_state.get("ticket_id", ids[0])
    ticket_id = st.selectbox("Ticket", ids, index=ids.index(current) if current in ids else 0)
    if ticket_id != st.session_state.get("ticket_id"):
        st.session_state["ticket_id"] = ticket_id
        st.session_state["opened_at"] = time.time()

    payload = api_get(f"/ticket/{ticket_id}") or {}
    ticket, result = payload.get("ticket"), payload.get("result")
    if not result:
        st.warning("No triage result stored for this ticket.")
        st.stop()
    g = result["graded"]

    left, right = st.columns([1, 1])

    with left:
        st.subheader("Ticket")
        if ticket:
            show_raw = st.toggle("Show unredacted original", value=False,
                                 help="The model only ever received the redacted text.")
            st.markdown(f"**{ticket['summary']}**")
            st.text_area("Body", ticket["description"] if show_raw else ticket["redacted_text"],
                         height=170, disabled=True, label_visibility="collapsed")
            red = ticket.get("redactions") or {}
            st.caption(f"submitted service: `{ticket.get('claimed_service')}` · entity: "
                       f"`{ticket.get('entity')}` · created: {ticket.get('created')} · "
                       f"redacted: {red or 'nothing'}")
            if ticket.get("comments"):
                with st.expander(f"{len(ticket['comments'])} existing comment(s)"):
                    for c in ticket["comments"]:
                        st.write(f"- {c}")

    with right:
        st.subheader("AI triage")
        flags = result.get("flags") or {}
        active = [k for k, v in flags.items() if v is True]
        active += [f"duplicate_of:{t}" for t in (flags.get("related_open") or [])[:1]]
        st.markdown(f"{priority_chip(g['priority'])} &nbsp; {badge_row(active)}", unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        m1.metric("Work type", g["work_type"])
        m2.metric("Team", g["team"])
        m3.metric("Confidence", f"{result['confidence']:.2f}",
                  delta="below floor" if result["confidence"] < 0.6 else "ok",
                  delta_color="inverse" if result["confidence"] < 0.6 else "normal")
        st.markdown(f"**Service** `{g['service']}` → **Assignee** `{g['assignee']}` "
                    f"(suggestion — assignment is random in the data)")
        st.markdown(f"**Priority reason:** {result['priority_reason']}")
        u, i = result["urgency"], result["impact"]
        st.caption(f"urgency **{u['value']}** — “{u['quote'][:140]}”")
        st.caption(f"impact **{i['value']}** — “{i['quote'][:140]}”")
        for ov in result.get("overrides", []):
            st.warning(f"override applied ({'ours' if ov['ours'] else 'organiser rule'}): {ov['effect']}")

    st.divider()
    d1, d2 = st.columns([1, 1])
    with d1:
        st.markdown(f"**Resolution:** `{g['resolution']}`")
        st.markdown("**Resolution comment**")
        edited = st.text_area("comment", g["resolution_comment"], height=130, label_visibility="collapsed")
        if result.get("draft_reply"):
            st.markdown("**Draft reply to requester**")
            st.info(result["draft_reply"])
        if result.get("next_steps"):
            st.markdown("**Next steps**")
            for s in result["next_steps"]:
                st.write(f"- {s}")
    with d2:
        st.markdown("**Citations**")
        if result["citations"]:
            for c in result["citations"][:6]:
                st.write(f"`{c['id']}` · score {c.get('score')} — {c['snippet'][:110]}…")
        else:
            st.caption("no supporting evidence retrieved — no fix is claimed")
        with st.expander(f"Trace — {len(result['trace'])} steps, "
                         f"{sum(s['latency_ms'] for s in result['trace']) / 1000:.1f}s"):
            for s in result["trace"]:
                tool = f" `{s['tool']}`" if s.get("tool") else ""
                st.write(f"**{s['step']}**{tool} · {s['latency_ms']:.0f} ms — {s['detail']}")

    st.divider()
    st.markdown("**Analyst decision**")
    reason = st.text_input("Reason (required for edit or reject)", "")
    b1, b2, b3 = st.columns(3)
    dwell = time.time() - st.session_state.get("opened_at", time.time())

    def send(decision: str, text: str = ""):
        out, err = api_post("/decision", {"ticket_id": ticket_id, "decision": decision,
                                          "reason": reason, "dwell_seconds": round(dwell, 1),
                                          "edited_text": text})
        if err:
            st.error(err)
        else:
            st.success(f"{decision} recorded · edit distance {out['edit_distance']} · dwell {dwell:.0f}s")

    if b1.button("✅ Approve", use_container_width=True):
        send("approve")
    if b2.button("✏️ Save edit", use_container_width=True, disabled=not reason):
        send("edit", edited)
    if b3.button("❌ Reject", use_container_width=True, disabled=not reason):
        send("reject")

# --- paste ----------------------------------------------------------------------------

elif view == "Paste a ticket":
    st.subheader("Paste a ticket or email")
    st.caption("Nothing is stored in the corpus; this runs the full pipeline on what you paste.")
    summary = st.text_input("Subject / summary", "NAV calculation failed overnight")
    body = st.text_area("Body", "The overnight pricing run did not complete and clients are waiting "
                                "for their reports. Contact me at anna.meier@intcom.com.", height=170)
    service = st.text_input("Submitted service (may be wrong on purpose)", "Outlook & Email")
    if st.button("Triage it", type="primary"):
        with st.spinner("Running the full pipeline…"):
            result, err = api_post("/triage", {"summary": summary, "description": body,
                                               "claimed_service": service or None})
        if err:
            st.error(err)
        else:
            g = result["graded"]
            st.markdown(priority_chip(g["priority"]), unsafe_allow_html=True)
            c = st.columns(4)
            c[0].metric("Work type", g["work_type"])
            c[1].metric("Service", g["service"])
            c[2].metric("Team", g["team"])
            c[3].metric("Confidence", f"{result['confidence']:.2f}")
            st.markdown(f"**Resolution** `{g['resolution']}` — {g['resolution_comment']}")
            if result.get("draft_reply"):
                st.info(result["draft_reply"])
            st.caption(f"priority: {result['priority_reason']}")
            with st.expander("Trace"):
                for s in result["trace"]:
                    st.write(f"**{s['step']}** · {s['latency_ms']:.0f} ms — {s['detail']}")

# --- metrics --------------------------------------------------------------------------

else:
    st.subheader("Metrics")
    m = api_get("/metrics") or {}
    if not m.get("triaged"):
        st.info("Nothing triaged yet.")
        st.stop()
    c = st.columns(5)
    c[0].metric("Triaged", m["triaged"])
    c[1].metric("Mean confidence", m.get("mean_confidence", 0))
    c[2].metric("Below floor", m.get("below_floor", 0))
    c[3].metric("Citation coverage", f"{m.get('citation_coverage', 0):.0%}")
    c[4].metric("Mean comment", f"{m.get('mean_comment_chars', 0):.0f} ch")

    a, b = st.columns(2)
    with a:
        st.markdown("**By resolution**")
        st.bar_chart(m.get("by_resolution", {}))
        st.markdown("**By priority**")
        st.bar_chart(m.get("by_priority", {}))
    with b:
        st.markdown("**By team**")
        st.bar_chart(m.get("by_team", {}))
        st.markdown("**Flags raised**")
        st.write(m.get("flagged", {}) or "none")

    st.divider()
    st.markdown("**Analyst decisions**")
    if m.get("total_decisions"):
        st.write(f"total {m['total_decisions']} · approval rate "
                 f"{(m.get('approval_rate') or 0):.0%}")
        st.json(m.get("by_decision", {}))
    else:
        st.caption("No analyst decisions recorded yet — approve or edit one in Review.")
