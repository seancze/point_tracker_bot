#!/usr/bin/env python
# -*- coding: utf-8 -*-
# This program is dedicated to the public domain under the CC0 license.

"""
Basic example for a bot that works with polls. Only 3 people are allowed to interact with each
poll/quiz the bot generates. The preview command generates a closed poll/quiz, excatly like the
one the user sends the bot
"""
import logging
import os
import re # Regex expression
import traceback
import html
import json
import pytz # For cross-platform timezone calculations
import uuid # For security
import csv
import subprocess # Execute some Python process?
import py7zr # Compressing
import util
import admin
import settings
from dotenv import load_dotenv
from datetime import datetime, timedelta
from pymongo import MongoClient, TEXT, DESCENDING

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
    PicklePersistence,
    MessageHandler,
    Filters,
    CallbackQueryHandler,
    ConversationHandler
)

load_dotenv()

DEVELOPER_CHAT_ID = int(os.environ.get('DEVELOPER_CHAT_ID'))
MONGO_DB = os.environ.get('MONGO_DB')
MONGO_URL = os.environ.get('MONGO_URL')
SUPER_ADMIN = os.environ.get('SUPER_ADMIN')
TELEGRAM_URL = os.environ.get('TELEGRAM_URL')
TOKEN = os.environ.get('TOKEN')
PORT = int(os.environ.get('PORT', 5000))
POSTED_MSG = os.environ.get('POSTED_MSG')

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

settings.init()
OPTIONS, TASKS, VERIFY, CONTACT = [el for el in settings.user_menu]
ADMIN, ADMIN_TASKS, ADMIN_VERIFY = [el for el in settings.admin_menu]
ONE, TWO, THREE, FOUR = range(4)



def parse_db(context):
    return context.user_data.setdefault("user_data", {})
    
def start(update, context):
    """Inform user about what this bot can do"""

    username = update.message.from_user.username

    # Create / Get db from mongodb
    user_coll, max_pt = util.get_user_collection(username, get_points=True)

    message = f"Welcome {username}! What would you like to do today?\nTotal Points: {max_pt}"

    # Show list of things that can be done
    keyboard = [
        [InlineKeyboardButton(f"Complete a task", callback_data=str(ONE))], 
        [InlineKeyboardButton(f"Contact Dev", callback_data=str(TWO))],
        ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text(text=message, reply_markup=reply_markup)
    return OPTIONS


def tasks(update,context):

    query = update.callback_query

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    if query:
        query.answer()
    keyboard = []

    if parse_db(context):
        tasks_completed = parse_db(context)["tasks_completed"]

        if len(tasks_completed) == len(settings.task_list):
            if query:
                all_tasks_completed = "Congratulations! You've completed all tasks!\nThanks for participating! :)"
                query.edit_message_text(text=all_tasks_completed)
            else:
                update.message.reply_text(text=all_tasks_completed)
            return ConversationHandler.END
    else:
        tasks_completed = []

    # Get remaining tasks not completed
    tasks_remaining = [d for d in settings.task_list if d['name'] not in tasks_completed]

    # Ensure that the callback_data matches the actual index of the dictionary in task_list via task_list.index(task)
    for task in tasks_remaining:
        keyboard.append([InlineKeyboardButton(f"{task['name']}", callback_data=str(settings.task_list.index(task)))])

    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = "Please choose the task that you have completed."
    if query:
        query.edit_message_text(text=msg, reply_markup=reply_markup)
    else:
        update.message.reply_text(text=msg, reply_markup=reply_markup)

    return TASKS
def get_code(update, context):
    query = update.callback_query

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    query.answer()

    # Get the callback_data and save to tasks
    context.user_data["tasks"] = query.data
    message = f"Please enter the verification code."

    query.edit_message_text(text=message, parse_mode=ParseMode.HTML)
    return VERIFY

def verify_code(update,context):
    # Retrieve data from user's message
    code = update.message.text
    user = update.message.from_user
    username = user.username
    # Retrieve the callback_data that was saved to tasks
    task_idx = int(context.user_data["tasks"])
    task_name = settings.task_list[task_idx]['name']
    isCorrect = False
    # Create / Return the Mongo collection with name = Telegram ID. Get points as well.
    user_collection, max_pt = util.get_user_collection(username, get_points=True)

    if settings.task_list[task_idx]['pw'] == code:
        isCorrect = True
        pts = int(settings.task_list[task_idx]['pts'])
    else:
        message = "Authentication failed. Please do not try to hack the system. :)"

    if isCorrect:
            if parse_db(context):
                parse_db(context)["tasks_completed"].append(task_name)
            else:
                parse_db(context)["username"] = username
                parse_db(context)["tasks_completed"] = [task_name]
                
            max_pt += pts
            message = f"Thanks for playing! You've earned {pts} point(s).\nTotal Points: {max_pt}"

    
    
    # Convert message into a dictionary
    doc = util.get_document_from_message(message)
    # Send dictionary to Mongo collection
    doc_id = user_collection.insert_one(doc)
    if doc_id:
        update.message.reply_text(text=message)
    else:
        message = f"Error saving data. Please try again.\nCurrent Points: {parse_db(context)['points']}"
        update.message.reply_text(text=message, parse_mode=ParseMode.HTML)

    return ConversationHandler.END

def contact_dev(update, context):
    query = update.callback_query

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    query.answer()

    message = f"Experiencing technical difficulties? Type your issue below and we'll get back to you!"

    query.edit_message_text(text=message)
    return CONTACT

def send_to_dev(update, context):
    issue = update.message.text
    username = update.message.from_user.username

    message = f"Message sent! We will be contact you within 3 working days."
    msg_to_dev = f"Issue: {issue}\nReply to: @{username}"

    update.message.reply_text(text=message)
    context.bot.send_message(chat_id=DEVELOPER_CHAT_ID, text=msg_to_dev)
    return ConversationHandler.END

def pm(update, context):
    msg = update.message.text
    username = update.message.from_user.username
    
    user_collection = util.get_user_collection(username)
    doc = util.get_document_from_message(msg)
    doc_id = user_collection.insert_one(doc)
    if doc_id:
        update.message.reply_text(POSTED_MSG)

def cancel(update, context):
    user = update.message.from_user
    logger.info("User %s cancelled the conversation.", user.first_name)
    update.message.reply_text(
        'Bye! I hope we can talk again some day.', reply_markup=ReplyKeyboardRemove()
    )

    return ConversationHandler.END

def help_handler(update, context):
    """Display a help message"""
    help_msg = '''
    /start - Add / Track points
    /cancel - Refresh the bot if the bot does not seem to be working. You will need to enter /start again after /cancel.

    For other issues, please contact the developer from /start
    If you are unable to get the bot to respond via /start, please contact the ROOT member in your respective Telegram groups.
    Thank you!
    '''
    update.message.reply_text(POSTED_MSG)

def error(update, context):
    """Log the error and send a telegram message to notify the developer."""
    # Log the error before we do anything else, so we can see it even if something breaks.
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = ''.join(tb_list)

    # Build the message with some markup and additional information about what happened.
    # You might need to add some logic to deal with messages longer than the 4096 character limit.
    message = (
        'An exception was raised while handling an update\n'
        '<pre>update = {}</pre>\n\n'
        '<pre>context.chat_data = {}</pre>\n\n'
        '<pre>context.user_data = {}</pre>\n\n'
        '<pre>{}</pre>'
    ).format(
        html.escape(json.dumps(update.to_dict(), indent=2, ensure_ascii=False)),
        html.escape(str(context.chat_data)),
        html.escape(str(context.user_data)),
        html.escape(tb_string),
    )

    # Finally, send the message
    context.bot.send_message(chat_id=DEVELOPER_CHAT_ID, text=message, parse_mode=ParseMode.HTML)

def main():
    # Create the EventHandler and pass it your bot's token.
    pp = PicklePersistence(filename='angelsAmongUsBot')
    updater = Updater(TOKEN, persistence=pp, use_context=True)
    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('help', help_handler), 1)
    

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CommandHandler('tasks', tasks)],
        states={
            OPTIONS: [
                CallbackQueryHandler(tasks, pattern='^' + str(ONE) + '$'),
                CallbackQueryHandler(contact_dev, pattern='^' + str(TWO) + '$'),
            ],
            TASKS: [
                CallbackQueryHandler(get_code)
            ],
            VERIFY: [
                MessageHandler(~Filters.command, verify_code),
            ],
            CONTACT: [
                MessageHandler(~Filters.command, send_to_dev),
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel), 
            MessageHandler(Filters.text, pm),
            ],
        name="user_options",
        persistent=True,
    )
    admin_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('admin', admin.admin)],
        states={
            ADMIN: [
                CallbackQueryHandler(admin.stats, pattern='^' + str(ONE) + '$'),
                CallbackQueryHandler(admin.all_users, pattern='^' + str(TWO) + '$'),
                CallbackQueryHandler(admin.all_tasks, pattern='^' + str(THREE) + '$'),
            ],
            ADMIN_TASKS: [
                CallbackQueryHandler(admin.task_action),
            ],
            ADMIN_VERIFY: [
                MessageHandler(~Filters.command, admin.verify_task_action),
                CallbackQueryHandler(admin.confirm_task_action, pattern='^' + str(ONE) + '$'),
                CallbackQueryHandler(admin.confirm_task_action, pattern='^' + str(TWO) + '$'),
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel), 
            MessageHandler(Filters.text, pm),
            ],
    )
    super_admin_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('superadmin', admin.super_admin)],
        states={
            SUPER_ADMIN: [
                MessageHandler(~Filters.command, admin.confirm_super_action),
                CallbackQueryHandler(admin.super_action),
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel), 
            MessageHandler(Filters.text, pm),
            ],
    )
    dp.add_handler(super_admin_conv_handler, 3)
    dp.add_handler(admin_conv_handler, 2)
    dp.add_handler(conv_handler, 1)

    # log all errors
    dp.add_error_handler(error, 1)

    # Start the Bot
    updater.start_webhook(listen="0.0.0.0",
                          port=int(PORT),
                          url_path=TOKEN)
    updater.bot.setWebhook('https://root-tele-seancze.herokuapp.com/' + TOKEN)

    # Run the bot until the you presses Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()