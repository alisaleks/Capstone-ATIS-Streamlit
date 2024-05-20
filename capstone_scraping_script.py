import requests
from bs4 import BeautifulSoup
import csv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from dateutil import parser
import time
import re
import pandas as pd
import datetime
import os

# Initialize the WebDriver
def initialize_browser(browser_type="chrome"):
    print("Initializing browser...")
    if browser_type.lower() == "chrome":
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # run headless if desired
        browser = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
    else:
        raise ValueError("Unsupported browser type: use 'chrome'")
    return browser

def format_date(date_string):
    try:
        date_obj = parser.parse(date_string, dayfirst=False)
        formatted_date = date_obj.strftime("%d.%m.%y")
        return formatted_date
    except (parser.ParserError, ValueError):
        return "not specified"

def parse_application_period(period_string):
    try:
        start_date_str, end_date_str = period_string.split(" until ")
        start_date = format_date(start_date_str)
        end_date = format_date(end_date_str)
        return start_date, end_date
    except ValueError:
        return "not specified", "not specified"

def extract_tender_code(tender_name, source_url):
    if "myorder.rib.de" in source_url:
        match = re.search(r'\(([^)]+)\)', tender_name)
        tender_code = tender_name.split()[0] if match is None else match.group(1)
    else:
        tender_code = tender_name.split()[0]
    return tender_code

def extract_tender_deadline(block):
    deadline_labels = ["Application deadline", "Expiration time"]
    for label in deadline_labels:
        info_tag = block.find('div', class_='info-label', string=lambda text: text and label in text)
        if info_tag:
            value = info_tag.find_next('div').text.strip()
            return format_date(value)
    return "not specified"

def scrape_bayern_selenium(browser, url, keywords, source_url):
    print(f"Scraping dynamic content from {url}...")
    tenders = []
    browser.get(url)
    
    # Scroll to the bottom of the page to ensure all dynamic content is loaded
    last_height = browser.execute_script("return document.body.scrollHeight")
    while True:
        # Scroll down to the bottom of the page
        browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        
        # Wait for new content to load
        time.sleep(2)
        
        # Calculate new scroll height and compare with last scroll height
        new_height = browser.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

    # Now that the page is fully loaded, proceed with scraping
    html = browser.page_source
    soup = BeautifulSoup(html, 'html.parser')
    
    tender_blocks = soup.find_all('div', class_='item')
    print(f"Found {len(tender_blocks)} tender blocks.")

    for block in tender_blocks:
        title_div = block.find('div', style=lambda value: value and 'overflow: hidden' in value)
        title_tag = title_div.find('strong') if title_div else None

        if title_tag:
            title = title_tag.get_text(strip=True)
            found_keywords = [keyword for keyword in keywords if keyword.lower() in title.lower()]
            if found_keywords:
                description_tag = block.find('div', class_='text-muted')
                description = description_tag.get_text(strip=True) if description_tag else "No Description"
                
                tender_authority = description.split(' by ')[-1]
                tender_code = extract_tender_code(title, source_url)
                
                tender_details = {
                    'tender_name': title,
                    'tender_authority': tender_authority,
                    'tender_code': tender_code,
                    'source_url': source_url,
                    'found_keywords': ', '.join(found_keywords)
                }

                info_dict = {
                    'Application period': 'application_period',
                    'Period': 'period',
                    'Execution place': 'tender_location'
                }

                for info_label, info_key in info_dict.items():
                    info_tag = block.find('div', class_='info-label', string=lambda text: text and info_label in text)
                    if info_tag:
                        value = info_tag.find_next('div').text.strip() if info_tag.find_next('div') else "not specified"
                        if info_key == 'application_period':
                            start_date, end_date = parse_application_period(value)
                            tender_details['application_start_date'] = start_date
                            tender_details['application_deadline'] = end_date
                        else:
                            tender_details[info_key] = value

                tender_details['tender_deadline'] = extract_tender_deadline(block)
                
                # Extract publication date
                date_div = block.find('div', class_='item-right meta')
                if date_div:
                    day = date_div.find('div', class_='date').text.strip()
                    month_year = date_div.find('div', class_='month').text.strip()
                    publication_date_str = f"{day} {month_year}"
                    publication_date = format_date(publication_date_str)
                    tender_details['date_published'] = publication_date
                else:
                    tender_details['date_published'] = "not specified"

                tenders.append(tender_details)

    return tenders

def scrape_muenchen(html, keywords, source_url):
    print(f"Scraping static content from {source_url}...")
    tenders = []
    soup = BeautifulSoup(html, 'html.parser')

    tender_rows = soup.find_all('tr', class_='tableRow clickable-row publicationDetail')
    print(f"Found {len(tender_rows)} tender rows.")

    for row in tender_rows:
        date_published = row.find('td').text.strip()
        tender_name = row.find('td', class_='tender').text.strip()
        tender_authority = row.find('td', class_='tenderAuthority').text.strip()
        tender_type = row.find('td', class_='tenderType').text.strip()
        tender_deadline = row.find('td', class_='tenderDeadline').text.strip()

        # Remove the hour from the tender deadline
        tender_deadline_date = tender_deadline.split(' ')[0]  # This assumes the format is "date time"
        formatted_deadline = format_date(tender_deadline_date)  # Format the date if needed

        # Reformat date published to dd.mm.yy
        try:
            date_obj = parser.parse(date_published, dayfirst=True)
            formatted_date_published = date_obj.strftime("%d.%m.%y")
        except (parser.ParserError, ValueError):
            formatted_date_published = "not specified"

        found_keywords = [keyword for keyword in keywords if keyword.lower() in tender_name.lower()]
        if found_keywords:
            tenders.append({
                'date_published': formatted_date_published,  # Use the formatted date
                'tender_name': tender_name,
                'tender_authority': tender_authority,
                'tender_type': tender_type,
                'tender_deadline': formatted_deadline,  # Use the formatted deadline
                'source_url': source_url,
                'found_keywords': ', '.join(found_keywords)
            })
        
    return tenders

def scrape_baden(html, keywords, source_url):
    print(f"Scraping static content from {source_url}...")
    tenders = []
    soup = BeautifulSoup(html, 'html.parser')

    tender_divs = soup.find_all('div', class_='col-6-l col-6-m  col-12 searchResult')
    print(f"Found {len(tender_divs)} tender divs.")

    for div in tender_divs:
        tender_name = div.find('div', class_='bekanntmachung-titel').text.strip()
        deadline = div.find('span', string='Deadline').find_next_sibling('span').text.strip()
        location = div.find('span', string='Location').find_next_sibling('span').text.strip()

        found_keywords = [keyword for keyword in keywords if keyword.lower() in tender_name.lower()]
        if found_keywords:
            formatted_deadline = format_date(deadline)
            tender_code = extract_tender_code(tender_name, source_url)
            tenders.append({
                'tender_name': tender_name,
                'tender_deadline': formatted_deadline,
                'tender_location': location,
                'source_url': source_url,
                'found_keywords': ', '.join(found_keywords),
                'tender_code': tender_code
            })

    return tenders

def scrape_website(url):
    print(f"Fetching content from {url}...")
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raises an HTTPError if the HTTP request returned an unsuccessful status code
        return response.text
    except requests.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
    except Exception as err:
        print(f"An error occurred: {err}")
    return None

def scrape_all():
    results = []
    browser = initialize_browser("chrome")
    
    websites = {
        "https://vergabe.muenchen.de/NetServer/PublicationSearchControllerServlet?function=SearchPublications&Gesetzesgrundlage=All&Category=InvitationToTender&thContext=publications": (scrape_muenchen, "https://vergabe.muenchen.de"),
        "https://www.vergabe24.de": (scrape_baden, "https://www.vergabe24.de")
    }

    keywords = ["Erlebnis", "Freizeit", "Destination", "Tourismus", "Tourismusförderung", "Tourismuskonzept", "Tourismuskonzeption", "Tourismusservice", "Besucher", "Museum", "Markenwelt", "Ausstellung", "Ideenskizze", "Konzept", "Nutzungsidee", "Masterplan", "Machbarkeit", "Beratung", "Studie", "Analyse", "Machbarkeitsanalyse", "Marktforschung", "Plausibilisierung","Investitionskostenschätzung", "Machbarkeitsstudie", "Besucherzentrum", "Informationszentrum", "Gartenschau", "Grünanlage", "Besucherinformationszentrum"]

    for url, (scrape_func, source_url) in websites.items():
        if scrape_func.__name__ != 'scrape_bayern_selenium':
            html = scrape_website(url)
            if html:
                tenders = scrape_func(html, keywords, source_url)
                results.extend(tenders)

    dynamic_url = "https://www.myorder.rib.de/public/publications"
    dynamic_source_url = dynamic_url
    bayern_results = scrape_bayern_selenium(browser, dynamic_url, keywords, dynamic_source_url)
    results.extend(bayern_results)

    browser.quit()

    if not results:
        return pd.DataFrame()  # Return an empty DataFrame if no results

    # Write the results to a CSV file
    fieldnames = [
        'tender_name', 
        'tender_authority',  # Authority part of description
        'application_start_date',  # Start date of application
        'application_deadline',  # End date of application
        'tender_deadline',  # Harmonized key for deadlines
        'period',  # Unique to scrape_bayern
        'tender_location',  # Harmonized key for location/execution place
        'date_published',  # From scrape_bayern and scrape_muenchen
        'tender_type',  # Unique to scrape_muenchen
        'source_url',  # Common across all functions
        'found_keywords',  # New column for found keywords
        'tender_code'  # New column for tender code
    ]
    df = pd.DataFrame(results, columns=fieldnames)

    # Get the current date and time
    now = datetime.datetime.now()
    formatted_date = now.strftime("%Y-%m-%d_%H-%M-%S")

    # Ensure the directory exists
    output_dir = "master/2_streamlit/Capstone_ATIS_Streamlit"
    os.makedirs(output_dir, exist_ok=True)

    # Save the DataFrame to a CSV file with the date and time in the filename
    filename = os.path.join(output_dir, f'capstone_results_{formatted_date}.csv')
    df.to_csv(filename, index=False)
    print(f"Scraping completed. Data saved to {filename}")
    
    return df
