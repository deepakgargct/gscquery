import streamlit as st
import pandas as pd
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import date, timedelta

st.set_page_config(page_title="GSC Comparison + Trends", layout="wide")
st.title("📊 Google Search Console: 6 Month Comparison & Trends (Query + Page)")

uploaded_file = st.file_uploader("🔐 Upload your Google Service Account JSON key", type="json")

end_date = date.today()
start_date = end_date - timedelta(days=180)
prev_start = start_date - timedelta(days=180)
prev_end = start_date - timedelta(days=1)

def fetch_gsc_data(service, site, start, end, dimensions):
    request = {
        'startDate': start.isoformat(),
        'endDate': end.isoformat(),
        'dimensions': dimensions,
        'rowLimit': 25000
    }
    response = service.searchanalytics().query(siteUrl=site, body=request).execute()
    rows = response.get("rows", [])
    data = []
    for row in rows:
        keys = row['keys']
        key_dict = {dim: key for dim, key in zip(dimensions, keys)}
        key_dict.update({
            'Clicks': row['clicks'],
            'Impressions': row['impressions'],
            'CTR (%)': round(row['clicks'] / row['impressions'] * 100, 2) if row['impressions'] else 0
        })
        data.append(key_dict)
    return pd.DataFrame(data)

if uploaded_file:
    try:
        service_account_info = json.load(uploaded_file)
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=['https://www.googleapis.com/auth/webmasters.readonly']
        )
        service = build('searchconsole', 'v1', credentials=credentials)

        site_list = service.sites().list().execute()
        verified_sites = [
            site['siteUrl']
            for site in site_list.get('siteEntry', [])
            if site['permissionLevel'] != 'siteUnverifiedUser'
        ]

        if not verified_sites:
            st.error("No verified GSC properties found.")
        else:
            selected_site = st.selectbox("Select a GSC property", verified_sites)

            if st.button("📥 Fetch & Compare Data"):
                with st.spinner("Fetching current 6-month data..."):
                    current_df = fetch_gsc_data(service, selected_site, start_date, end_date, ['query', 'page'])
                with st.spinner("Fetching previous 6-month data..."):
                    prev_df = fetch_gsc_data(service, selected_site, prev_start, prev_end, ['query', 'page'])

                merged_df = pd.merge(
                    current_df,
                    prev_df,
                    how='outer',
                    on=['query', 'page'],
                    suffixes=('_current', '_previous')
                ).fillna(0)

                merged_df['Clicks_diff'] = merged_df['Clicks_current'] - merged_df['Clicks_previous']
                merged_df['Clicks_%change'] = merged_df.apply(
                    lambda row: ((row['Clicks_diff'] / row['Clicks_previous']) * 100) if row['Clicks_previous'] != 0 else 100,
                    axis=1
                )

                merged_df['Impressions_diff'] = merged_df['Impressions_current'] - merged_df['Impressions_previous']
                merged_df['Impr_%change'] = merged_df.apply(
                    lambda row: ((row['Impressions_diff'] / row['Impressions_previous']) * 100) if row['Impressions_previous'] != 0 else 100,
                    axis=1
                )

                st.success(f"✅ Retrieved {len(merged_df)} rows with comparison.")

                st.sidebar.header("Filter top growing/declining queries")
                top_n = st.sidebar.number_input("Show top N queries", min_value=5, max_value=1000, value=20, step=5)
                filter_mode = st.sidebar.radio("Select filter mode:", ['All', 'Top Growing', 'Top Declining'])

                if filter_mode == 'Top Growing':
                    filtered_df = merged_df.sort_values(by='Clicks_%change', ascending=False).head(top_n)
                elif filter_mode == 'Top Declining':
                    filtered_df = merged_df.sort_values(by='Clicks_%change', ascending=True).head(top_n)
                else:
                    filtered_df = merged_df

                st.dataframe(filtered_df)

                st.header("📈 Aggregated Performance Trends (Current vs Previous 6 Months)")

                agg_current = current_df[['Clicks', 'Impressions', 'CTR (%)']].sum()
                agg_prev = prev_df[['Clicks', 'Impressions', 'CTR (%)']].sum()

                trend_df = pd.DataFrame({
                    'Metric': ['Clicks', 'Impressions', 'CTR (%)'],
                    'Previous 6 Months': [agg_prev['Clicks'], agg_prev['Impressions'], agg_prev['CTR (%)']],
                    'Last 6 Months': [agg_current['Clicks'], agg_current['Impressions'], agg_current['CTR (%)']]
                }).set_index('Metric')

                st.bar_chart(trend_df)

                csv = filtered_df.to_csv(index=False).encode('utf-8')
                st.download_button("⬇️ Download Filtered CSV", csv, "gsc_comparison_filtered.csv", "text/csv")

    except Exception as e:
        st.error(f"❌ Error: {e}")
else:
    st.info("Please upload your Google service account JSON to get started.")
