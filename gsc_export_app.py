import streamlit as st
import pandas as pd
import plotly.express as px
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import json  # <--- import json to parse uploaded file

# Initialize session state keys
if "data_fetched" not in st.session_state:
    st.session_state["data_fetched"] = False
if "gsc_data_current" not in st.session_state:
    st.session_state["gsc_data_current"] = None
if "gsc_data_previous" not in st.session_state:
    st.session_state["gsc_data_previous"] = None

st.title("Google Search Console: Query/Page Performance Export & Comparison")

uploaded_file = st.file_uploader("Upload your Google Service Account JSON key file", type=["json"])
property_uri = st.text_input("Enter your GSC Property URL (e.g., https://example.com)", key="property_uri")

today = datetime.today()
default_end = today - timedelta(days=1)
default_start = default_end - timedelta(days=180)
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Current Period Start Date", default_start)
with col2:
    end_date = st.date_input("Current Period End Date", default_end)

prev_start_date = start_date - (end_date - start_date) - timedelta(days=1)
prev_end_date = start_date - timedelta(days=1)

group_by = st.selectbox("Group data by:", options=["query", "page"])

def fetch_gsc_data(service, property_uri, start_date, end_date, dimension, row_limit=500):
    request = {
        "startDate": start_date.strftime("%Y-%m-%d"),
        "endDate": end_date.strftime("%Y-%m-%d"),
        "dimensions": [dimension, "date"],
        "rowLimit": row_limit,
    }
    response = service.searchanalytics().query(siteUrl=property_uri, body=request).execute()
    rows = response.get("rows", [])
    data = []
    for row in rows:
        dims = row.get("keys", [])
        if len(dims) == 2:
            key, date = dims
            clicks = row.get("clicks", 0)
            impressions = row.get("impressions", 0)
            ctr = row.get("ctr", 0)
            position = row.get("position", 0)
            data.append(
                {
                    dimension: key,
                    "date": date,
                    "clicks": clicks,
                    "impressions": impressions,
                    "ctr": ctr,
                    "position": position,
                }
            )
    df = pd.DataFrame(data)
    return df

def aggregate_metrics(df, group_col):
    agg = df.groupby(group_col).agg(
        clicks=pd.NamedAgg(column="clicks", aggfunc="sum"),
        impressions=pd.NamedAgg(column="impressions", aggfunc="sum"),
        ctr=pd.NamedAgg(column="ctr", aggfunc="mean"),
        position=pd.NamedAgg(column="position", aggfunc="mean"),
    ).reset_index()
    return agg

def calculate_comparison(current, previous, group_col):
    df = pd.merge(current, previous, on=group_col, suffixes=("_current", "_previous"))
    df["clicks_change"] = df["clicks_current"] - df["clicks_previous"]
    df["ctr_change"] = df["ctr_current"] - df["ctr_previous"]
    df["impressions_change"] = df["impressions_current"] - df["impressions_previous"]
    return df

def filter_top_growing_declining(df):
    filtered = df[
        (df["clicks_change"] < 0)
        & (df["ctr_change"] < 0)
        & (df["impressions_change"] > 0)
    ]
    filtered = filtered.sort_values(by="impressions_change", ascending=False).head(20)
    return filtered

def plot_trends(df, group_col):
    df["date"] = pd.to_datetime(df["date"])
    fig = px.line(
        df,
        x="date",
        y="clicks",
        color=group_col,
        title=f"Clicks Over Time by {group_col.capitalize()}",
        labels={"clicks": "Clicks", "date": "Date"},
    )
    st.plotly_chart(fig, use_container_width=True)

if st.button("Fetch and Compare Data"):
    if not uploaded_file or not property_uri:
        st.error("Please upload a service account JSON key file and enter your GSC Property URL.")
    else:
        try:
            json_dict = json.load(uploaded_file)  # <-- parse bytes JSON to dict here
            creds = service_account.Credentials.from_service_account_info(json_dict)
            service = build("searchconsole", "v1", credentials=creds, cache_discovery=False)

            with st.spinner("Fetching current period data..."):
                df_current = fetch_gsc_data(service, property_uri, start_date, end_date, group_by)
            with st.spinner("Fetching previous period data..."):
                df_previous = fetch_gsc_data(service, property_uri, prev_start_date, prev_end_date, group_by)

            st.session_state.gsc_data_current = df_current
            st.session_state.gsc_data_previous = df_previous
            st.session_state.data_fetched = True

        except Exception as e:
            st.error(f"Error fetching data from Google Search Console API:\n{e}")

if st.session_state.data_fetched:
    st.subheader("Aggregated Current Period Metrics")
    agg_current = aggregate_metrics(st.session_state.gsc_data_current, group_by)
    st.dataframe(agg_current)

    st.subheader("Aggregated Previous Period Metrics")
    agg_previous = aggregate_metrics(st.session_state.gsc_data_previous, group_by)
    st.dataframe(agg_previous)

    st.subheader("Comparison: Current vs Previous Period")
    comparison_df = calculate_comparison(agg_current, agg_previous, group_by)
    st.dataframe(comparison_df)

    st.subheader("Top 20 Queries/Pages with Clicks and CTR Dropping but Impressions Rising")
    filtered = filter_top_growing_declining(comparison_df)
    st.dataframe(filtered)

    st.subheader(f"Trends Over Time (Clicks) by {group_by.capitalize()}")
    plot_trends(st.session_state.gsc_data_current, group_by)
