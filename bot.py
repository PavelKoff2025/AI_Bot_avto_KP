"""Telegram-канал OfferDesk для менеджера отдела продаж."""

from __future__ import annotations

import asyncio
import tempfile
import zipfile
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    ErrorEvent,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Update,
)
from dotenv import load_dotenv
import os

from utils.combined_document import build_combined_document
from utils.config import (
    DEFAULT_CLIENT_NAME,
    apply_outbound_proxy_env,
    sanitize_client_name,
    telegram_allowed_ids,
)
from utils.kp_generator import BOT_VARIANTS
from utils.logging_setup import get_logger, setup_logging
from utils.package_builder import build_manager_package
from utils.sufficiency import check_transcription_sufficiency, format_sufficiency_message

load_dotenv()
# Подхватить корневой .env, если бот стартует не из корня
load_dotenv(Path(__file__).resolve().parent / ".env")
_proxy = apply_outbound_proxy_env()
setup_logging()
logger = get_logger("bot")
if _proxy:
    logger.info("OpenAI/outbound proxy: %s", _proxy.split("@")[-1])

PROJECT_ROOT = Path(__file__).resolve().parent

# Антидребезг: один тяжёлый job на пользователя
_user_locks: dict[int, asyncio.Lock] = {}


def _lock_for(user_id: int | None) -> asyncio.Lock:
    uid = user_id or 0
    if uid not in _user_locks:
        _user_locks[uid] = asyncio.Lock()
    return _user_locks[uid]


def _is_manager(user_id: int | None) -> bool:
    """Менеджерский функционал (транскрибации) — только TELEGRAM_ALLOWED_IDS."""
    allowed = telegram_allowed_ids()
    if not allowed:
        return False
    return bool(user_id and user_id in allowed)


def _is_allowed(user_id: int | None) -> bool:
    """Совместимость: доступ к менеджерским хендлерам."""
    return _is_manager(user_id)


CLIENT_HELLO = (
    "Здравствуйте! Это бот «Дом Мастер» для получения коммерческого предложения.\n\n"
    "Чтобы привязать Telegram к сделке, откройте персональную ссылку от менеджера "
    "(вид <code>t.me/…?start=deal_N</code>) и нажмите «Старт».\n\n"
    "После привязки КП придёт сюда автоматически.\n"
    "Ваш ID: команда /myid"
)


async def _deny_if_forbidden(message_or_cb: Message | CallbackQuery) -> bool:
    """True = доступ запрещён (уже ответили пользователю)."""
    user = message_or_cb.from_user
    uid = user.id if user else None
    if _is_manager(uid):
        return False
    logger.warning("[%s] отказ: пользователь не в TELEGRAM_ALLOWED_IDS", _user_tag(message_or_cb))
    text = CLIENT_HELLO
    try:
        if isinstance(message_or_cb, CallbackQuery):
            await message_or_cb.answer("Доступ только по ссылке из CRM", show_alert=True)
            if message_or_cb.message:
                await message_or_cb.message.answer(text, parse_mode="HTML")
        else:
            await message_or_cb.answer(text, parse_mode="HTML")
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось отправить отказ в доступе")
    return True


def _client_name_from_state(data: dict) -> str:
    sufficiency = data.get("sufficiency") or {}
    if isinstance(sufficiency, dict):
        return sanitize_client_name(sufficiency.get("client_name"))
    return sanitize_client_name(data.get("client_name"), fallback=DEFAULT_CLIENT_NAME)


def _user_facing_error(prefix: str = "Не удалось выполнить операцию") -> str:
    return f"{prefix}. Подробности в логе сервера."


class Flow(StatesGroup):
    waiting_transcription = State()
    choose_variant = State()
    choose_ar = State()
    choose_ir = State()
    ready_actions = State()


def _user_tag(message_or_cb: Message | CallbackQuery) -> str:
    user = message_or_cb.from_user
    if not user:
        return "user=?"
    return f"user_id={user.id} (@{user.username or '—'})"


def kb_variants() -> InlineKeyboardMarkup:
    rows = []
    for key, meta in BOT_VARIANTS.items():
        rows.append([
            InlineKeyboardButton(
                text=f"{meta['title']} — {meta['description']}",
                callback_data=f"var:{key}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_yes_no(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да", callback_data=f"{prefix}:yes"),
                InlineKeyboardButton(text="Нет", callback_data=f"{prefix}:no"),
            ]
        ]
    )


def kb_delivery() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📥 Скачать файлы", callback_data="act:download")],
            [InlineKeyboardButton(
                text="📄 Собрать все в один документ",
                callback_data="act:combine",
            )],
            [InlineKeyboardButton(text="✉️ Отправить на e-mail", callback_data="act:email")],
            [InlineKeyboardButton(text="🔄 Новый звонок", callback_data="act:restart")],
        ]
    )


def kb_after_combine() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🗜 Заархивировать финальное КП (ZIP)",
                callback_data="act:zip",
            )],
            [InlineKeyboardButton(
                text="📥 Скачать единый PDF ещё раз",
                callback_data="act:download_combined",
            )],
            [InlineKeyboardButton(
                text="✉️ Отправить на e-mail",
                callback_data="act:email",
            )],
            [InlineKeyboardButton(text="🔄 Новый звонок", callback_data="act:restart")],
        ]
    )


def kb_email_prep() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🗜 Сначала ZIP, потом e-mail",
                callback_data="act:zip_then_email",
            )],
            [InlineKeyboardButton(
                text="✉️ E-mail без архива (позже)",
                callback_data="act:email_stub",
            )],
            [InlineKeyboardButton(text="« Назад", callback_data="act:back_final")],
        ]
    )


def make_final_zip(combined_pdf: Path, extra_files: list[Path] | None = None) -> Path:
    zip_path = combined_pdf.with_name(combined_pdf.stem + "_FINAL.zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(combined_pdf, arcname=combined_pdf.name)
        html = combined_pdf.with_suffix(".html")
        summary_html = combined_pdf.parent / "00_summary_costs.html"
        for optional in (html, summary_html):
            if optional.exists() and optional.resolve() != combined_pdf.resolve():
                zf.write(optional, arcname=optional.name)
        for path in extra_files or []:
            if path.exists() and path.resolve() != combined_pdf.resolve():
                zf.write(path, arcname=path.name)
    return zip_path.resolve()


async def notify_error(target: Message | CallbackQuery, text: str) -> None:
    """Сообщение об ошибке пользователю (единый стиль)."""
    msg = f"⚠️ {text}\nПопробуйте ещё раз или /start."
    try:
        if isinstance(target, CallbackQuery):
            if target.message:
                await target.message.answer(msg)
            else:
                await target.answer(text[:180], show_alert=True)
        else:
            await target.answer(msg)
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось отправить сообщение об ошибке пользователю")


async def cmd_start(message: Message, state: FSMContext, command: CommandObject) -> None:
    """
    /start — менеджер (только TELEGRAM_ALLOWED_IDS).
    /start deal_123 — клиент привязывает chat_id к сделке (без allowlist).
    Обычный /start у клиента — короткое клиентское приветствие (не промпт про .txt).
    """
    args = (command.args or "").strip()
    if args.lower().startswith("deal_"):
        await _bind_client_from_start(message, args)
        return

    user = message.from_user
    if not _is_manager(user.id if user else None):
        logger.info("[%s] /start — клиентское приветствие", _user_tag(message))
        await state.clear()
        await message.answer(CLIENT_HELLO, parse_mode="HTML")
        return

    logger.info("[%s] /start — новая сессия менеджера", _user_tag(message))
    await state.clear()
    await state.set_state(Flow.waiting_transcription)
    await message.answer(
        "Привет! Это <b>OfferDesk</b> — рабочее место ОП «Дом-Мастер».\n\n"
        "Пришлите <b>.txt</b> с транскрибацией звонка (документом) "
        "или вставьте текст сообщением.\n\n"
        "Сверю данные с эталоном и скажу, хватает ли информации для КП.\n\n"
        "Клиенту для привязки сделки отправьте ссылку из CRM "
        "(кнопка «Привязать Telegram»).",
        parse_mode="HTML",
    )


async def _bind_client_from_start(message: Message, args: str) -> None:
    """Deep-link start=deal_<id> — сохраняет chat_id в deals.telegram_chat_id."""
    from utils.crm_telegram import bind_telegram_to_deal, bind_telegram_via_crm_api

    raw_id = args.split("_", 1)[-1].strip()
    if not raw_id.isdigit():
        await message.answer(
            "Некорректная ссылка привязки. Попросите менеджера прислать новую из CRM."
        )
        return
    deal_id = int(raw_id)
    user = message.from_user
    if not user:
        await message.answer("Не удалось определить ваш Telegram ID.")
        return

    info = None
    errors: list[str] = []
    crm_url = os.getenv("CRM_PUBLIC_URL", "").strip()

    # При CRM_PUBLIC_URL — пишем в прод-CRM (бот может крутиться локально)
    if crm_url:
        try:
            remote = bind_telegram_via_crm_api(
                deal_id,
                chat_id=user.id,
                username=user.username,
            )
            info = {
                "deal_id": deal_id,
                "client_name": remote.get("client_name") or "Клиент",
                "chat_id": str(user.id),
                "username": user.username,
            }
        except Exception as exc:  # noqa: BLE001
            errors.append(f"crm: {exc}")
            logger.warning("remote bind deal_%s failed: %s", deal_id, exc)
    else:
        try:
            info = bind_telegram_to_deal(
                deal_id,
                chat_id=user.id,
                username=user.username,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"local: {exc}")
            logger.warning("local bind deal_%s failed: %s", deal_id, exc)

    if not info:
        logger.error("bind deal_%s failed for %s: %s", deal_id, _user_tag(message), errors)
        await message.answer(
            "Не удалось привязать Telegram к сделке.\n"
            "Напишите менеджеру свой ID из /myid или попробуйте ссылку позже."
        )
        return

    logger.info(
        "[%s] привязан к сделке #%s (%s)",
        _user_tag(message),
        deal_id,
        info.get("client_name"),
    )
    await message.answer(
        f"✅ Готово!\n\n"
        f"Ваш Telegram привязан к сделке <b>№{deal_id}</b> "
        f"({info.get('client_name')}).\n"
        f"ID: <code>{user.id}</code>\n\n"
        f"Менеджер «Дом-Мастер» сможет отправить вам коммерческое предложение сюда.",
        parse_mode="HTML",
    )


async def cmd_myid(message: Message) -> None:
    """Любой пользователь может узнать свой chat_id."""
    user = message.from_user
    if not user:
        return
    uname = f"@{user.username}" if user.username else "—"
    await message.answer(
        f"Ваш Telegram ID: <code>{user.id}</code>\nUsername: {uname}\n\n"
        f"Передайте ID менеджеру или откройте персональную ссылку привязки из CRM.",
        parse_mode="HTML",
    )


async def cmd_help(message: Message) -> None:
    if await _deny_if_forbidden(message):
        return
    logger.info("[%s] /help", _user_tag(message))
    await message.answer(
        "/start — начать заново\n"
        "/help — справка\n"
        "/myid — показать ваш Telegram ID\n\n"
        "Клиент: откройте ссылку из CRM вида t.me/…?start=deal_N — "
        "так привяжется chat_id для отправки КП.\n\n"
        "Варианты КП:\n"
        "• Базовый — газобетон\n"
        "• Средний + — газобетон усиленный\n"
        "• Средний (оптимальный) — клееный брус\n\n"
        "К КП можно приложить АР (проект дома) и ИР (инженерка).",
    )


async def _read_txt_document(message: Message, bot: Bot) -> str | None:
    doc = message.document
    if not doc:
        return None
    name = (doc.file_name or "").lower()
    if not name.endswith(".txt"):
        logger.warning("[%s] отклонён файл не .txt: %s", _user_tag(message), doc.file_name)
        await message.answer("Нужен файл с расширением .txt")
        return None
    if doc.file_size and doc.file_size > 2_000_000:
        logger.warning("[%s] файл слишком большой: %s bytes", _user_tag(message), doc.file_size)
        await message.answer("Файл слишком большой (лимит 2 МБ).")
        return None

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        await bot.download(doc, destination=tmp_path)
        text = tmp_path.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:  # noqa: BLE001
        logger.exception("[%s] ошибка скачивания/чтения .txt", _user_tag(message))
        await message.answer("Не удалось прочитать файл. Пришлите другой .txt.")
        return None
    finally:
        tmp_path.unlink(missing_ok=True)

    if not text:
        logger.warning("[%s] пустой .txt", _user_tag(message))
        await message.answer("Файл пуст.")
        return None

    logger.info(
        "[%s] получен .txt «%s», длина=%s символов",
        _user_tag(message),
        doc.file_name,
        len(text),
    )
    return text


async def handle_transcription(message: Message, state: FSMContext, bot: Bot) -> None:
    if await _deny_if_forbidden(message):
        return

    text: str | None = None
    if message.document:
        text = await _read_txt_document(message, bot)
        if text is None:
            return
    elif message.text and not message.text.startswith("/"):
        text = message.text.strip()
        logger.info("[%s] получена текстовая транскрибация, длина=%s", _user_tag(message), len(text))
    else:
        await message.answer("Пришлите .txt документ или текст транскрибации.")
        return

    wait = await message.answer("Анализирую транскрибацию по эталону…")
    logger.info("[%s] этап: проверка достаточности данных (LLM)", _user_tag(message))
    try:
        result = await asyncio.to_thread(check_transcription_sufficiency, text)
    except Exception:  # noqa: BLE001
        logger.exception("[%s] ошибка анализа достаточности", _user_tag(message))
        await wait.edit_text(_user_facing_error("Ошибка анализа транскрибации"))
        return

    client_name = sanitize_client_name(result.get("client_name"))
    await state.update_data(
        transcription=text,
        sufficiency=result,
        client_name=client_name,
    )
    logger.info(
        "[%s] результат проверки: can_form_kp=%s score=%s client=%s",
        _user_tag(message),
        result.get("can_form_kp"),
        result.get("score"),
        client_name,
    )
    await wait.edit_text(format_sufficiency_message(result), parse_mode="HTML")

    if not result["can_form_kp"]:
        logger.info("[%s] данных недостаточно — ждём дополненную транскрибацию", _user_tag(message))
        await state.set_state(Flow.waiting_transcription)
        return

    await state.set_state(Flow.choose_variant)
    logger.info("[%s] этап: выбор варианта КП", _user_tag(message))
    await message.answer(
        f"Заказчик: <b>{client_name}</b>\nВыберите вариант КП:",
        parse_mode="HTML",
        reply_markup=kb_variants(),
    )


async def on_variant(callback: CallbackQuery, state: FSMContext) -> None:
    if await _deny_if_forbidden(callback):
        return
    key = (callback.data or "").split(":", 1)[-1]
    if key not in BOT_VARIANTS:
        logger.warning("[%s] неизвестный вариант КП: %s", _user_tag(callback), key)
        await callback.answer("Неизвестный вариант", show_alert=True)
        return
    await state.update_data(variant_key=key)
    await state.set_state(Flow.choose_ar)
    meta = BOT_VARIANTS[key]
    logger.info("[%s] выбран вариант КП: %s (%s)", _user_tag(callback), key, meta["title"])
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"Выбрано: <b>{meta['title']}</b>\n{meta['description']}\n\n"
        "Приложить к КП <b>проект дома (АР)</b> — визуализация и план помещений?",
        parse_mode="HTML",
        reply_markup=kb_yes_no("ar"),
    )
    await callback.answer()


async def on_ar(callback: CallbackQuery, state: FSMContext) -> None:
    if await _deny_if_forbidden(callback):
        return
    with_ar = (callback.data or "").endswith(":yes")
    await state.update_data(with_ar=with_ar)
    await state.set_state(Flow.choose_ir)
    logger.info("[%s] АР: %s", _user_tag(callback), with_ar)
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"АР: <b>{'да' if with_ar else 'нет'}</b>\n\n"
        "Приложить <b>проект инженерных решений (ИР)</b> "
        "(водоснабжение, канализация, отопление, тёплые полы, вентиляция + смета)?",
        parse_mode="HTML",
        reply_markup=kb_yes_no("ir"),
    )
    await callback.answer()


async def on_ir(callback: CallbackQuery, state: FSMContext) -> None:
    if await _deny_if_forbidden(callback):
        return
    with_ir = (callback.data or "").endswith(":yes")
    await state.update_data(with_engineering=with_ir)
    data = await state.get_data()
    variant_key = data.get("variant_key")
    if not variant_key or variant_key not in BOT_VARIANTS:
        logger.warning("[%s] нет variant_key в FSM — сброс", _user_tag(callback))
        await callback.answer("Сессия устарела", show_alert=True)
        await state.clear()
        await state.set_state(Flow.waiting_transcription)
        await notify_error(callback, "Сессия устарела. Пришлите транскрибацию заново")
        return

    transcription = data.get("transcription")
    if not transcription:
        await callback.answer("Нет транскрибации", show_alert=True)
        await notify_error(callback, "Нет транскрибации в сессии")
        await state.set_state(Flow.waiting_transcription)
        return

    meta = BOT_VARIANTS[variant_key]
    client_name = _client_name_from_state(data)
    user_id = callback.from_user.id if callback.from_user else None
    lock = _lock_for(user_id)

    if lock.locked():
        await callback.answer("Уже выполняется сборка, подождите…", show_alert=True)
        return

    logger.info(
        "[%s] этап: сборка пакета variant=%s ar=%s ir=%s client=%s",
        _user_tag(callback),
        variant_key,
        data.get("with_ar"),
        with_ir,
        client_name,
    )

    await callback.message.edit_text(  # type: ignore[union-attr]
        "Собираю пакет документов…\n"
        f"• Заказчик: {client_name}\n"
        f"• КП: {meta['title']}\n"
        f"• АР: {'да' if data.get('with_ar') else 'нет'}\n"
        f"• ИР: {'да' if with_ir else 'нет'}\n\n"
        "Это может занять 1–3 минуты (особенно с АР).",
        parse_mode="HTML",
    )
    await callback.answer()

    async with lock:
        try:
            package = await asyncio.to_thread(
                build_manager_package,
                transcription,
                variant_key,
                with_ar=bool(data.get("with_ar")),
                with_engineering=with_ir,
                include_fz=False,
                client_name=client_name,
            )
        except Exception:  # noqa: BLE001
            logger.exception("[%s] ошибка сборки пакета", _user_tag(callback))
            await notify_error(callback, _user_facing_error("Ошибка формирования пакета"))
            await state.set_state(Flow.waiting_transcription)
            return

    await state.update_data(
        package_files=[str(p) for p in package["files"]],
        kp_path=str(package["kp"]),
        ar_path=str(package["ar"]) if package.get("ar") else None,
        engineering_path=str(package["engineering"]) if package.get("engineering") else None,
        client_name=package.get("client_name") or client_name,
    )
    await state.set_state(Flow.ready_actions)
    logger.info(
        "[%s] пакет готов: files=%s",
        _user_tag(callback),
        [Path(p).name for p in package["files"]],
    )

    file_list = "\n".join(f"• {Path(p).name}" for p in package["files"])
    await callback.message.answer(  # type: ignore[union-attr]
        f"✅ Пакет готов: <b>{package['variant_title']}</b>\n"
        f"Заказчик: <b>{package.get('client_name') or client_name}</b>\n\n"
        f"{file_list}\n\n"
        "Что сделать дальше?",
        parse_mode="HTML",
        reply_markup=kb_delivery(),
    )


async def _send_package_files(message: Message, files: list[str]) -> None:
    sent = 0
    for path_str in files:
        path = Path(path_str)
        if not path.exists() or path.suffix.lower() != ".pdf":
            logger.warning("Пропуск файла при отправке: %s", path_str)
            continue
        await message.answer_document(
            FSInputFile(path, filename=path.name),
            caption=path.name,
        )
        sent += 1
    logger.info("Отправлено PDF в чат: %s", sent)


async def on_action(callback: CallbackQuery, state: FSMContext) -> None:
    if await _deny_if_forbidden(callback):
        return
    action = (callback.data or "").split(":", 1)[-1]
    data = await state.get_data()
    files = data.get("package_files") or []
    logger.info("[%s] действие: %s", _user_tag(callback), action)
    user_id = callback.from_user.id if callback.from_user else None
    lock = _lock_for(user_id)

    if action == "download":
        await callback.answer("Отправляю файлы…")
        if not files:
            await callback.message.answer("Файлы не найдены. Начните /start")  # type: ignore[union-attr]
            return
        try:
            await _send_package_files(callback.message, files)  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001
            logger.exception("[%s] ошибка отправки файлов", _user_tag(callback))
            await notify_error(callback, _user_facing_error("Не удалось отправить файлы"))
            return
        await callback.message.answer(  # type: ignore[union-attr]
            "Файлы отправлены. Можно скачать их в чат.",
            reply_markup=kb_delivery(),
        )
        return

    if action == "combine":
        await callback.answer()
        transcription = data.get("transcription")
        if not transcription:
            await callback.message.answer(  # type: ignore[union-attr]
                "Нет транскрибации в сессии. Начните /start"
            )
            return

        if lock.locked():
            await callback.message.answer(  # type: ignore[union-attr]
                "Уже выполняется сборка документов. Подождите…"
            )
            return

        client_name = _client_name_from_state(data)
        logger.info(
            "[%s] этап: сборка единого PDF (3 КП + смета), client=%s",
            _user_tag(callback),
            client_name,
        )
        wait = await callback.message.answer(  # type: ignore[union-attr]
            "Собираю единый PDF: сводная стоимость + все 3 КП"
            + (" + АР" if data.get("with_ar") else "")
            + (" + ИР" if data.get("with_engineering") else "")
            + "…\nЭто может занять несколько минут."
        )
        async with lock:
            try:
                combined = await asyncio.to_thread(
                    build_combined_document,
                    transcription,
                    with_ar=bool(data.get("with_ar")),
                    with_engineering=bool(data.get("with_engineering")),
                    include_fz=False,
                    client_name=client_name,
                    existing_ar=data.get("ar_path"),
                    existing_engineering=data.get("engineering_path"),
                )
            except Exception:  # noqa: BLE001
                logger.exception("[%s] ошибка combine", _user_tag(callback))
                await wait.edit_text(_user_facing_error("Ошибка сборки документа"))
                return

        combined_pdf = Path(combined["combined_pdf"])
        await state.update_data(combined_pdf=str(combined_pdf))
        logger.info(
            "[%s] единый PDF готов: %s (%s bytes)",
            _user_tag(callback),
            combined_pdf.name,
            combined_pdf.stat().st_size,
        )

        lines = [
            f"<b>Заказчик:</b> {client_name}",
            "<b>Стоимость по выбранным опциям:</b>",
        ]
        for row in combined["summary"]["rows"]:
            parts = [f"контур {row['contour_fmt']} ₽"]
            if data.get("with_ar"):
                parts.append(f"АР {row['ar_fmt']} ₽")
            if data.get("with_engineering"):
                parts.append(f"ИР {row['ir_fmt']} ₽")
            lines.append(
                f"• {row['title']}: {' + '.join(parts)} = <b>{row['total_fmt']} ₽</b>"
            )
        await wait.edit_text("\n".join(lines), parse_mode="HTML")

        await callback.message.answer_document(  # type: ignore[union-attr]
            FSInputFile(combined_pdf, filename=combined_pdf.name),
            caption=(
                "Единый документ готов (сводная смета + 3 КП"
                + (" + АР" if combined.get("ar") else "")
                + (" + ИР" if combined.get("engineering") else "")
                + ").\n\n"
                "Перед отправкой клиенту по e-mail удобно сделать ZIP-архив."
            ),
            reply_markup=kb_after_combine(),
        )
        return

    if action == "download_combined":
        await callback.answer()
        combined_path = data.get("combined_pdf")
        if not combined_path or not Path(combined_path).exists():
            await callback.message.answer(  # type: ignore[union-attr]
                "Сводный PDF ещё не собран. Нажмите «Собрать все в один документ».",
                reply_markup=kb_delivery(),
            )
            return
        path = Path(combined_path)
        logger.info("[%s] повторная отправка combined PDF", _user_tag(callback))
        await callback.message.answer_document(  # type: ignore[union-attr]
            FSInputFile(path, filename=path.name),
            caption="Единый PDF с полным пакетом КП",
            reply_markup=kb_after_combine(),
        )
        return

    if action in {"zip", "zip_then_email"}:
        await callback.answer("Создаю ZIP…")
        combined_path = data.get("combined_pdf")
        if not combined_path or not Path(combined_path).exists():
            await callback.message.answer(  # type: ignore[union-attr]
                "Сначала соберите единый документ («Собрать все в один документ»).",
                reply_markup=kb_delivery(),
            )
            return

        logger.info("[%s] этап: ZIP финального КП", _user_tag(callback))
        try:
            zip_path = await asyncio.to_thread(make_final_zip, Path(combined_path))
        except Exception:  # noqa: BLE001
            logger.exception("[%s] ошибка ZIP", _user_tag(callback))
            await notify_error(callback, _user_facing_error("Ошибка ZIP"))
            return

        await state.update_data(combined_zip=str(zip_path))
        size_mb = zip_path.stat().st_size / (1024 * 1024)
        logger.info("[%s] ZIP готов: %s (%.1f МБ)", _user_tag(callback), zip_path.name, size_mb)
        await callback.message.answer_document(  # type: ignore[union-attr]
            FSInputFile(zip_path, filename=zip_path.name),
            caption=(
                f"🗜 Архив финального КП готов ({size_mb:.1f} МБ).\n"
                "Удобно прикреплять к письму клиенту."
            ),
            reply_markup=kb_after_combine(),
        )
        if action == "zip_then_email":
            logger.info("[%s] e-mail stub после ZIP", _user_tag(callback))
            await callback.message.answer(  # type: ignore[union-attr]
                "✉️ Отправка на e-mail будет автоматизирована позже.\n"
                "Сейчас ZIP уже в чате — перешлите его клиенту вручную "
                "или сохраните для вложения в почтовый клиент.",
                reply_markup=kb_after_combine(),
            )
        return

    if action == "email":
        await callback.answer()
        logger.info("[%s] запрос e-mail (stub)", _user_tag(callback))
        if data.get("combined_pdf"):
            await callback.message.answer(  # type: ignore[union-attr]
                "Перед отправкой по e-mail рекомендуем заархивировать финальный документ.\n"
                "Так письмо не раздувается и клиенту проще скачать пакет.",
                reply_markup=kb_email_prep(),
            )
        else:
            await callback.message.answer(  # type: ignore[union-attr]
                "✉️ Отправка на e-mail будет автоматизирована позже.\n"
                "Сначала соберите единый документ, затем сделайте ZIP.",
                reply_markup=kb_delivery(),
            )
        return

    if action == "email_stub":
        await callback.answer()
        logger.info("[%s] e-mail stub без ZIP", _user_tag(callback))
        await callback.message.answer(  # type: ignore[union-attr]
            "✉️ Автоотправка e-mail появится позже.\n"
            "Используйте ZIP из чата как вложение в письмо клиенту.",
            reply_markup=kb_after_combine() if data.get("combined_pdf") else kb_delivery(),
        )
        return

    if action == "back_final":
        await callback.answer()
        markup = kb_after_combine() if data.get("combined_pdf") else kb_delivery()
        await callback.message.answer(  # type: ignore[union-attr]
            "Что сделаем дальше?",
            reply_markup=markup,
        )
        return

    if action == "restart":
        await callback.answer()
        logger.info("[%s] сессия сброшена (/restart)", _user_tag(callback))
        await state.clear()
        await state.set_state(Flow.waiting_transcription)
        await callback.message.answer(  # type: ignore[union-attr]
            "Ок. Пришлите новую транскрибацию (.txt или текстом)."
        )
        return

    await callback.answer("Неизвестное действие", show_alert=True)


async def on_stale_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Устаревшие кнопки после /start или рестарта процесса."""
    if await _deny_if_forbidden(callback):
        return
    logger.info("[%s] устаревший callback: %s", _user_tag(callback), callback.data)
    await callback.answer("Сессия устарела — нажмите /start", show_alert=True)
    current = await state.get_state()
    if current is None:
        await state.set_state(Flow.waiting_transcription)
    if callback.message:
        await callback.message.answer(
            "Эта кнопка больше не действует. Нажмите /start и пришлите транскрибацию."
        )


async def on_global_error(event: ErrorEvent) -> None:
    """Единый перехват необработанных ошибок aiogram."""
    update: Update | None = event.update
    exc = event.exception
    logger.exception("Необработанная ошибка бота: %s | update=%s", exc, update)

    try:
        if update and update.callback_query and update.callback_query.message:
            await update.callback_query.message.answer(
                "⚠️ Внутренняя ошибка. Мы записали её в лог. Нажмите /start."
            )
        elif update and update.message:
            await update.message.answer(
                "⚠️ Внутренняя ошибка. Мы записали её в лог. Нажмите /start."
            )
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось уведомить пользователя о глобальной ошибке")


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.errors.register(on_global_error)
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_help, Command("help"))
    dp.message.register(cmd_myid, Command("myid"))
    dp.message.register(
        handle_transcription,
        Flow.waiting_transcription,
        F.document | F.text,
    )
    dp.callback_query.register(on_variant, Flow.choose_variant, F.data.startswith("var:"))
    dp.callback_query.register(on_ar, Flow.choose_ar, F.data.startswith("ar:"))
    dp.callback_query.register(on_ir, Flow.choose_ir, F.data.startswith("ir:"))
    dp.callback_query.register(on_action, Flow.ready_actions, F.data.startswith("act:"))
    dp.callback_query.register(on_stale_callback)
    return dp


async def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or token == "your_telegram_bot_token_here":
        logger.error("TELEGRAM_BOT_TOKEN не задан в .env")
        raise SystemExit(
            "Укажите TELEGRAM_BOT_TOKEN в .env (токен от @BotFather)"
        )

    allowed = telegram_allowed_ids()
    if allowed:
        logger.info("Allowlist Telegram (менеджеры): %s id(s)", len(allowed))
    else:
        logger.warning(
            "TELEGRAM_ALLOWED_IDS пуст — менеджерский режим выключен. "
            "Клиенты видят короткое приветствие; укажите id менеджеров в .env"
        )

    bot = Bot(token=token)
    dp = build_dispatcher()
    if os.getenv("CRM_PUBLIC_URL", "").strip():
        from utils.telegram_outbox import outbox_loop

        asyncio.create_task(outbox_loop(bot))
        logger.info("CRM_PUBLIC_URL=%s — remote bind + outbox worker", os.getenv("CRM_PUBLIC_URL"))
    logger.info("Бот запущен (polling). Логи: logs/bot.log")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())