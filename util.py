import re
import pytz
import os
from pymongo import MongoClient
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

MONGO_DB = os.environ.get('MONGO_DB')
MONGO_URL = os.environ.get('MONGO_URL')
HASHTAG_RE = re.compile(r'#\w+', re.UNICODE)



# Ensure that time is in SG timezone
def utc_to_time(naive, timezone="Singapore"):
  return naive.replace(tzinfo=pytz.utc).astimezone(pytz.timezone(timezone))

def get_user_collection(username, get_points=False):
    '''Creating a collection in Mongo Database with collection_name = Telegram's Username'''
    client = MongoClient(MONGO_URL)
    database = client[MONGO_DB]

    collection_name = str(username)
    user_coll = database[collection_name]

    # If need to get points from collection as well
    if get_points:
        # Search Query for Points in database
        find = {"points": {"$gt": 0}}

        # Retrieve max points
        all_pts = user_coll.find(find)
        if all_pts.count() > 0:
            max_pt = int(all_pts.sort('points', -1)[0]['points'])
        else:
            max_pt = 0
        return user_coll, max_pt

    return user_coll

def get_document_from_message(msg):
    '''Converting the message into a dictionary'''
    tags = [t[1:] for t in HASHTAG_RE.findall(msg)]
    post = msg

    now = utc_to_time(datetime.utcnow())
    time = f"{now.strftime('%B %d, %Y')} at {now.strftime('%H:%M:%S')}"
    
    # Check if msg contains Points OR if smb is just trying to hack the system :/
    isPoints = "Total Points: "
    if isPoints in msg:
        pts = int(msg.split(isPoints)[-1])

    else:
        pts = "NA"
    doc = {
        'time': now,
        'time_formatted': time,
        'post': post,
        'points': pts,
        'tags': tags,
        }
    return doc

def get_first_hashtag(post):
    tags = HASHTAG_RE.findall(post)
    return tags[0] if tags else ''

def show_all_tasks(ls):
    message = "<b>All Tasks</b>"

    for task in ls:
        message += f"\n{task['name']}, <b>Code</b>: {task['pw']}, <b>Points</b>: {task['pts']}"

    return message