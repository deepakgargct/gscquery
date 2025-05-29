import streamlit as st
import pandas as pd
import plotly.express as px
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import json

st.title("Google Search Console Performance Comparison")

uploaded_file = st.file_uploader("Upload your Google Service Account JSON key file", type=["json"])
property_uri = st.text_input("Enter your GSC Property URL (e.g., https://example.com)")

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
    return pd.DataFrame(data)

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
    df["position_change"] = df["position_current"] - df["position_previous"]
    return df

def filter_top_dropping(df):
    filtered = df[
        (df["clicks_change"] < 0) &
        (df["ctr_change"] < 0) &
        (df["impressions_change"] > 0)
    ].sort_values(by="impressions_change", ascending=False).head(20)
    return filtered

def plot_position_trends(df, group_col):
    df["date"] = pd.to_datetime(df["date"])
    # average position over time per group_col
    fig = px.line(
        df.groupby([group_col, "date"])["position"].mean().reset_index(),
        x="date",
        y="position",
        color=group_col,
        title=f"Average Position Over Time by {group_col.capitalize()}",
        labels={"position": "Average Position", "date": "Date"},
    )
    fig.update_yaxes(autorange="reversed")  # lower position is better
    st.plotly_chart(fig, use_container_width=True)

if st.button("Fetch and Compare Data"):
    if not uploaded_file or not property_uri:
        st.error("Please upload a service account JSON key file and enter your GSC Property URL.")
    else:
        try:
            json_dict = json.load(uploaded_file)
            creds = service_account.Credentials.from_service_account_info(json_dict)
            service = build("searchconsole", "v1", credentials=creds, cache_discovery=False)

            with st.spinner("Fetching current period data..."):
                df_current = fetch_gsc_data(service, property_uri, start_date, end_date, group_by)
            with st.spinner("Fetching previous period data..."):
                df_previous = fetch_gsc_data(service, property_uri, prev_start_date, prev_end_date, group_by)

            agg_current = aggregate_metrics(df_current, group_by)
            agg_previous = aggregate_metrics(df_previous, group_by)

            comparison_df = calculate_comparison(agg_current, agg_previous, group_by)

            st.subheader("Summary Comparison (Current vs Previous Period)")
            st.dataframe(comparison_df.style.format({
                "ctr_current": "{:.2%}", "ctr_previous": "{:.2%}", "ctr_change": "{:.2%}",
                "position_current": "{:.2f}", "position_previous": "{:.2f}", "position_change": "{:.2f}"
            }))

            st.subheader("Top 20 Dropping Queries/Pages (Clicks & CTR down, Impressions up)")
            filtered = filter_top_dropping(comparison_df)
            st.dataframe(filtered.style.format({
                "ctr_current": "{:.2%}", "ctr_previous": "{:.2%}", "ctr_change": "{:.2%}",
                "position_current": "{:.2f}", "position_previous": "{:.2f}", "position_change": "{:.2f}"
            }))

            st.subheader(f"Aggregated Current Period Metrics by {group_by.capitalize()}")
            st.dataframe(agg_current.style.format({
                "ctr": "{:.2%}", "position": "{:.2f}"
            }))

            st.subheader(f"Average Position Trends Over Time by {group_by.capitalize()}")
            plot_position_trends(df_current, group_by)

        except Exception as e:
            st.error(f"Error fetching data from Google Search Console API:\n{e}")
