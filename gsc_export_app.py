import streamlit as st
import pandas as pd
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import date, timedelta

st.set_page_config(page_title="GSC Query Exporter", layout="centered")
st.title("📊 Google Search Console - 6 Month Query Exporter")

# Upload service account key
uploaded_file = st.file_uploader("🔐 Upload your Service Account JSON key", type="json")

# Define date range (last 6 months)
end_date = date.today()
start_date = end_date - timedelta(days=180)

if uploaded_file:
    try:
        # Parse the uploaded JSON file
        service_account_info = json.load(uploaded_file)

        # Authenticate using the service account
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=['https://www.googleapis.com/auth/webmasters.readonly']
        )

        # Build GSC API client
        service = build('searchconsole', 'v1', credentials=credentials)

        # Get verified site properties
        site_list = service.sites().list().execute()
        verified_sites = [
            site['siteUrl']
            for site in site_list.get('siteEntry', [])
            if site['permissionLevel'] != 'siteUnverifiedUser'
        ]

        if not verified_sites:
            st.error("No verified properties found for this service account.")
        else:
            selected_site = st.selectbox("Select a verified property", verified_sites)

            if st.button("🔍 Fetch GSC Data"):
                st.info(f"Fetching query data from {start_date} to {end_date}...")

                # Prepare API request
                request = {
                    'startDate': start_date.isoformat(),
                    'endDate': end_date.isoformat(),
                    'dimensions': ['query'],
                    'rowLimit': 25000
                }

                response = service.searchanalytics().query(siteUrl=selected_site, body=request).execute()

                if 'rows' in response:
                    data = []
                    for row in response['rows']:
                        query = row['keys'][0]
                        clicks = row['clicks']
                        impressions = row['impressions']
                        ctr = round(clicks / impressions * 100, 2) if impressions else 0
                        data.append([query, clicks, impressions, ctr])

                    df = pd.DataFrame(data, columns=['Query', 'Clicks', 'Impressions', 'CTR (%)'])
                    st.success(f"✅ Retrieved {len(df)} rows.")
                    st.dataframe(df)

                    csv = df.to_csv(index=False).encode('utf-8')
                    st.download_button("📥 Download CSV", csv, "gsc_6_months_data.csv", "text/csv")
                else:
                    st.warning("No data found for this site and time range.")

    except Exception as e:
        st.error(f"❌ Authentication failed: {e}")
else:
    st.info("Upload your Google service account JSON to begin.")
