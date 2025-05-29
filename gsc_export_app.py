import streamlit as st
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import pandas as pd
import plotly.express as px
from datetime import date
from oauthlib.oauth2.rfc6749.errors import InvalidGrantError

st.set_page_config(page_title="GSC Visualizer", layout="wide")
st.title("📊 GSC Visualization: Unique URLs & Clicks Over Time")

if "creds" not in st.session_state:
    st.session_state.creds = None

uploaded_file = st.file_uploader("Upload your client_secrets.json", type="json")

if uploaded_file:
    with open("client_secrets_temp.json", "wb") as f:
        f.write(uploaded_file.getbuffer())

    if st.session_state.creds is None:
        flow = Flow.from_client_secrets_file(
            "client_secrets_temp.json",
            scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
            redirect_uri="urn:ietf:wg:oauth:2.0:oob"
        )

        auth_url, _ = flow.authorization_url(prompt='consent')
        st.markdown(f"[🔗 Click here to authorize]({auth_url})")
        st.info("⚠️ Please get a new authorization code each time and paste it below immediately after authorizing.")

        auth_code = st.text_input("Paste the authorization code here:").strip()

        if auth_code:
            try:
                flow.fetch_token(code=auth_code)
                st.session_state.creds = flow.credentials
                st.success("Authorization successful! You can now fetch data.")
            except InvalidGrantError as e:
                st.error(f"Authorization failed: Invalid grant. The code may be expired or already used. Please retry with a fresh code.")
            except Exception as e:
                st.error(f"An unexpected error occurred during token fetch: {e}")

    if st.session_state.creds:
        service = build("searchconsole", "v1", credentials=st.session_state.creds)
        site_list = service.sites().list().execute()
        verified_sites = [s["siteUrl"] for s in site_list.get("siteEntry", []) if s.get("permissionLevel") == "siteOwner"]

        if not verified_sites:
            st.warning("No verified sites found for this account.")
        else:
            site = st.selectbox("Choose a site", verified_sites)
            start_date = st.date_input("Start date", date(2024, 4, 1))
            end_date = st.date_input("End date", date(2024, 4, 30))

            if st.button("Fetch and Visualize Data"):
                request = {
                    "startDate": str(start_date),
                    "endDate": str(end_date),
                    "dimensions": ["date", "page"],
                    # Removed country filter here
                    "rowLimit": 25000,
                    "dataState": "final"
                }

                response = service.searchanalytics().query(siteUrl=site, body=request).execute()
                rows = response.get("rows", [])

                if not rows:
                    st.warning("No data returned for this period.")
                else:
                    records = []
                    for row in rows:
                        record = {
                            "date": row["keys"][0],
                            "page": row["keys"][1],
                            "clicks": row.get("clicks", 0),
                            "impressions": row.get("impressions", 0),
                            "ctr": row.get("ctr", 0),
                            "position": row.get("position", 0),
                        }
                        records.append(record)

                    df = pd.DataFrame(records)
                    df["date"] = pd.to_datetime(df["date"])

                    url_counts = df.groupby("date")["page"].nunique().reset_index()
                    url_counts.columns = ["date", "unique_urls"]
                    clicks = df.groupby("date")["clicks"].sum().reset_index()

                    fig_urls = px.line(url_counts, x="date", y="unique_urls", title="Unique URLs Indexed per Day")
                    st.plotly_chart(fig_urls, use_container_width=True)

                    fig_clicks = px.line(clicks, x="date", y="clicks", title="Total Clicks per Day")
                    st.plotly_chart(fig_clicks, use_container_width=True)

                    st.subheader("📋 Raw Data Preview")
                    st.dataframe(df.head())

                    st.subheader("🔍 Page-Level Insights")
                    page_summary = (
                        df.groupby("page")[["clicks", "impressions", "ctr", "position"]]
                        .agg({
                            "clicks": "sum",
                            "impressions": "sum",
                            "ctr": "mean",
                            "position": "mean"
                        })
                        .sort_values(by="clicks", ascending=False)
                        .reset_index()
                    )
                    st.dataframe(page_summary.head(20))

                    st.subheader("📥 Download CSV")
                    csv_raw = df.to_csv(index=False).encode("utf-8")
                    st.download_button("Download Raw Data (Date + Page)", csv_raw, "gsc_raw_data.csv", "text/csv")

                    csv_page = page_summary.to_csv(index=False).encode("utf-8")
                    st.download_button("Download Page-Level Summary", csv_page, "gsc_page_summary.csv", "text/csv")

        if st.button("Clear Credentials and Restart Authorization"):
            st.session_state.creds = None
            st.experimental_rerun()
