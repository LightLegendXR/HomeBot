from calendar import day_name
from humanize import naturalsize
from re import match
from requests import HTTPError
from sebaubuntu_libs.liblineage.ota import get_nightlies
from sebaubuntu_libs.liblineage.wiki import get_device_data
from shutil import which
from subprocess import check_output
from telegram.ext import CallbackContext
from telegram.parsemode import ParseMode
from telegram.update import Update
from telegram.utils.helpers import escape_markdown
from typing import Callable

def info(update: Update, context: CallbackContext):
	if len(context.args) < 2:
		update.message.reply_text("Device codename not specified")
		return

	device = context.args[1]
	try:
		device_data = get_device_data(device)
	except HTTPError:
		update.message.reply_text("Error: Device not found")
		return

	update.message.reply_text(f"{device_data}", disable_web_page_preview=True)

def last(update: Update, context: CallbackContext):
	if len(context.args) < 2:
		update.message.reply_text("Device codename not specified")
		return

	device = context.args[1]
	response = get_nightlies(device)
	if not response:
		update.message.reply_text(f"Error: no updates found for {device}")
		return

	last_update = response[-1]
	update.message.reply_text(f"Last update for {escape_markdown(device, 2)}:\n"
	                          f"Version: {escape_markdown(last_update.version, 2)}\n"
	                          f"Date: {last_update.datetime.strftime('%Y/%m/%d')}\n"
							  f"Size: {escape_markdown(naturalsize(last_update.size), 2)}\n"
	                          f"Download: [{escape_markdown(last_update.filename, 2)}]({escape_markdown(last_update.url, 2)})",
	                          parse_mode=ParseMode.MARKDOWN_V2)

def when(update: Update, context: CallbackContext):
	if len(context.args) < 2:
		update.message.reply_text("Device codename not specified")
		return

	device = context.args[1]

	if not match('^[a-zA-Z0-9\-_]+$', device):
		update.message.reply_text("Error: Invalid codename")
		return

	try:
		device_data = get_device_data(device)
	except HTTPError:
		update.message.reply_text("Error: Device not found")
		return

	if not device_data.maintainers:
		update.message.reply_text("Error: Device not maintained")
		return

	if which("python2") is None:
		update.message.reply_text("Error: Python 2.x isn't installed, it's required to parse the day")
		return

	command = f'from random import Random; print(Random("{device}").randint(1, 7))'
	day_int = int(check_output(f"python2 -c '{command}'", shell=True))
	day = day_name[day_int - 1]
	update.message.reply_text(f"The next build for {device_data.vendor} {device_data.name} ({device}) will be on {day}")

# name: function
COMMANDS: dict[str, Callable[[Update, CallbackContext], None]] = {
	"info": info,
	"last": last,
	"when": when,
}

HELP_TEXT = (
	"Available commands:\n" +
	"\n".join(COMMANDS.keys())
)

def lineageos(update: Update, context: CallbackContext):
	if not context.args:
		update.message.reply_text(
			"Error: No argument provided\n\n"
			f"{HELP_TEXT}"
		)
		return

	command = context.args[0]

	if command not in COMMANDS:
		update.message.reply_text(
			f"Error: Unknown command {command}\n\n"
			f"{HELP_TEXT}"
		)
		return

	func = COMMANDS[command]

	func(update, context)
