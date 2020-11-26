import logging
import os
import util
import settings
from dotenv import load_dotenv
from datetime import datetime, timedelta
from pymongo import MongoClient, TEXT, DESCENDING
from operator import itemgetter
from telegram import (
    ParseMode,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackQueryHandler,
    ConversationHandler
)



logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()

MONGO_DB = os.environ.get('MONGO_DB')
MONGO_URL = os.environ.get('MONGO_URL')
DEVELOPER_CHAT_ID = int(os.environ.get('DEVELOPER_CHAT_ID'))
SUPER_ADMIN = os.environ.get('SUPER_ADMIN')

ONE, TWO, THREE, FOUR = range(4)



def super_admin(update, context):
    """Options available to me :)"""

    username = update.message.from_user.username
    if username == SUPER_ADMIN:
        message = f"Welcome back Sean! :)\nWhat would you like to do today?"
    else:
        message = "**<b>SUPERADMIN ACCESS DENIED</b>**"
        msg_to_dev = f"{username} just tried to access /superadmin"
        update.message.reply_text(text=message, parse_mode=ParseMode.HTML)
        context.bot.send_message(chat_id=DEVELOPER_CHAT_ID, text=msg_to_dev)
        return ConversationHandler.END

    # Show list of things that can be done
    keyboard = [
        [InlineKeyboardButton(f"Add Admin", callback_data=str(ONE))], 
        [InlineKeyboardButton(f"Delete Admin", callback_data=str(TWO))],
        ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text(text=message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    return SUPER_ADMIN

def super_action(update, context):
    query = update.callback_query
    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    query.answer()

    chat_id = query.message.chat_id
    callback = query.data

    msg = "Please enter the Telegram ID you would like to "
    if callback == "0":
        msg += "add."
        context.user_data["task_selected"] = 0
    else:
        msg += "delete."
        context.user_data["task_selected"] = 1
    
    context.bot.send_message(chat_id=chat_id, text=msg)
    return SUPER_ADMIN

def confirm_super_action(update, context):
    tele_id = update.message.text
    
    task_selected = context.user_data["task_selected"]
    if task_selected == 0:
        
        settings.ADMIN_IDS.append(tele_id)
        # Just to ensure that they are unique
        settings.ADMIN_IDS = list(set(settings.ADMIN_IDS))
        msg = f"Successfully added <b>{tele_id}</b>"
    else:
        if tele_id in settings.ADMIN_IDS:
            settings.ADMIN_IDS.remove(tele_id)
            msg = f"Successfully removed <b>{tele_id}</b>"
        else:
            msg = f"<b>{tele_id}</b> is not an admin."

    for i, el in enumerate(settings.ADMIN_IDS):
        msg += f"\n{i+1}. {el}"
    update.message.reply_text(text=msg, parse_mode=ParseMode.HTML)

    return ConversationHandler.END

def admin(update, context):
    """Options available to Admins"""

    username = update.message.from_user.username
    
    if username in settings.ADMIN_IDS:
        message = f"<b>ADMIN ACCESS AUTHENTICATED</b>\nWelcome back {username}! What would you like to do today?"
    else:
        message = "**<b>ADMIN ACCESS DENIED</b>**"
        update.message.reply_text(text=message, parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    # Show list of things that can be done
    keyboard = [
        [InlineKeyboardButton(f"Show Stats", callback_data=str(ONE))], 
        [InlineKeyboardButton(f"All Users", callback_data=str(TWO))],
        [InlineKeyboardButton(f"All Tasks", callback_data=str(THREE))],
        ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text(text=message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    return settings.admin_menu[0]

def stats(update, context):
    query = update.callback_query
    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    query.answer()

    user = query.from_user
    chat_id = query.message.chat_id
    user_coll = util.get_user_collection(user)
    response = f'🗄 Your Database has {user_coll.count()} records\n'

    if user.username in settings.ADMIN_IDS:
        client = MongoClient(MONGO_URL)
        db = client[MONGO_DB]
        coll_counts = [db[coll].count() for coll in db.collection_names()]
        response += f'\nDatabase has `{len(coll_counts)} user(s)`\n'
        response += f'Biggest collection sizes: `{sorted(coll_counts)[-3:]}`\n'

        month_ago = datetime.utcnow() - timedelta(days=30)
        recent_counts = [db[coll].find({'time': {'$gt': month_ago}}).count()
                        for coll in db.collection_names()]
        response += f'New records over past 30 days:  `{sum(recent_counts)}`\n'
        active_colls = sum([c > 0 for c in recent_counts])
        response += f'Users active over past 30 days: `{active_colls}`\n'

    # Send stats
    context.bot.send_message(chat_id=chat_id, text=response, parse_mode=ParseMode.MARKDOWN_V2)

    return settings.admin_menu[0]

def all_users(update, context):
    query = update.callback_query
    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    query.answer()

    user = query.from_user
    chat_id = query.message.chat_id
    # prev_msg = query.message.text

    # Search query: Find all points greater than 0
    find = {"points": {"$gt": 0}}

    if user.username in settings.ADMIN_IDS:
        client = MongoClient(MONGO_URL)
        db = client[MONGO_DB]
        message = "<b>All Users</b>"
        # If no element, 'for loop' will not execute
        # Add each username and max_pt to a tuple and append to list for sorting
        score_ls = []
        for i, username in enumerate(db.collection_names()):
            all_pts = db[username].find(find)
            # Only sort and retrieve points if there is at least one dict in collection with points = Int
            if all_pts.count() > 0:
                max_pt = all_pts.sort('points',-1)[0]["points"] # Sort in reverse (Descending order). Get first element. Get key = "points"
            else: 
                max_pt = 0
            score_ls.append((username, max_pt))
        score_ls.sort(reverse=True, key=itemgetter(1))

        for i, el in enumerate(score_ls):
            message += f"\n{i+1}. {el[0]} - {el[1]}"

    # Send stats
    context.bot.send_message(chat_id=chat_id, text=message, parse_mode=ParseMode.HTML)
    # Remove button
    # query.edit_message_text(text=prev_msg)
    
    return settings.admin_menu[0]

def all_tasks(update, context):
    """Show all tasks
    1) Add Task
    2) Change verification code
    """
    query = update.callback_query
    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    query.answer()

    chat_id = query.message.chat_id
    # prev_msg = query.message.text
    message = util.show_all_tasks(settings.task_list)
    
    keyboard = [
        [InlineKeyboardButton(f"Add Task", callback_data=str(ONE))],
        [InlineKeyboardButton(f"Delete Task", callback_data=str(TWO))],
        [InlineKeyboardButton(f"Change Verification Code", callback_data=str(THREE))],
        [InlineKeyboardButton(f"Change Points Earned", callback_data=str(FOUR))],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.bot.send_message(chat_id=chat_id, text=message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

    return settings.admin_menu[1]

def task_action(update, context):
    # TO-DO Finish up add task + change verification code!
    query = update.callback_query
    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    query.answer()

    # user = query.from_user
    chat_id = query.message.chat_id
    # prev_msg = query.message.text
    callback = int(query.data)

    if callback == 0:
        message = "Please enter the name of the task, verification code and points earned separated by commas\nE.g. Lunch with fellow Angel, verificationCode, 2"
        # Check if adding new task or changing verification code by saving it to context.user_data["task_selected"]
        context.user_data["task_selected"] = 0
    elif callback == 1:
        message = "Please enter the task number you would like to delete."
        context.user_data["task_selected"] = 1
    elif callback == 2:
        message = "Please enter the task number followed by the new verification code.\nE.g. <code>1 ILuvRoot!</code>"
        context.user_data["task_selected"] = 2
    elif callback == 3:
        message = "Please enter the task number followed by the new points earned upon successful completion.\nE.g. <code>1 2</code>"
        context.user_data["task_selected"] = 3

    context.bot.send_message(chat_id=chat_id, text=message, parse_mode=ParseMode.HTML)
    return settings.admin_menu[2]


def verify_task_action(update, context):
    message = update.message.text
    # chat_id = update.message.text.chat_id

    # Need to add points to 'Add Task', Change points functionality

    # Check which task selected
    task_selected = context.user_data["task_selected"]

    # Add Task
    if task_selected == 0:
        task_num = len(settings.task_list) + 1
        task, code, pts = [i for i in message.split(", ")]

        response = f"Task {task_num}: {task}\nCode: {code}\nPoints: {pts}\nConfirm?"
    # Delete Task
    elif task_selected == 1:
        idx = int(message) - 1
        if idx < 0 or idx > (len(settings.task_list)-1):
            response = f"Please enter a task number from 1 to {len(settings.task_list)}."
            update.message.reply_text(text=response)
            return ConversationHandler.END
        else:
            response = f"{settings.task_list[idx]['name']}\nConfirm?\n<b>WARNING! TASK WILL BE PERMANENTLY DELETED!</b>"
    # Change Verification Code OR Change Points earned
    elif task_selected == 2 or task_selected == 3:
        idx = int(message.split(" ")[0]) - 1
        to_be_changed = message.split(" ")[1]
        if idx < 0 or idx > (len(settings.task_list)-1):
            response = f"Please enter a task number from 1 to {len(settings.task_list)}."
            update.message.reply_text(text=response)
            return ConversationHandler.END
        else:
            if task_selected == 2:
                response = f"{settings.task_list[idx]['name']}\nCode: {to_be_changed}\nConfirm?"
            else:
                response = f"{settings.task_list[idx]['name']}\nPoints: {to_be_changed}\nConfirm?"

    keyboard = [
        [InlineKeyboardButton(f"Yes", callback_data=str(ONE))],
        [InlineKeyboardButton(f"No", callback_data=str(TWO))],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text(text=response, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    return settings.admin_menu[2]

def confirm_task_action(update, context):
    query = update.callback_query
    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    query.answer()

    prev_msg = query.message.text
    callback = int(query.data)
    chat_id = query.message.chat_id
    # Retrieve task number to delete from previous message
    task_num = int(prev_msg.split(" ")[1].rstrip(':'))
    idx = task_num - 1
    task_selected = context.user_data["task_selected"]
    if callback == 0:
        # Delete a task
        if task_selected == 1:
            settings.task_list.pop(idx)
            # Change numbering of tasks accordingly
            # Note: This is hard-coded in the sense that the dictionary name MUST HAVE 'Task <Num>:' at the start
            for i, d in enumerate(settings.task_list):
                start_idx = d['name'].index(' ')
                colon_idx = d['name'].index(':')
                num = int(d['name'][start_idx:colon_idx])
                num = i+1
                d['name'] = f"Task {num}" + d['name'][colon_idx:]

            msg = f"<b>Successfully deleted task!</b>\n{util.show_all_tasks(settings.task_list)}"
        else:
            new_task = prev_msg.split("\n")[0]
            # Add a task
            if task_selected == 0:
                code = prev_msg.split("Code: ")[1].split("\n")[0]
                pts = int(prev_msg.split("Points: ")[1].split("\n")[0])
                settings.task_list.append({
                    "name": new_task,
                    "pw": code,
                    "pts": pts
                })
                msg = f"<b>Successfully added new task!</b>\n{util.show_all_tasks(settings.task_list)}"
            # Change verification code
            elif task_selected == 2:
                code = prev_msg.split("Code: ")[1].split("\n")[0]
                settings.task_list[idx]['pw'] = code
                msg = f"<b>Successfully changed verification code!</b>\n{util.show_all_tasks(settings.task_list)}"
            # Change points earned
            else:
                pts = int(prev_msg.split("Points: ")[1].split("\n")[0])
                settings.task_list[idx]['pts'] = pts
                msg = f"<b>Successfully changed points!</b>\n{util.show_all_tasks(settings.task_list)}"

        context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    else:
        context.bot.send_message(chat_id=chat_id, text="Alright, see you!", parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    query = update.callback_query
    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    query.answer()

    prev_msg = query.message.text
    callback = int(query.data)
    chat_id = query.message.chat_id
    # Retrieve task number to delete from previous message
    task_num = int(prev_msg.split(" ")[1].rstrip(':'))
    idx = task_num - 1
    task_selected = context.user_data["task_selected"]
    if callback == 0:
        # Delete a task
        if task_selected == 1:
            settings.task_list.pop(idx)
            msg = f"<b>Successfully deleted task!</b>\n{util.show_all_tasks(settings.task_list)}"
        else:
            new_task = prev_msg.split("\n")[0]
            code = prev_msg.split("\n")[1][6:]
            # Add a task
            if task_num == len(settings.task_list) + 1:
                settings.task_list.append([new_task, code])
                msg = f"<b>Successfully added new task!</b>\n{util.show_all_tasks(settings.task_list)}"
            # Change verification code
            else:
                settings.task_list[idx][1] = code
                msg = f"<b>Successfully changed verification code!</b>\n{util.show_all_tasks(settings.task_list)}"

        context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    else:
        context.bot.send_message(chat_id=chat_id, text="Alright, see you!", parse_mode=ParseMode.HTML)
        return ConversationHandler.END