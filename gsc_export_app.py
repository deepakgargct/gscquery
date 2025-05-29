import streamlit as st
import pandas as pd
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import date, timedelta

st.title("🔍 GSC Exporter: Last 6 Months")

uploaded_file = st.file_uploader("Upload your service account JSON", type="json")

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

        if not verified_sites:
            st.error("No verified sites found.")
        else:
            selected_site = st.selectbox("Choose a verified site", verified_sites)

            if st.button("Fetch GSC Data"):
                end_date = date.today()
                start_date = end_date - timedelta(days=180)

                request = {
                    "startDate": start_date.isoformat(),
                    "endDate": end_date.isoformat(),
                    "dimensions": ["query", "page"],
                    "rowLimit": 10000
                }

                response = service.searchanalytics().query(siteUrl=selected_site, body=request).execute()
                rows = response.get("rows", [])

                data = []
                for row in rows:
                    keys = row.get("keys", ["", ""])
                    data.append({
                        "Query": keys[0],
                        "Page": keys[1],
                        "Clicks": row["clicks"],
                        "Impressions": row["impressions"],
                        "CTR (%)": round(row["clicks"] / row["impressions"] * 100, 2) if row["impressions"] else 0,
                    })

                df = pd.DataFrame(data)
                st.dataframe(df.head(50))
                st.download_button("Download CSV", df.to_csv(index=False), "gsc_data.csv", "text/csv")

    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.info("Please upload a valid service account JSON.")
