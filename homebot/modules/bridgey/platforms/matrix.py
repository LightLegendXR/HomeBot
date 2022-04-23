from __future__ import annotations
from datetime import datetime
from homebot.core.database import HomeBotDatabase
from homebot.modules.bridgey.platform import PlatformBase
from homebot.modules.bridgey.types.file import File
from homebot.modules.bridgey.types.message import Message, MessageType
from homebot.modules.bridgey.types.user import User
import magic
from matrix_client.client import MatrixClient, MatrixRequestError
from matrix_client.room import Room
import requests
from sebaubuntu_libs.libexception import format_exception
from sebaubuntu_libs.liblogging import LOGE

class MatrixPlatform(PlatformBase):
	NAME = "Matrix"
	ICON_URL = "https://matrix.org/blog/wp-content/uploads/2015/01/logo1.png"
	FILE_TYPE = str
	MESSAGE_TYPE = dict
	USER_TYPE = str

	def __init__(self, pool, instance_name: str, data: dict):
		super().__init__(pool, instance_name, data)

		self.username: str = data["username"]
		self.password: str = data["password"]
		self.homeserver_url: str = data["homeserver_url"]
		self.room_alias: str = data["room_alias"]

		self.client = None
		self.room = None
		self.thread = None

		if HomeBotDatabase.has(f"{self.database_key_prefix}.logged_in"):
			self.client = MatrixClient(self.homeserver_url,
			                           token=HomeBotDatabase.get(f"{self.database_key_prefix}.token"),
			                           user_id=HomeBotDatabase.get(f"{self.database_key_prefix}.user_id"))
			self.client.device_id = HomeBotDatabase.get(f"{self.database_key_prefix}.device_id")
		else:
			self.client = MatrixClient(self.homeserver_url)
			try:
				token = self.client.login(self.username, self.password, sync=False)
			except MatrixRequestError as e:
				LOGE(f"Failed to login: {format_exception(e)}")
				return

			HomeBotDatabase.set(f"{self.database_key_prefix}.token", token)
			HomeBotDatabase.set(f"{self.database_key_prefix}.device_id", self.client.device_id)
			HomeBotDatabase.set(f"{self.database_key_prefix}.user_id", self.client.user_id)
			HomeBotDatabase.set(f"{self.database_key_prefix}.logged_in", True)

		try:
			self.room: Room = self.client.join_room(self.room_alias)
		except MatrixRequestError as e:
			LOGE(f"Failed to join room: {format_exception(e)}")
			return

		self.room.add_listener(self.handle_msg, "m.room.message")
		self.client.start_listener_thread()
		self.thread = self.client.sync_thread

	@property
	def running(self):
		return self.thread and self.thread.is_alive()

	def file_to_generic(self, file: FILE_TYPE) -> Message:
		return File(platform=self,
		            url=self.client.api.get_download_url(file))

	def user_to_generic(self, user: USER_TYPE) -> User:
		avatar_url = self.client.api.get_avatar_url(user)
		return User(platform=self,
		            name=user,
					url=f"https://matrix.to/#/{user}",
		            avatar_url=self.client.api.get_download_url(avatar_url))

	def message_to_generic(self, message: MESSAGE_TYPE) -> Message:
		content = message["content"]
		message_type = MessageType.UNKNOWN
		text = ""
		file = None
		reply_to = None

		if content["msgtype"] == "m.text":
			message_type = MessageType.TEXT
		elif content["msgtype"] == "m.image":
			message_type = MessageType.IMAGE
		elif content["msgtype"] == "m.video":
			message_type = MessageType.VIDEO
		elif content["msgtype"] == "m.audio":
			message_type = MessageType.AUDIO
		elif content["msgtype"] == "m.file":
			message_type = MessageType.DOCUMENT

		if "body" in content:
			text = content["body"]

		user = self.user_to_generic(message["sender"])

		if "url" in content:
			file = self.file_to_generic(content["url"])

		if ("m.relates_to" in content and "m.in_reply_to" in content["m.relates_to"]
		    and "event_id" in content["m.relates_to"]["m.in_reply_to"]):
			in_reply_to = content['m.relates_to']['m.in_reply_to']['event_id']
			reply_to = reply_to = self.get_generic_message_id(in_reply_to)

		return Message(platform=self,
		               message_type=message_type,
		               user=user,
		               timestamp=datetime.now(),
		               text=text,
		               file=file,
					   reply_to=reply_to)

	def handle_msg(self, room: Room, event: dict):
		# Make sure we didn't send this message
		if event['sender'] == self.client.user_id:
			return

		self.on_message(self.message_to_generic(event), event["event_id"])

	def send_message(self, message: Message, message_id: int):
		if not self.running:
			return

		text = f"[{message.platform.NAME}] {message.user}:"
		if message.text:
			text += f"\n{message.text}"

		if message.message_type.is_file():
			try:
				r = requests.get(message.file.url)
			except Exception as e:
				LOGE(f"Failed to download file: {e}")
				return
			try:
				mime_type = magic.from_buffer(r.content, mime=True)
				url = self.client.upload(content=r.content, content_type=mime_type, filename=message.file.name)
			except Exception as e:
				LOGE(f"Failed to upload file: {format_exception(e)}")
				return
		else:
			url = None

		if message.message_type is MessageType.TEXT:
			matrix_message = self.room.send_text(text)
		elif message.message_type is MessageType.IMAGE or message.message_type is MessageType.STICKER:
			matrix_message = self.room.send_image(url, message.file.name, body=text)
		elif message.message_type is MessageType.VIDEO or message.message_type is MessageType.ANIMATION:
			matrix_message = self.room.send_video(url, message.file.name,body=text)
		elif message.message_type is MessageType.AUDIO:
			matrix_message = self.room.send_audio(url, message.file.name, body=text)
		elif message.message_type is MessageType.DOCUMENT:
			matrix_message = self.room.send_file(url, message.file.name, body=text)
		else:
			LOGE(f"Unknown message type: {message.message_type}")
			return

		self.set_platform_message_id(message_id, matrix_message["event_id"])
