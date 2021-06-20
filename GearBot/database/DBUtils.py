from discord import MessageType
from tortoise import Tortoise
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from database.DatabaseConnector import LoggedMessage, LoggedAttachment

async def insert_message(message):
    try:
        message_type = message.type

        if message_type == MessageType.default:
            message_type = None
        else:
            if not isinstance(message_type, int):
                message_type = message_type.value
        is_reply = message.reference is not None and message.reference.channel_id == message.channel.id
        logged = await LoggedMessage.create(messageid=message.id, content=message.content.replace('\x00', ''),
                                    author=message.author.id,
                                    channel=message.channel.id, server=message.guild.id,
                                    type=message_type, pinned=message.pinned,
                                            reply_to=message.reference.message_id if is_reply else None)
        for a in message.attachments:
            await LoggedAttachment.create(id=a.id, name=a.filename,
                                       isImage=(a.width is not None or a.width == 0),
                                       message=logged)
    except IntegrityError:
        return message
    return logged
