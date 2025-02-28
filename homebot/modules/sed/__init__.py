"""HomeBot sed module."""

from homebot.core.mdlintf import ModuleInterface, mdlbinder
from telegram.ext import MessageHandler
from telegram.ext.filters import Filters

from homebot.modules.sed.main import (
	sed_handler,
)

class SedModule(ModuleInterface):
	name = "sed"
	version = "1.0"
	handlers = [
		MessageHandler(Filters.update.message, sed_handler, run_async=True),
	]

mdlbinder.register_interface(SedModule())
