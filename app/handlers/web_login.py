from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import get_settings
from app.services import web_login

router = Router(name="web_login")


@router.message(F.chat.type == "private", CommandStart(deep_link=True, magic=F.args.startswith("login_")))
async def login_request(message: Message, command: CommandObject, login_redis):
    if get_settings().role(message.from_user.id) not in {"sensi", "admin_team"}:
        await message.answer("این حساب اجازهٔ ورود به پنل مدیریت را ندارد.")
        return
    challenge = (command.args or "")[6:]
    data = await web_login.pending(login_redis, challenge)
    if not data or data.get("telegram_id") or data.get("denied"):
        await message.answer("این درخواست ورود منقضی شده یا استفاده شده است. از پنل دوباره تلاش کن.")
        return
    await message.answer(
        f"🔐 تأیید ورود به پنل سنسی\n\nکد تطبیق: {data['code']}\n\n"
        "فقط اگر خودت در مرورگر درخواست ورود دادی و همین کد را می‌بینی، تأیید کن. "
        "لینکی که شخص دیگری فرستاده را تأیید نکن.\nاین درخواست حداکثر ۳ دقیقه اعتبار دارد.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="تأیید ورود", callback_data=f"web_login:yes:{challenge}"),
            InlineKeyboardButton(text="رد درخواست", callback_data=f"web_login:no:{challenge}"),
        ]]),
    )


@router.callback_query(F.data.startswith("web_login:"))
async def login_decision(callback: CallbackQuery, login_redis):
    parts = (callback.data or "").split(":")
    if not callback.message or callback.message.chat.type != "private" or len(parts) != 3 or parts[1] not in {"yes", "no"}:
        await callback.answer("درخواست نامعتبر است.", show_alert=True)
        return
    denied = parts[1] == "no"
    accepted = await web_login.approve(login_redis, parts[2], callback.from_user.id, denied=denied)
    if not accepted:
        await callback.answer("درخواست منقضی شده یا اجازهٔ ورود نداری.", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text("درخواست ورود رد شد." if denied else "✅ ورود تأیید شد. به همان مرورگر یا اپ پنل برگرد؛ ورود خودکار انجام می‌شود.")
