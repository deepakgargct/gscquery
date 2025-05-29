import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
import pandas as pd
import plotly.express as px
from datetime import date, timedelta
import json

st.set_page_config(layout="wide")
st.title("📊 Google Search Console: 6-Month Comparison & Trends")

# Session state setup
if "data_fetched" not in st.session_state:
    st.session_state["data_fetched"] = False

# Auth + Setup
uploaded_file = st.file_uploader("Upload your Google Service Account JSON", type="json")
property_uri = st.text_input("Enter your GSC Property URL (e.g., https://example.com)", "")

# Custom date input
today = date.today()
default_end = today - timedelta(days=3)
default_start = default_end - timedelta(days=180)
default_prev_start = default_start - timedelta(days=180)
default_prev_end = default_start - timedelta(days=1)

start_date = st.date_input("Start Date", default_start)
end_date = st.date_input("End Date", default_end)

group_by = st.selectbox("Group Data By", ["query", "page"])

if uploaded_file and property_uri and st.button("Fetch Data"):
    st.session_state["data_fetched"] = True

if st.session_state["data_fetched"]:
    # Load credentials JSON as dict (fix for bytes error)
    service_account_info = json.load(uploaded_file)
    credentials = service_account.Credentials.from_service_account_info(
        service_account_info, scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
    )
    service = build("searchconsole", "v1", credentials=credentials)

    def fetch_data(start, end):
        request = {
            "startDate": str(start),
            "endDate": str(end),
            "dimensions": [group_by],
            "rowLimit": 500,
        }
        response = service.searchanalytics().query(siteUrl=property_uri, body=request).execute()
        rows = response.get("rows", [])
        data = [{group_by: r["keys"][0], "Clicks": r["clicks"], "Impressions": r["impressions"],
                 "CTR": r["ctr"] * 100, "Position": r["position"]} for r in rows]
        return pd.DataFrame(data)

    df_current = fetch_data(start_date, end_date)

    # Previous period calculation
    default_prev_start = start_date - timedelta(days=(end_date - start_date).days + 1)
    default_prev_end = start_date - timedelta(days=1)
    df_previous = fetch_data(default_prev_start, default_prev_end)

    df_current.rename(columns={
        "Clicks": "Clicks_Current",
        "Impressions": "Impressions_Current",
        "CTR": "CTR_Current",
        "Position": "Position_Current"
    }, inplace=True)
    df_previous.rename(columns={
        "Clicks": "Clicks_Previous",
        "Impressions": "Impressions_Previous",
        "CTR": "CTR_Previous",
        "Position": "Position_Previous"
    }, inplace=True)

    merged = pd.merge(df_current, df_previous, on=group_by, how="outer").fillna(0)
    merged["Clicks_Diff"] = merged["Clicks_Current"] - merged["Clicks_Previous"]
    merged["CTR_Diff"] = merged["CTR_Current"] - merged["CTR_Previous"]
    merged["Impr_Diff"] = merged["Impressions_Current"] - merged["Impressions_Previous"]
    merged["Position_Diff"] = merged["Position_Previous"] - merged["Position_Current"]

    st.subheader("📈 6-Month Comparison")
    st.dataframe(merged.sort_values(by="Clicks_Current", ascending=False), use_container_width=True)

    # Top Gainers & Decliners
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🔼 Top Gainers")
        gainers = merged.sort_values(by="Clicks_Diff", ascending=False).head(20)
        st.dataframe(gainers[[group_by, "Clicks_Current", "Clicks_Previous", "Clicks_Diff"]])

    with col2:
        st.subheader("🔽 Top Decliners")
        decliners = merged.sort_values(by="Clicks_Diff").head(20)
        st.dataframe(decliners[[group_by, "Clicks_Current", "Clicks_Previous", "Clicks_Diff"]])

    # CTR Drop + Impressions Rise
    merged["CTR_Drop"] = merged["CTR_Current"] < merged["CTR_Previous"]
    merged["Clicks_Drop"] = merged["Clicks_Current"] < merged["Clicks_Previous"]
    merged["Impr_Rise"] = merged["Impressions_Current"] > merged["Impressions_Previous"]
    declining_focus = merged[merged["CTR_Drop"] & merged["Clicks_Drop"] & merged["Impr_Rise"]]
    st.subheader("📉 CTR & Click Drop + Impressions Rise (Top 20)")
    st.dataframe(declining_focus.sort_values(by="Clicks_Diff").head(20), use_container_width=True)

    # Trends over time
    def fetch_over_time(dim):
        request = {
            "startDate": str(start_date),
            "endDate": str(end_date),
            "dimensions": ["date", dim],
            "rowLimit": 500
        }
        response = service.searchanalytics().query(siteUrl=property_uri, body=request).execute()
        rows = response.get("rows", [])
        data = []
        for r in rows:
            d = {
                "date": r["keys"][0],
                dim: r["keys"][1],
                "Clicks": r["clicks"],
                "Impressions": r["impressions"],
                "CTR": r["ctr"] * 100,
                "Position": r["position"]
            }
            data.append(d)
        return pd.DataFrame(data)

    st.subheader("📈 Trends Over Time (Top Performers)")
    df_trend = fetch_over_time(group_by)
    if not df_trend.empty:
        top_entities = df_trend.groupby(group_by)["Clicks"].sum().sort_values(ascending=False).head(5).index
        fig = px.line(df_trend[df_trend[group_by].isin(top_entities)],
                      x="date", y="Clicks", color=group_by,
                      title="Clicks Over Time")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No trend data available.")
