import pandas as pd
import streamlit as st
import pydeck as pdk
from datetime import datetime
from capstone_scraping_script import scrape_all  # Import the scrape_all function

# Cache the scraping function to avoid redundant calls
@st.cache_data
def fetch_latest_data():
    return scrape_all()

# Fetch the latest data
df = fetch_latest_data()

# Actual city coordinates (replace with real values)
city_coordinates = {
    'Erlangen': {'latitude': 49.5896744, 'longitude': 11.0068111},
    'Berlin': {'latitude': 52.5200066, 'longitude': 13.404954},
    'Darmstadt': {'latitude': 49.8728253, 'longitude': 8.6511929},
    'Ulm': {'latitude': 48.4010822, 'longitude': 9.9876073},
    'Wuppertal': {'latitude': 51.2562128, 'longitude': 7.1507646},
    'Rheda-Wiedenbrück': {'latitude': 51.8492961, 'longitude': 8.3008344},
    'Cuxhaven': {'latitude': 53.8610103, 'longitude': 8.6947224},
    'München': {'latitude': 48.1351253, 'longitude': 11.5819806},
    'Nieste': {'latitude': 51.2998113, 'longitude': 9.6984197},
    'Kiel': {'latitude': 54.3232927, 'longitude': 10.1227655},
    'Freiberg': {'latitude': 50.910924, 'longitude': 13.3438359},
    'Neu-Ulm': {'latitude': 48.3923122, 'longitude': 10.0117107},
    'Amberg': {'latitude': 49.442754, 'longitude': 11.8634993},
}

# Function to extract unique city names from the 'tender_location' column
def extract_cities(df):
    df['city'] = df.apply(
        lambda row: row['tender_location'].split(' ')[1] if pd.notnull(row['tender_location']) and ' ' in row['tender_location'] and row['source_url'] == 'https://www.myorder.rib.de/public/publications' else 
        'München' if row['source_url'] == 'https://vergabe.muenchen.de' and pd.isnull(row['tender_location']) else None,
        axis=1
    )
    unique_cities = df['city'].dropna().unique()
    return unique_cities

# Function to add coordinates based on city names
def add_coordinates(df):
    df['city'] = df.apply(
        lambda row: row['tender_location'].split(' ')[1] if pd.notnull(row['tender_location']) and ' ' in row['tender_location'] and row['source_url'] == 'https://www.myorder.rib.de/public/publications' else 
        'München' if row['source_url'] == 'https://vergabe.muenchen.de' and pd.isnull(row['tender_location']) else None,
        axis=1
    )
    df['latitude'] = df['city'].apply(lambda x: city_coordinates[x]['latitude'] if x in city_coordinates else None)
    df['longitude'] = df['city'].apply(lambda x: city_coordinates[x]['longitude'] if x in city_coordinates else None)
    return df

# Extract unique city names and add coordinates to the dataframe
unique_cities = extract_cities(df)
df = add_coordinates(df)

# Add 'ALL' option to unique_cities
unique_cities = ['ALL'] + list(unique_cities)

# Get unique keywords
keywords = df['found_keywords'].str.split(';').explode().unique()

def display_overview(df, location_column, date_columns):
    st.header("Company Overview")
    
    st.markdown("""
    **Erlebniskontor GmbH** is a consultancy with over 25 years of expertise in creating and managing innovative visitor centers, brand worlds, and exhibitions. Specializing in the seamless integration of location, concept, and operation, the company ensures the success of tourism and cultural projects. With a focus on collaboration, they tailor experiences to meet the needs of clients and audiences alike. Services include comprehensive economic analyses, feasibility studies, and strategic planning to establish a solid foundation for each project.  
    **Current Challenge**  
    In Germany's federal system, each state issues its tenders separately, requiring the exhaustive effort of searching through 16 different portals, in addition to federal tenders.  
    **Operational Inefficiency**  
    The need to manually sift through numerous tender platforms results in a significant drain on time and resources.  
    **GOALS**  
    * Develop a fully functional Automated Tender Identification System (ATIS).  
    * Generate daily reports of new, relevant tender opportunities.  
    * Save time and increase efficiency in operational processes, allowing more focus on creative and experiential aspects.
    """)

    st.subheader("Filtered Tender Data")
    
    location = st.sidebar.multiselect("Filter by Location", unique_cities, default=['ALL'])
    keyword = st.sidebar.selectbox("Filter by Keyword", options=['ALL'] + list(keywords))
    
    for col in date_columns:
        date_range = st.sidebar.date_input(f"Filter by {col.replace('_', ' ').title()} Range", [])
        if len(date_range) == 2:
            start_date, end_date = date_range
            df = df[(pd.to_datetime(df[col], format="%d.%m.%y") >= pd.to_datetime(start_date)) & 
                    (pd.to_datetime(df[col], format="%d.%m.%y") <= pd.to_datetime(end_date))]

    if 'ALL' not in location:
        df = df[df[location_column].isin(location)]
    if keyword != 'ALL':
        df = df[df['found_keywords'].str.contains(keyword, case=False, na=False)]

    st.dataframe(df)
    st.write(f"Number of rows: {df.shape[0]}")

    st.download_button(
        label="Download filtered data as CSV",
        data=df.to_csv().encode('utf-8'),
        file_name='filtered_tenders.csv',
        mime='text/csv'
    )

def display_statistics(df, location_column):
    st.header("Statistics Summary")

    df['application_period'] = (pd.to_datetime(df['tender_deadline'], format="%d.%m.%y") - pd.to_datetime(df['application_start_date'], format="%d.%m.%y")).dt.days
    df['published_period'] = (datetime.now() - pd.to_datetime(df['date_published'], format="%d.%m.%y")).dt.days
    
    stat_df = df.groupby(location_column).agg({
        'application_period': 'mean',
        'published_period': 'mean'
    }).reset_index()

    stat_df['application_period'] = stat_df['application_period'].round(2)
    stat_df['published_period'] = stat_df['published_period'].round(2)
    stat_df.columns = ['City', 'Average Application Period (days)', 'Average Published Period (days)']

    st.write(stat_df)

    st.header("Bar Charts")
    criteria = st.radio("Select criteria for bar chart", ['Location', 'Keywords by Location'])

    if criteria == 'Location':
        bar_data = df.groupby(location_column).size().reset_index(name='count')
        st.bar_chart(bar_data.set_index(location_column)['count'])
    else:
        keyword_col = 'found_keywords'
        bar_data = df[keyword_col].str.split(';').explode().groupby(df[location_column]).value_counts().reset_index(name='count')
        bar_data.columns = [location_column, 'Keyword', 'count']
        bar_data_pivot = bar_data.pivot(index='Keyword', columns=location_column, values='count').fillna(0)
        st.bar_chart(bar_data_pivot)

    st.header("Publication Dates")
    pub_dates = df['date_published'].value_counts().reset_index(name='count')
    pub_dates.columns = ['Date', 'Count']
    pub_dates['Date'] = pd.to_datetime(pub_dates['Date'], format="%d.%m.%y")
    pub_dates = pub_dates.sort_values(by='Date')
    min_date = pub_dates['Date'].min().to_pydatetime()
    max_date = pub_dates['Date'].max().to_pydatetime()
    selected_date_range = st.slider("Select Date Range", min_value=min_date, max_value=max_date, value=(min_date, max_date), format="YYYY-MM-DD")
    pub_dates_filtered = pub_dates[(pub_dates['Date'] >= selected_date_range[0]) & (pub_dates['Date'] <= selected_date_range[1])]
    st.line_chart(pub_dates_filtered.set_index('Date')['Count'])

def display_map(df):
    st.header("Tender Locations on Map")
    if 'latitude' in df.columns and 'longitude' in df.columns:
        df_map = df.dropna(subset=['latitude', 'longitude']).copy()
        df_map['count'] = df_map.groupby(['latitude', 'longitude'])['tender_name'].transform('count')
        st.pydeck_chart(
            pdk.Deck(
                map_style="mapbox://styles/mapbox/light-v9",
                initial_view_state=pdk.ViewState(
                    latitude=df_map["latitude"].mean(),
                    longitude=df_map["longitude"].mean(),
                    zoom=6,
                    pitch=50,
                ),
                layers=[
                    pdk.Layer(
                        "ScatterplotLayer",
                        data=df_map,
                        get_position=["longitude", "latitude"],
                        get_color=[200, 30, 0, 160],
                        get_radius=10000,
                        pickable=True,
                        auto_highlight=True,
                    ),
                    pdk.Layer(
                        "TextLayer",
                        data=df_map,
                        get_position=["longitude", "latitude"],
                        get_text="count",
                        get_size=16,
                        get_color=[0, 0, 0],
                        get_alignment_baseline="'bottom'",
                    ),
                ],
                tooltip={"text": "City: {city}\nNumber of Tenders: {count}"}
            )
        )

def main():
    st.title("Automated Tender Identification System (ATIS)")

    # Define the columns
    location_column = 'city'
    date_columns = ['application_start_date', 'tender_deadline', 'date_published']

    tab_overview, tab_stats, tab_map = st.tabs(["Overview", "Statistics", "Map"])

    with tab_overview:
        display_overview(df, location_column, date_columns)
    with tab_stats:
        display_statistics(df, location_column)
    with tab_map:
        display_map(df)

if __name__ == "__main__":
    main()
