import streamlit as st
import pandas as pd
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
        credentials = service_account.Credentials.from_service_account_info(
            uploaded_file.read(),
            scopes=['https://www.googleapis.com/auth/webmasters.readonly']
        )
        
        service = build('searchconsole', 'v1', credentials=credentials)
        site_list = service.sites().list().execute()
        
        verified_sites = [s['siteUrl'] for s in site_list['siteEntry'] if s['permissionLevel'] != 'siteUnverifiedUser']

        if not verified_sites:
            st.error("No verified properties found for this account.")
        else:
            selected_site = st.selectbox("Select a verified property", verified_sites)

            if st.button("🔍 Fetch Data"):
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
                    st.dataframe(df)

                    csv = df.to_csv(index=False).encode('utf-8')
                    st.download_button("📥 Download CSV", csv, "gsc_6_months_data.csv", "text/csv")
                else:
                    st.warning("No data found for this time period.")

    except Exception as e:
        st.error(f"Authentication failed: {e}")
else:
    st.info("Please upload your Google Service Account JSON file to begin.")

