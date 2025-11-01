import os
from dotenv import load_dotenv
from notion_client import Client
import requests
from urllib.parse import urlparse
from icalendar import Calendar
from datetime import datetime, timedelta, date

load_dotenv()




webcal_url = os.environ.get("WEBCAL_URL")

notion = Client(auth=os.environ["NOTION_TOKEN"])




def fetch_webcal_feed(webcal_url):
    #convert webcal:// to https://
    if webcal_url.startswith('webcal://'):
        http_url = webcal_url.replace('webcal://', 'https://')
    else:
        http_url = webcal_url
        
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/calendar,application/calendar,text/plain,*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
        
    response = requests.get(http_url, headers=headers, timeout=30)
    response.raise_for_status()

    calendar = Calendar.from_ical(response.content)
    
    events = []
    for component in calendar.walk():
        if component.name == "VEVENT":
            event = {
                'summary': str(component.get('summary')),
                'dtstart': component.get('dtstart').dt,
                'dtend': component.get('dtend').dt,
                'description': str(component.get('description')),
            }
            events.append(event)

    return events


def filter_future_events(events):
    today = date.today()    

    future_events = []
    for event in events:
        event_date = event['dtstart']
        
        if isinstance(event_date, datetime):
            event_date = event_date.date()

        if today <= event_date:
            future_events.append(event)
    
    return future_events


def filter_assignments(events):
    assignments = []
    numbers = ['1','2','3','4','5','6','7']
    for event in events:
        for number in numbers:
            if f'{number}:' in event['summary']:
                assignments.append(event)
    return assignments

def get_existing_assignments():
    """Get all existing assignments from Notion database"""
    try:
        url = f"https://api.notion.com/v1/databases/{os.environ['DATABASE_ID']}/query"
        
        headers = {
            "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        # Empty body for querying all pages
        data = {}
        
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        
        result = response.json()
        
        existing_titles = []
        for page in result['results']:
            # Get the title from the Name property
            title_property = page['properties']['Name']['title']
            if title_property:
                title = title_property[0]['text']['content']
                existing_titles.append(title)
        
        return existing_titles
    except Exception as e:
        print(f"Error fetching existing assignments: {e}")
        return []



def export_to_notion(events):
    existing_assignments = get_existing_assignments()
    for event in events:
        #Check if alr created
        if event['summary'] in existing_assignments:
            print(f"Skipped (already exists): {event['summary']}")
            continue
        
        #Convert datetime to ISO
        start_date = event['dtstart']
        end_date = event['dtend']
        
        if isinstance(start_date, datetime):
            start_iso = start_date.isoformat()
        else:
            # If it's a date object, convert to datetime then ISO
            start_iso = datetime.combine(start_date, datetime.min.time()).isoformat()
            
        # Handle end date  
        if isinstance(end_date, datetime):
            end_iso = end_date.isoformat()
        else:
            # If it's a date object, convert to datetime then ISO
            end_iso = datetime.combine(end_date, datetime.min.time()).isoformat()
        
        description = event['description'] if event['description'] and event['description'] != 'None' else ""
        
        try:
            #Create Page in Notion DB
            notion.pages.create(
                parent={"database_id": os.environ["DATABASE_ID"]},
                properties={
                    "Name": {
                        "title": [
                            {
                                "text": {
                                    "content": event['summary']
                            }
                        }
                    ]
                },
                "Due Date": {
                        "date": {
                            "start": start_iso,
                            "end": end_iso
                        }
                    },
                "Description": {
                        "rich_text": [
                            {
                                "text": {
                                    "content": description[:2000]  # Notion has a 2000 character limit
                                }
                            }
                        ]
                    }
            }
            )
            print(f"Added: {event['summary']} to Notion")
            
        except Exception as e:
            print(f"Error adding {event['summary']} to Notion: {e}")


events = filter_future_events(filter_assignments(fetch_webcal_feed(webcal_url)))

if events:
    export_to_notion(events)
else:
    print("No upcoming assignments found.")