import streamlit as st
import pandas as pd
import json
from datetime import date, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

st.set_page_config(page_title="GSC Analyzer", layout="wide")
st.title("📊 Google Search Console Analyzer")

uploaded_file = st.file_uploader("Upload your GSC service account JSON", type="json")

if uploaded_file:
    try:
        creds_json = json.load(uploaded_file)
        creds = service_account.Credentials.from_service_account_info(
            creds_json,
            scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
        )
        service = build("searchconsole", "v1", credentials=creds)

        sites = service.sites().list().execute()
        verified_sites = [s["siteUrl"] for s in sites["siteEntry"] if s["permissionLevel"] != "siteUnverifiedUser"]
        selected_site = st.selectbox("Choose a verified property", verified_sites)

        # 🔘 Grouping choice
        group_option = st.radio("Group results by:", ["Query", "Page", "Query + Page"])

        # 📆 Date selectors
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Select START date (for comparison)", date.today() - timedelta(days=180))
        with col2:
            end_date = st.date_input("Select END date (for comparison)", date.today())

        if start_date >= end_date:
            st.warning("Start date must be before end date.")
        elif st.button("Fetch Data"):
            compare_start = start_date - (end_date - start_date)
            compare_end = start_date - timedelta(days=1)

            def fetch_data(start, end):
                request = {
                    "startDate": start.isoformat(),
                    "endDate": end.isoformat(),
                    "dimensions": ["query", "page"],
                    "rowLimit": 10000
                }
                response = service.searchanalytics().query(siteUrl=selected_site, body=request).execute()
                rows = response.get("rows", [])
                return pd.DataFrame([{
                    "Query": r["keys"][0],
                    "Page": r["keys"][1],
                    "Clicks": r["clicks"],
                    "Impressions": r["impressions"],
                    "CTR": round(r["ctr"] * 100, 2),
                    "Position": round(r["position"], 2)
                } for r in rows])

            df_current = fetch_data(start_date, end_date)
            df_previous = fetch_data(compare_start, compare_end)

            # Select grouping keys
            if group_option == "Query":
                key_cols = ["Query"]
            elif group_option == "Page":
                key_cols = ["Page"]
            else:
                key_cols = ["Query", "Page"]

            df_group_current = df_current.groupby(key_cols).agg({
                "Clicks": "sum",
                "Impressions": "sum",
                "CTR": "mean",
                "Position": "mean"
            }).reset_index()

            df_group_previous = df_previous.groupby(key_cols).agg({
                "Clicks": "sum",
                "Impressions": "sum",
                "CTR": "mean",
                "Position": "mean"
            }).reset_index()

            df_merged = pd.merge(
                df_group_current,
                df_group_previous,
                on=key_cols,
                how="outer",
                suffixes=("_Current", "_Previous")
            ).fillna(0)

            # Add delta metrics
            df_merged["Click_Change"] = df_merged["Clicks_Current"] - df_merged["Clicks_Previous"]
            df_merged["CTR_Change"] = df_merged["CTR_Current"] - df_merged["CTR_Previous"]
            df_merged["Position_Change"] = df_merged["Position_Current"] - df_merged["Position_Previous"]

            st.subheader("⬆️ Top Growing by Clicks")
            st.dataframe(df_merged.sort_values("Click_Change", ascending=False).head(10))

            st.subheader("⬇️ Top Declining by Clicks")
            st.dataframe(df_merged.sort_values("Click_Change", ascending=True).head(10))

            # ==============================
            # 📈 Trend Chart by Top Entities
            # ==============================
            st.subheader("📈 Trends Over Time (Top Performers)")

            top_entities = df_group_current.sort_values("Clicks", ascending=False).head(5)

            # Fetch trend over time (by date + grouping)
            trend_request = {
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "dimensions": ["date", "query", "page"],
                "rowLimit": 25000
            }
            response = service.searchanalytics().query(siteUrl=selected_site, body=trend_request).execute()
            trend_rows = response.get("rows", [])

            trend_data = []
            for row in trend_rows:
                keys = row.get("keys", [])
                date_val = keys[0]
                query_val = keys[1]
                page_val = keys[2]
                match_key = {
                    "Query": query_val,
                    "Page": page_val,
                    "Query + Page": (query_val, page_val)
                }[group_option]
                if match_key in top_entities.set_index(key_cols).index:
                    trend_data.append({
                        "Date": date_val,
                        "Key": " | ".join([query_val]) if group_option == "Query" else (
                            page_val if group_option == "Page" else f"{query_val} | {page_val}"
                        ),
                        "Clicks": row["clicks"]
                    })

            trend_df = pd.DataFrame(trend_data)
            if not trend_df.empty:
                trend_df["Date"] = pd.to_datetime(trend_df["Date"])
                chart_df = trend_df.pivot(index="Date", columns="Key", values="Clicks").fillna(0)
                st.line_chart(chart_df)
            else:
                st.info("No trend data available for top results in selected date range.")

            # ==============================
            # 💾 Download merged dataset
            # ==============================
            st.subheader("📥 Download Comparison Dataset")
            st.download_button(
                "Download CSV",
                df_merged.to_csv(index=False),
                file_name="gsc_comparison.csv",
                mime="text/csv"
            )

    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.info("Upload your GSC service account JSON to begin.")
