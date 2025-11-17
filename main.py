import os
import logging
import sqlite3
from datetime import datetime, timedelta, time
import io
import asyncio
from threading import Lock
from enum import Enum
import sys

import pandas as pd

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup,
    KeyboardButton, InputFile, Message, CallbackQuery
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes,
    MessageHandler, filters, ConversationHandler
)
from telegram.error import TimedOut, NetworkError, RetryAfter


# --- Load .env manually ---
def load_env_file(path: str = ".env"):
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k not in os.environ:
                os.environ[k] = v


load_env_file(".env")

# ---------- CONFIG ----------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Admin IDs (employers)
admin_ids_set = set()
if os.environ.get("ADMIN_IDS"):
    for part in os.environ.get("ADMIN_IDS").split(","):
        try:
            admin_ids_set.add(int(part.strip()))
        except:
            pass

DB_PATH = os.environ.get("DB_PATH", "jobs_bot.db")

# Локализация
LANGUAGES = {
    'ru': 'Русский',
    'en': 'English',
    'kk': 'Қазақша'
}

TEXTS = {
    'start': {
        'ru': "👋 Добро пожаловать в сервис поиска вакансий для студентов!\n\nЗдесь вы можете найти подходящие стажировки и подать заявки.",
        'en': "👋 Welcome to the student job search service!\n\nHere you can find suitable internships and apply.",
        'kk': "👋 Студенттерге арналған жұмыс іздеу қызметіне қош келдіңіз!\n\nМұнда сіз сәйкес стажировкаларды тауып, өтініш бере аласыз."
    },
    'start_employer': {
        'ru': "👔 Панель работодателя",
        'en': "👔 Employer panel",
        'kk': "👔 Жұмыс беруші панелі"
    },
    'start_student': {
        'ru': "🎓 Панель студента",
        'en': "🎓 Student panel",
        'kk': "🎓 Студент панелі"
    },
    'choose_language': {
        'ru': "🌍 Выберите язык:",
        'en': "🌍 Choose your language:",
        'kk': "🌍 Тіліңізді таңдаңыз:"
    },
    'main_menu': {
        'ru': "📋 Главное меню",
        'en': "📋 Main menu",
        'kk': "📋 Негізгі мәзір"
    },
    'back': {
        'ru': "⬅️ Назад",
        'en': "⬅️ Back",
        'kk': "⬅️ Артқа"
    },
    'cancel': {
        'ru': "❌ Отмена",
        'en': "❌ Cancel",
        'kk': "❌ Бас тарту"
    },
    'change_language': {
        'ru': "🌐 Сменить язык",
        'en': "🌐 Change language",
        'kk': "🌐 Тілді өзгерту"
    },
    'language_changed': {
        'ru': "🌐 Язык изменен на русский",
        'en': "🌐 Language changed to English",
        'kk': "🌐 Тіл қазақ тіліне өзгертілді"
    },
    'student_register': {
        'ru': "Давайте зарегистрируем ваш профиль студента. Введите ваше ФИО:",
        'en': "Let's register your student profile. Enter your full name:",
        'kk': "Студент профиліңізді тіркеңіз. Аты-жөніңізді енгізіңіз:"
    },
    'enter_phone': {
        'ru': "Введите ваш номер телефона или нажмите кнопку для отправки контакта:",
        'en': "Enter your phone number or press the button to share contact:",
        'kk': "Телефон нөміріңізді енгізіңіз немесе батырманы басып контакті жіберіңіз:"
    },
    'share_contact': {
        'ru': "📞 Отправить контакт",
        'en': "📞 Share contact",
        'kk': "📞 Контакті жіберу"
    },
    'enter_course': {
        'ru': "Введите ваш курс обучения:",
        'en': "Enter your course:",
        'kk': "Оқу курсыңызды енгізіңіз:"
    },
    'enter_major': {
        'ru': "Введите вашу специальность:",
        'en': "Enter your major:",
        'kk': "Мамандығыңызды енгізіңіз:"
    },
    'enter_about': {
        'ru': "Напишите несколько предложений о себе:",
        'en': "Write a few sentences about yourself:",
        'kk': "Өзіңіз туралы бірнеше сөйлем жаз:"
    },
    'employer_register': {
        'ru': "Давайте зарегистрируем ваш профиль работодателя. Введите название компании:",
        'en': "Let's register your employer profile. Enter company name:",
        'kk': "Жұмыс беруші профиліңізді тіркеңіз. Компания атауын енгізіңіз:"
    },
    'enter_employer_phone': {
        'ru': "Введите контактный телефон компании:",
        'en': "Enter company contact phone:",
        'kk': "Компанияның байланыс телефонын енгізіңіз:"
    },
    'browse_jobs': {
        'ru': "🔍 Поиск вакансий",
        'en': "🔍 Browse jobs",
        'kk': "🔍 Вакансияларды іздеу"
    },
    'my_applications': {
        'ru': "📄 Мои заявки",
        'en': "📄 My applications",
        'kk': "📄 Менің өтініштерім"
    },
    'profile': {
        'ru': "👤 Профиль",
        'en': "👤 Profile",
        'kk': "👤 Профиль"
    },
    'create_job': {
        'ru': "➕ Создать вакансию",
        'en': "➕ Create job",
        'kk': "➕ Вакансия жасау"
    },
    'my_jobs': {
        'ru': "💼 Мои вакансии",
        'en': "💼 My jobs",
        'kk': "💼 Менің вакансияларым"
    },
    'view_applications': {
        'ru': "📋 Просмотр заявок",
        'en': "📋 View applications",
        'kk': "📋 Өтініштерді қарау"
    },
    'enter_job_title': {
        'ru': "Введите название вакансии:",
        'en': "Enter job title:",
        'kk': "Вакансия атауын енгізіңіз:"
    },
    'enter_job_description': {
        'ru': "Введите описание вакансии:",
        'en': "Enter job description:",
        'kk': "Вакансия сипаттамасын енгізіңіз:"
    },
    'enter_salary': {
        'ru': "Введите зарплату или условия оплаты:",
        'en': "Enter salary or payment terms:",
        'kk': "Жалақыны немесе төлем шарттарын енгізіңіз:"
    },
    'enter_requirements': {
        'ru': "Введите требования к кандидату:",
        'en': "Enter candidate requirements:",
        'kk': "Үміткерге қойылатын талаптарды енгізіңіз:"
    },
    'job_created': {
        'ru': "✅ Вакансия успешно создана!",
        'en': "✅ Job created successfully!",
        'kk': "✅ Вакансия сәтті жасалды!"
    },
    'no_jobs': {
        'ru': "😔 На данный момент нет доступных вакансий.",
        'en': "😔 No available jobs at the moment.",
        'kk': "😔 Қазіргі уақытта бос вакансиялар жоқ."
    },
    'available_jobs': {
        'ru': "📋 Доступные вакансии:",
        'en': "📋 Available jobs:",
        'kk': "📋 Қол жетімді вакансиялар:"
    },
    'salary': {
        'ru': "Зарплата",
        'en': "Salary",
        'kk': "Жалақы"
    },
    'requirements': {
        'ru': "Требования",
        'en': "Requirements",
        'kk': "Талаптар"
    },
    'contact': {
        'ru': "Контакт",
        'en': "Contact",
        'kk': "Байланыс"
    },
    'apply_job': {
        'ru': "📨 Подать заявку",
        'en': "📨 Apply",
        'kk': "📨 Өтініш беру"
    },
    'already_applied': {
        'ru': "ℹ️ Вы уже подавали заявку на эту вакансию.",
        'en': "ℹ️ You have already applied for this job.",
        'kk': "ℹ️ Сіз бұл вакансияға өтініш бергенсіз."
    },
    'application_submitted': {
        'ru': "✅ Заявка успешно подана! Работодатель свяжется с вами.",
        'en': "✅ Application submitted! Employer will contact you.",
        'kk': "✅ Өтініш сәтті жіберілді! Жұмыс беруші сізбен хабарласады."
    },
    'new_application': {
        'ru': "📨 Новая заявка на вакансию",
        'en': "📨 New job application",
        'kk': "📨 Вакансияға жаңа өтініш"
    },
    'name': {
        'ru': "ФИО",
        'en': "Name",
        'kk': "Аты-жөні"
    },
    'course': {
        'ru': "Курс",
        'en': "Course",
        'kk': "Курс"
    },
    'major': {
        'ru': "Специальность",
        'en': "Major",
        'kk': "Мамандық"
    },
    'phone': {
        'ru': "Телефон",
        'en': "Phone",
        'kk': "Телефон"
    },
    'job': {
        'ru': "Вакансия",
        'en': "Job",
        'kk': "Вакансия"
    },
    'about_student': {
        'ru': "О себе",
        'en': "About",
        'kk': "Өзі туралы"
    },
    'no_applications': {
        'ru': "📭 У вас пока нет заявок.",
        'en': "📭 No applications yet.",
        'kk': "📭 Әлі өтініштер жоқ."
    },
    'your_applications': {
        'ru': "📋 Заявки на ваши вакансии:",
        'en': "📋 Applications for your jobs:",
        'kk': "📋 Сіздің вакансияларыңызға өтініштер:"
    },
    'status_pending': {
        'ru': "⏳ Ожидание",
        'en': "⏳ Pending",
        'kk': "⏳ Күтуде"
    },
    'status_under_review': {
        'ru': "🔍 Рассмотрение",
        'en': "🔍 Under review",
        'kk': "🔍 Қарастыруда"
    },
    'status_accepted': {
        'ru': "✅ Принята",
        'en': "✅ Accepted",
        'kk': "✅ Қабылданды"
    },
    'status_rejected': {
        'ru': "❌ Отклонена",
        'en': "❌ Rejected",
        'kk': "❌ Қабылданбады"
    },
    'application': {
        'ru': "Заявка",
        'en': "Application",
        'kk': "Өтініш"
    },
    'applied_at': {
        'ru': "Подана",
        'en': "Applied at",
        'kk': "Өтініш берді"
    },
    'status': {
        'ru': "Статус",
        'en': "Status",
        'kk': "Статус"
    },
    'accept_application': {
        'ru': "✅ Принять",
        'en': "✅ Accept",
        'kk': "✅ Қабылдау"
    },
    'reject_application': {
        'ru': "❌ Отклонить",
        'en': "❌ Reject",
        'kk': "❌ Қабылдамау"
    },
    'application_updated': {
        'ru': "Статус заявки обновлен на: {status}",
        'en': "Application status updated to: {status}",
        'kk': "Өтініш статусы жаңартылды: {status}"
    },
    'application_accepted': {
        'ru': "🎉 Поздравляем! Ваша заявка на вакансию '{job}' в компании '{company}' была принята!",
        'en': "🎉 Congratulations! Your application for '{job}' at '{company}' has been accepted!",
        'kk': "🎉 Құттықтаймыз! Сіздің '{company}' компаниясындағы '{job}' вакансиясына өтінішіңіз қабылданды!"
    },
    'application_rejected': {
        'ru': "ℹ️ К сожалению, ваша заявка на вакансию '{job}' в компании '{company}' была отклонена.",
        'en': "ℹ️ Unfortunately, your application for '{job}' at '{company}' has been rejected.",
        'kk': "ℹ️ Өкінішке орай, сіздің '{company}' компаниясындағы '{job}' вакансиясына өтінішіңіз қабылданбады."
    },
    'admin_only': {
        'ru': "❌ Эта команда доступна только администраторам.",
        'en': "❌ This command is available only for administrators.",
        'kk': "❌ Бұл команда тек әкімшілер үшін қолжетімді."
    },
    'help_admin_text': {
        'ru': """👔 *Команды для администраторов (работодателей):*

*/create_job* - создать вакансию
*/my_jobs* - просмотреть мои вакансии
*/view_applications* - просмотреть заявки
*/export_applications* - экспорт заявок в Excel
*/list_students* - список всех студентов
*/help_admin* - показать это сообщение

*Быстрые команды:*
*/delete_job_<ID>* - удалить вакансию
*/delete_application_<ID>* - удалить заявку""",
        'en': """👔 *Admin commands (employers):*

*/create_job* - create a job
*/my_jobs* - view my jobs
*/view_applications* - view applications
*/export_applications* - export applications to Excel
*/list_students* - list all students
*/help_admin* - show this message

*Quick commands:*
*/delete_job_<ID>* - delete job
*/delete_application_<ID>* - delete application""",
        'kk': """👔 *Әкімшілер үшін командалар (жұмыс берушілер):*

*/create_job* - вакансия жасау
*/my_jobs* - менің вакансияларымды қарау
*/view_applications* - өтініштерді қарау
*/export_applications* - өтініштерді Excel-ге экспорттау
*/list_students* - барлық студенттердің тізімі
*/help_admin* - бұл хабарды көрсету

*Жылдам командалар:*
*/delete_job_<ID>* - вакансияны жою
*/delete_application_<ID>* - өтінішті жою"""
    },
    'no_students': {
        'ru': "📭 Студентов пока нет.",
        'en': "📭 No students yet.",
        'kk': "📭 Әлі студенттер жоқ."
    },
    'students_list': {
        'ru': "👥 Список студентов:",
        'en': "👥 Students list:",
        'kk': "👥 Студенттер тізімі:"
    },
    'error_export': {
        'ru': "❌ Ошибка при экспорте файла",
        'en': "❌ Error exporting file",
        'kk': "❌ Файлды экспорттау кезінде қате"
    },
    'no_employer_profile': {
        'ru': "❌ Сначала заполните профиль работодателя. Используйте команду /create_job",
        'en': "❌ Please complete your employer profile first. Use /create_job command",
        'kk': "❌ Алдымен жұмыс беруші профиліңізді толтырыңыз. /create_job командасын пайдаланыңыз"
    },
    'company_name_saved': {
        'ru': "✅ Название компании сохранено. Теперь введите контактный телефон:",
        'en': "✅ Company name saved. Now enter contact phone:",
        'kk': "✅ Компания атауы сақталды. Енді байланыс телефонын енгізіңіз:"
    },
    'switch_to_student': {
        'ru': "🎓 Режим студента",
        'en': "🎓 Student mode",
        'kk': "🎓 Студент режимі"
    },
    'switch_to_employer': {
        'ru': "👔 Режим работодателя",
        'en': "👔 Employer mode",
        'kk': "👔 Жұмыс беруші режимі"
    },
    'employer_as_student_warning': {
        'ru': "⚠️ Вы просматриваете вакансии в режиме студента. Для возврата в панель работодателя нажмите 'Режим работодателя'",
        'en': "⚠️ You are browsing jobs in student mode. To return to employer panel, press 'Employer mode'",
        'kk': "⚠️ Сіз студент режимінде вакансияларды көрудесіз. Жұмыс беруші панеліне оралу үшін 'Жұмыс беруші режимі' батырмасын басыңыз"
    },
    'student_applications': {
        'ru': "📄 Ваши заявки:",
        'en': "📄 Your applications:",
        'kk': "📄 Сіздің өтініштеріңіз:"
    },
    'student_profile': {
        'ru': "👤 Ваш профиль:",
        'en': "👤 Your profile:",
        'kk': "👤 Сіздің профиліңіз:"
    },
    'edit_profile': {
        'ru': "✏️ Редактировать профиль",
        'en': "✏️ Edit profile",
        'kk': "✏️ Профильді өңдеу"
    }
}


# Statuses for applications
class ApplicationStatus(Enum):
    PENDING = "pending"  # Очередь
    UNDER_REVIEW = "under_review"  # Рассмотрение
    ACCEPTED = "accepted"  # Принята
    REJECTED = "rejected"  # Отклонена


# ------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states
(SELECT_LANGUAGE, STUDENT_NAME, STUDENT_PHONE, STUDENT_COURSE,
 STUDENT_MAJOR, STUDENT_ABOUT, EMPLOYER_NAME, EMPLOYER_PHONE,
 JOB_TITLE, JOB_DESCRIPTION, JOB_SALARY, JOB_REQUIREMENTS) = range(12)

db_lock = Lock()


# ------------------ DB ------------------
def init_db():
    with db_lock:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        cur = conn.cursor()

        # Таблица пользователей (студенты и работодатели)
        cur.execute("""CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER UNIQUE NOT NULL,
                        user_type TEXT NOT NULL, -- 'student' or 'employer'
                        language TEXT DEFAULT 'ru',
                        created_at TEXT NOT NULL
                    )""")

        # Таблица студентов
        cur.execute("""CREATE TABLE IF NOT EXISTS students (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER UNIQUE NOT NULL,
                        fullname TEXT NOT NULL,
                        phone TEXT NOT NULL,
                        course TEXT NOT NULL,
                        major TEXT NOT NULL,
                        about TEXT,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(user_id) REFERENCES users(user_id)
                    )""")

        # Таблица работодателей
        cur.execute("""CREATE TABLE IF NOT EXISTS employers (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER UNIQUE NOT NULL,
                        company_name TEXT NOT NULL,
                        contact_phone TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(user_id) REFERENCES users(user_id)
                    )""")

        # Таблица вакансий
        cur.execute("""CREATE TABLE IF NOT EXISTS jobs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        employer_id INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        description TEXT NOT NULL,
                        salary TEXT,
                        requirements TEXT,
                        created_at TEXT NOT NULL,
                        is_active BOOLEAN DEFAULT 1,
                        FOREIGN KEY(employer_id) REFERENCES employers(id)
                    )""")

        # Таблица заявок
        cur.execute("""CREATE TABLE IF NOT EXISTS applications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_id INTEGER NOT NULL,
                        student_id INTEGER NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        applied_at TEXT NOT NULL,
                        reviewed_at TEXT,
                        employer_notes TEXT,
                        FOREIGN KEY(job_id) REFERENCES jobs(id),
                        FOREIGN KEY(student_id) REFERENCES students(id)
                    )""")

        conn.commit()
        conn.close()


def db_execute(query, params=(), fetch=False, many=False):
    with db_lock:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        cur = conn.cursor()
        if many:
            cur.executemany(query, params)
            conn.commit()
            conn.close()
            return None
        cur.execute(query, params)
        res = cur.fetchall() if fetch else None
        conn.commit()
        conn.close()
        return res


# ------------------ Language & Text Utilities ------------------
def get_user_language(user_id: int) -> str:
    """Get user's preferred language"""
    result = db_execute(
        "SELECT language FROM users WHERE user_id = ?",
        (user_id,), fetch=True
    )
    return result[0][0] if result else 'ru'


def get_text(key: str, language: str) -> str:
    """Get localized text"""
    return TEXTS.get(key, {}).get(language, TEXTS.get(key, {}).get('ru', key))


async def send_localized_message(context, chat_id, key, reply_markup=None, **format_kwargs):
    """Send message in user's language"""
    language = get_user_language(chat_id)
    text = get_text(key, language)

    if format_kwargs:
        text = text.format(**format_kwargs)

    await safe_send_message(context.bot, chat_id=chat_id, text=text, reply_markup=reply_markup)


# ------------------ User Management ------------------
def is_employer(user_id: int) -> bool:
    """Check if user is employer (admin)"""
    return user_id in admin_ids_set


def get_user_type(user_id: int) -> str:
    """Get user type (student/employer)"""
    result = db_execute(
        "SELECT user_type FROM users WHERE user_id = ?",
        (user_id,), fetch=True
    )
    return result[0][0] if result else None


def is_user_registered(user_id: int) -> bool:
    """Check if user is fully registered"""
    user_type = get_user_type(user_id)
    if not user_type:
        return False

    if user_type == 'student':
        result = db_execute(
            "SELECT id FROM students WHERE user_id = ?",
            (user_id,), fetch=True
        )
    else:  # employer
        result = db_execute(
            "SELECT id FROM employers WHERE user_id = ?",
            (user_id,), fetch=True
        )

    return bool(result)


def get_employer_id(user_id: int) -> int:
    """Get employer ID by user ID"""
    result = db_execute(
        "SELECT id FROM employers WHERE user_id = ?",
        (user_id,), fetch=True
    )
    return result[0][0] if result else None


def has_student_profile(user_id: int) -> bool:
    """Check if user has student profile"""
    result = db_execute(
        "SELECT id FROM students WHERE user_id = ?",
        (user_id,), fetch=True
    )
    return bool(result)


# ------------------ Async helpers ------------------
async def safe_send_message(bot, chat_id: int = None, text: str = None, reply_markup=None,
                            reply_to_message_id=None, parse_mode=None):
    """Safe message sending with retry logic"""
    if text is None:
        text = "\u200b"

    kwargs = {'chat_id': chat_id, 'text': text}
    if reply_markup is not None:
        kwargs['reply_markup'] = reply_markup
    if reply_to_message_id is not None:
        kwargs['reply_to_message_id'] = reply_to_message_id
    if parse_mode is not None:
        kwargs['parse_mode'] = parse_mode

    try:
        return await bot.send_message(**kwargs)
    except (TimedOut, NetworkError, RetryAfter) as e:
        logger.warning("send_message error: %s - retrying", e)
        try:
            return await bot.send_message(**kwargs)
        except Exception as e2:
            logger.error("Second attempt failed: %s", e2)
            return None
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        return None


def get_chat_id(update_or_query) -> int:
    """Extract chat_id from various update types"""
    if hasattr(update_or_query, "effective_chat") and update_or_query.effective_chat:
        return update_or_query.effective_chat.id
    if isinstance(update_or_query, CallbackQuery):
        if update_or_query.message and update_or_query.message.chat:
            return update_or_query.message.chat.id
        if update_or_query.from_user:
            return update_or_query.from_user.id
    if isinstance(update_or_query, Message):
        if update_or_query.chat:
            return update_or_query.chat.id
    return None


# ------------------ Language Change Handler ------------------
async def callback_change_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle language change request"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = get_chat_id(query)

    # Show language selection
    keyboard = []
    for code, name in LANGUAGES.items():
        keyboard.append([InlineKeyboardButton(name, callback_data=f"change_lang:{code}")])

    await safe_send_message(
        context.bot,
        chat_id=chat_id,
        text=get_text('choose_language', get_user_language(user_id)),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def callback_set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle language selection"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    language_code = query.data.split(":")[1]

    # Determine user type
    user_type = 'employer' if is_employer(user_id) else 'student'

    # Create or update user record
    existing_user = db_execute(
        "SELECT id FROM users WHERE user_id = ?",
        (user_id,), fetch=True
    )

    if existing_user:
        # Update existing user
        db_execute(
            "UPDATE users SET language = ? WHERE user_id = ?",
            (language_code, user_id)
        )
    else:
        # Create new user
        db_execute(
            "INSERT INTO users (user_id, user_type, language, created_at) VALUES (?, ?, ?, ?)",
            (user_id, user_type, language_code, datetime.now().isoformat())
        )

    # Send confirmation
    chat_id = get_chat_id(query)

    text = get_text('language_changed', language_code)
    await safe_send_message(context.bot, chat_id=chat_id, text=text)

    # Continue based on user type and registration status
    if is_user_registered(user_id):
        await show_main_menu(update, context, user_type)
    else:
        if user_type == 'student':
            return await start_student_registration(update, context)
        else:
            # For employers, show main menu directly - they'll register when creating first job
            await show_main_menu(update, context, 'employer')


# ------------------ Handlers ------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command with language selection"""
    user_id = update.effective_user.id
    context.user_data.clear()

    # Check if user already exists
    existing_user = db_execute(
        "SELECT user_type, language FROM users WHERE user_id = ?",
        (user_id,), fetch=True
    )

    if existing_user:
        user_type, language = existing_user[0]
        # User exists, show appropriate menu
        if is_user_registered(user_id):
            await show_main_menu(update, context, user_type)
            return
        else:
            # User exists but not fully registered
            if user_type == 'student':
                return await start_student_registration(update, context)
            else:
                # For employers, just show main menu - they'll register when creating first job
                await show_main_menu(update, context, 'employer')
                return

    # New user - show language selection
    keyboard = []
    for code, name in LANGUAGES.items():
        keyboard.append([InlineKeyboardButton(name, callback_data=f"set_lang:{code}")])

    chat_id = get_chat_id(update)
    await safe_send_message(
        context.bot,
        chat_id=chat_id,
        text=get_text('choose_language', 'ru'),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def start_student_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start student registration process"""
    chat_id = get_chat_id(update.callback_query if update.callback_query else update)
    language = get_user_language(chat_id)

    text = get_text('student_register', language)
    await safe_send_message(context.bot, chat_id=chat_id, text=text)
    return STUDENT_NAME


# Student registration handlers
async def student_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["student_fullname"] = update.message.text.strip()
    chat_id = get_chat_id(update)
    language = get_user_language(chat_id)

    text = get_text('enter_phone', language)
    kb = ReplyKeyboardMarkup([[KeyboardButton(get_text('share_contact', language), request_contact=True)]],
                             resize_keyboard=True, one_time_keyboard=True)

    await safe_send_message(context.bot, chat_id=chat_id, text=text, reply_markup=kb)
    return STUDENT_PHONE


async def student_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = None
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text.strip()

    context.user_data["student_phone"] = phone
    chat_id = get_chat_id(update)
    language = get_user_language(chat_id)

    text = get_text('enter_course', language)
    await safe_send_message(context.bot, chat_id=chat_id, text=text)
    return STUDENT_COURSE


async def student_course(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["student_course"] = update.message.text.strip()
    chat_id = get_chat_id(update)
    language = get_user_language(chat_id)

    text = get_text('enter_major', language)
    await safe_send_message(context.bot, chat_id=chat_id, text=text)
    return STUDENT_MAJOR


async def student_major(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["student_major"] = update.message.text.strip()
    chat_id = get_chat_id(update)
    language = get_user_language(chat_id)

    text = get_text('enter_about', language)
    await safe_send_message(context.bot, chat_id=chat_id, text=text)
    return STUDENT_ABOUT


async def student_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["student_about"] = update.message.text.strip()
    user_id = update.effective_user.id

    # Save student data
    db_execute(
        """INSERT INTO students (user_id, fullname, phone, course, major, about, created_at) 
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, context.user_data["student_fullname"], context.user_data["student_phone"],
         context.user_data["student_course"], context.user_data["student_major"],
         context.user_data["student_about"], datetime.now().isoformat())
    )

    await show_main_menu(update, context, 'student')
    context.user_data.clear()
    return ConversationHandler.END


# Employer registration handlers - SIMPLIFIED VERSION
async def start_employer_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start employer registration process"""
    chat_id = get_chat_id(update.callback_query if update.callback_query else update)
    language = get_user_language(chat_id)

    text = get_text('employer_register', language)
    await safe_send_message(context.bot, chat_id=chat_id, text=text)
    return EMPLOYER_NAME


async def employer_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle employer company name input"""
    context.user_data["company_name"] = update.message.text.strip()
    chat_id = get_chat_id(update)
    language = get_user_language(chat_id)

    text = get_text('company_name_saved', language)
    kb = ReplyKeyboardMarkup([[KeyboardButton(get_text('share_contact', language), request_contact=True)]],
                             resize_keyboard=True, one_time_keyboard=True)

    await safe_send_message(context.bot, chat_id=chat_id, text=text, reply_markup=kb)
    return EMPLOYER_PHONE


async def employer_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle employer phone input"""
    phone = None
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text.strip()

    user_id = update.effective_user.id

    # Save employer data
    db_execute(
        """INSERT INTO employers (user_id, company_name, contact_phone, created_at) 
           VALUES (?, ?, ?, ?)""",
        (user_id, context.user_data["company_name"], phone, datetime.now().isoformat())
    )

    chat_id = get_chat_id(update)
    language = get_user_language(chat_id)

    text = "✅ Профиль работодателя создан! Теперь вы можете создавать вакансии."
    await safe_send_message(context.bot, chat_id=chat_id, text=text)

    await show_main_menu(update, context, 'employer')
    context.user_data.clear()
    return ConversationHandler.END


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_type: str):
    """Show main menu based on user type"""
    chat_id = get_chat_id(update.callback_query if update.callback_query else update)
    user_id = update.effective_user.id if update.effective_user else update.callback_query.from_user.id
    language = get_user_language(user_id)

    keyboard = []

    if user_type == 'student':
        keyboard = [
            [InlineKeyboardButton(get_text('browse_jobs', language), callback_data="browse_jobs")],
            [InlineKeyboardButton(get_text('my_applications', language), callback_data="my_applications")],
            [InlineKeyboardButton(get_text('profile', language), callback_data="student_profile")],
        ]

        # Add switch to employer mode if user is employer
        if is_employer(user_id):
            keyboard.append(
                [InlineKeyboardButton(get_text('switch_to_employer', language), callback_data="switch_to_employer")])

        keyboard.append([InlineKeyboardButton(get_text('change_language', language), callback_data="change_language")])

        title = get_text('start_student', language)
    else:  # employer
        keyboard = [
            [InlineKeyboardButton(get_text('create_job', language), callback_data="create_job")],
            [InlineKeyboardButton(get_text('my_jobs', language), callback_data="my_jobs")],
            [InlineKeyboardButton(get_text('view_applications', language), callback_data="view_applications")],
        ]

        # Add student functionality for employers
        if has_student_profile(user_id):
            keyboard.append(
                [InlineKeyboardButton(get_text('switch_to_student', language), callback_data="switch_to_student")])
        else:
            keyboard.append(
                [InlineKeyboardButton(get_text('browse_jobs', language), callback_data="browse_jobs_as_employer")])

        keyboard.append([InlineKeyboardButton(get_text('change_language', language), callback_data="change_language")])

        title = get_text('start_employer', language)

    await safe_send_message(
        context.bot,
        chat_id=chat_id,
        text=title,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# Job creation handlers (employer side)
async def callback_create_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start job creation process"""
    user_id = update.callback_query.from_user.id
    chat_id = get_chat_id(update.callback_query)
    language = get_user_language(chat_id)

    # Check if employer has profile
    employer_id = get_employer_id(user_id)

    if not employer_id:
        # Start employer registration first
        text = get_text('employer_register', language)
        await safe_send_message(context.bot, chat_id=chat_id, text=text)
        return EMPLOYER_NAME

    # Continue with job creation
    text = get_text('enter_job_title', language)
    await safe_send_message(context.bot, chat_id=chat_id, text=text)
    return JOB_TITLE


async def job_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["job_title"] = update.message.text.strip()
    chat_id = get_chat_id(update)
    language = get_user_language(chat_id)

    text = get_text('enter_job_description', language)
    await safe_send_message(context.bot, chat_id=chat_id, text=text)
    return JOB_DESCRIPTION


async def job_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["job_description"] = update.message.text.strip()
    chat_id = get_chat_id(update)
    language = get_user_language(chat_id)

    text = get_text('enter_salary', language)
    await safe_send_message(context.bot, chat_id=chat_id, text=text)
    return JOB_SALARY


async def job_salary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["job_salary"] = update.message.text.strip()
    chat_id = get_chat_id(update)
    language = get_user_language(chat_id)

    text = get_text('enter_requirements', language)
    await safe_send_message(context.bot, chat_id=chat_id, text=text)
    return JOB_REQUIREMENTS


async def job_requirements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["job_requirements"] = update.message.text.strip()
    user_id = update.effective_user.id

    # Get employer ID
    employer_id = get_employer_id(user_id)

    if employer_id:
        # Save job
        db_execute(
            """INSERT INTO jobs (employer_id, title, description, salary, requirements, created_at) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (employer_id, context.user_data["job_title"], context.user_data["job_description"],
             context.user_data["job_salary"], context.user_data["job_requirements"],
             datetime.now().isoformat())
        )

        chat_id = get_chat_id(update)
        language = get_user_language(chat_id)

        text = get_text('job_created', language)
        await safe_send_message(context.bot, chat_id=chat_id, text=text)

    await show_main_menu(update, context, 'employer')
    context.user_data.clear()
    return ConversationHandler.END


# Job browsing and application handlers (student side)
async def callback_browse_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show available jobs"""
    user_id = update.callback_query.from_user.id
    chat_id = get_chat_id(update.callback_query)
    language = get_user_language(chat_id)

    # Check if user has student profile (for applying to jobs)
    has_profile = has_student_profile(user_id)
    is_employer_user = is_employer(user_id)

    jobs = db_execute(
        """SELECT j.id, j.title, e.company_name, j.salary, j.created_at 
           FROM jobs j 
           JOIN employers e ON j.employer_id = e.id 
           WHERE j.is_active = 1 
           ORDER BY j.created_at DESC""",
        fetch=True
    )

    if not jobs:
        text = get_text('no_jobs', language)
        await safe_send_message(context.bot, chat_id=chat_id, text=text)
        return

    # Add warning for employers browsing as students
    text = get_text('available_jobs', language)
    if is_employer_user and has_profile:
        text += f"\n\n{get_text('employer_as_student_warning', language)}"

    keyboard = []
    for job_id, title, company, salary, created_at in jobs:
        button_text = f"{title} - {company}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"view_job:{job_id}")])

    # Add back button
    keyboard.append([InlineKeyboardButton(get_text('back', language), callback_data="back_to_main")])

    await safe_send_message(
        context.bot,
        chat_id=chat_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def callback_browse_jobs_as_employer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show available jobs for employers without student profile"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = get_chat_id(query)
    language = get_user_language(user_id)

    jobs = db_execute(
        """SELECT j.id, j.title, e.company_name, j.salary, j.created_at 
           FROM jobs j 
           JOIN employers e ON j.employer_id = e.id 
           WHERE j.is_active = 1 
           ORDER BY j.created_at DESC""",
        fetch=True
    )

    if not jobs:
        text = get_text('no_jobs', language)
        await safe_send_message(context.bot, chat_id=chat_id, text=text)
        return

    text = get_text('available_jobs', language) + "\n\n"
    text += "ℹ️ Вы можете просматривать вакансии, но для подачи заявки необходимо заполнить профиль студента."

    keyboard = []
    for job_id, title, company, salary, created_at in jobs:
        button_text = f"{title} - {company}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"view_job_info:{job_id}")])

    keyboard.append([InlineKeyboardButton(get_text('back', language), callback_data="back_to_main")])

    await safe_send_message(
        context.bot,
        chat_id=chat_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def callback_view_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show job details for users with student profile"""
    query = update.callback_query
    await query.answer()

    job_id = int(query.data.split(":")[1])
    user_id = query.from_user.id

    job = db_execute(
        """SELECT j.title, j.description, j.salary, j.requirements, e.company_name, e.contact_phone
           FROM jobs j 
           JOIN employers e ON j.employer_id = e.id 
           WHERE j.id = ?""",
        (job_id,), fetch=True
    )

    if job:
        title, description, salary, requirements, company, phone = job[0]
        chat_id = get_chat_id(query)
        language = get_user_language(user_id)

        is_employer_user = is_employer(user_id)
        has_profile = has_student_profile(user_id)

        text = f"**{title}**\n\n{company}\n\n{description}\n\n"
        if salary:
            text += f"💵 {get_text('salary', language)}: {salary}\n"
        if requirements:
            text += f"📋 {get_text('requirements', language)}: {requirements}\n"
        text += f"📞 {get_text('contact', language)}: {phone}"

        # Add warning for employers
        if is_employer_user:
            text += f"\n\n{get_text('employer_as_student_warning', language)}"

        keyboard = [
            [InlineKeyboardButton(get_text('apply_job', language), callback_data=f"apply_job:{job_id}")],
        ]

        # Different back button based on user type
        if is_employer_user and has_profile:
            keyboard.append([InlineKeyboardButton(get_text('back', language), callback_data="browse_jobs")])
        else:
            keyboard.append([InlineKeyboardButton(get_text('back', language), callback_data="browse_jobs")])

        await safe_send_message(
            context.bot,
            chat_id=chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )


async def callback_view_job_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show job details for employers without student profile (view only)"""
    query = update.callback_query
    await query.answer()

    job_id = int(query.data.split(":")[1])
    user_id = query.from_user.id
    chat_id = get_chat_id(query)
    language = get_user_language(user_id)

    job = db_execute(
        """SELECT j.title, j.description, j.salary, j.requirements, e.company_name, e.contact_phone
           FROM jobs j 
           JOIN employers e ON j.employer_id = e.id 
           WHERE j.id = ?""",
        (job_id,), fetch=True
    )

    if job:
        title, description, salary, requirements, company, phone = job[0]

        text = f"**{title}**\n\n{company}\n\n{description}\n\n"
        if salary:
            text += f"💵 {get_text('salary', language)}: {salary}\n"
        if requirements:
            text += f"📋 {get_text('requirements', language)}: {requirements}\n"
        text += f"📞 {get_text('contact', language)}: {phone}\n\n"
        text += "ℹ️ Для подачи заявки на эту вакансию необходимо заполнить профиль студента."

        keyboard = [
            [InlineKeyboardButton("📝 Заполнить профиль студента", callback_data="start_student_registration")],
            [InlineKeyboardButton(get_text('back', language), callback_data="browse_jobs_as_employer")]
        ]

        await safe_send_message(
            context.bot,
            chat_id=chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )


async def callback_apply_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Apply for a job"""
    query = update.callback_query
    await query.answer()

    job_id = int(query.data.split(":")[1])
    user_id = query.from_user.id

    # Get student ID
    student = db_execute(
        "SELECT id FROM students WHERE user_id = ?", (user_id,), fetch=True
    )

    if student:
        student_id = student[0][0]

        # Check if already applied
        existing = db_execute(
            "SELECT id FROM applications WHERE job_id = ? AND student_id = ?",
            (job_id, student_id), fetch=True
        )

        chat_id = get_chat_id(query)
        language = get_user_language(user_id)

        if existing:
            text = get_text('already_applied', language)
            await safe_send_message(context.bot, chat_id=chat_id, text=text)
        else:
            # Create application
            db_execute(
                """INSERT INTO applications (job_id, student_id, applied_at, status) 
                   VALUES (?, ?, ?, ?)""",
                (job_id, student_id, datetime.now().isoformat(), ApplicationStatus.PENDING.value)
            )

            text = get_text('application_submitted', language)
            await safe_send_message(context.bot, chat_id=chat_id, text=text)

            # Notify employer
            await notify_employer_about_application(context, job_id, student_id)

    await show_main_menu(update, context, 'student' if not is_employer(user_id) else 'employer')


async def notify_employer_about_application(context: ContextTypes.DEFAULT_TYPE, job_id: int, student_id: int):
    """Notify employer about new application"""
    application_data = db_execute(
        """SELECT s.fullname, s.course, s.major, s.about, s.phone, j.title, e.user_id
           FROM applications a
           JOIN students s ON a.student_id = s.id
           JOIN jobs j ON a.job_id = j.id
           JOIN employers e ON j.employer_id = e.id
           WHERE a.job_id = ? AND a.student_id = ?""",
        (job_id, student_id), fetch=True
    )

    if application_data:
        fullname, course, major, about, phone, job_title, employer_user_id = application_data[0]
        language = get_user_language(employer_user_id)

        text = (
            f"📨 {get_text('new_application', language)}\n\n"
            f"👤 {get_text('name', language)}: {fullname}\n"
            f"🎓 {get_text('course', language)}: {course}\n"
            f"📚 {get_text('major', language)}: {major}\n"
            f"📞 {get_text('phone', language)}: {phone}\n"
            f"💼 {get_text('job', language)}: {job_title}\n"
            f"📝 {get_text('about_student', language)}: {about}"
        )

        await safe_send_message(context.bot, chat_id=employer_user_id, text=text)


# ------------------ Student Applications and Profile Handlers ------------------
async def callback_my_applications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show student's applications"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = get_chat_id(query)
    language = get_user_language(user_id)

    # Get student ID
    student = db_execute(
        "SELECT id FROM students WHERE user_id = ?", (user_id,), fetch=True
    )

    if not student:
        text = "Сначала заполните профиль студента."
        await safe_send_message(context.bot, chat_id=chat_id, text=text)
        return

    student_id = student[0][0]

    # Get applications
    applications = db_execute(
        """SELECT a.id, j.title, e.company_name, a.status, a.applied_at
           FROM applications a
           JOIN jobs j ON a.job_id = j.id
           JOIN employers e ON j.employer_id = e.id
           WHERE a.student_id = ?
           ORDER BY a.applied_at DESC""",
        (student_id,), fetch=True
    )

    if not applications:
        text = get_text('no_applications', language)
        keyboard = [[InlineKeyboardButton(get_text('back', language), callback_data="back_to_main")]]
        await safe_send_message(
            context.bot,
            chat_id=chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    text = get_text('student_applications', language) + "\n\n"

    for app_id, job_title, company, status, applied_at in applications:
        status_text = get_text(f'status_{status}', language)
        applied_date = datetime.fromisoformat(applied_at).strftime("%d.%m.%Y %H:%M")
        text += f"📄 *{job_title}*\n"
        text += f"🏢 {company}\n"
        text += f"📊 {status_text}\n"
        text += f"📅 {applied_date}\n\n"

    keyboard = [[InlineKeyboardButton(get_text('back', language), callback_data="back_to_main")]]

    await safe_send_message(
        context.bot,
        chat_id=chat_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def callback_student_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show student profile"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = get_chat_id(query)
    language = get_user_language(user_id)

    # Get student data
    student = db_execute(
        "SELECT fullname, phone, course, major, about FROM students WHERE user_id = ?",
        (user_id,), fetch=True
    )

    if not student:
        text = "Сначала заполните профиль студента."
        keyboard = [[InlineKeyboardButton("📝 Заполнить профиль", callback_data="start_student_registration")]]
        await safe_send_message(
            context.bot,
            chat_id=chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    fullname, phone, course, major, about = student[0]

    text = get_text('student_profile', language) + "\n\n"
    text += f"👤 {get_text('name', language)}: {fullname}\n"
    text += f"📞 {get_text('phone', language)}: {phone}\n"
    text += f"🎓 {get_text('course', language)}: {course}\n"
    text += f"📚 {get_text('major', language)}: {major}\n"
    if about:
        text += f"📝 {get_text('about_student', language)}: {about}\n"

    keyboard = [
        [InlineKeyboardButton(get_text('edit_profile', language), callback_data="edit_student_profile")],
        [InlineKeyboardButton(get_text('back', language), callback_data="back_to_main")]
    ]

    await safe_send_message(
        context.bot,
        chat_id=chat_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def callback_edit_student_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start student profile editing"""
    query = update.callback_query
    await query.answer()

    chat_id = get_chat_id(query)
    language = get_user_language(chat_id)

    text = "Редактирование профиля временно недоступно. Для изменения данных обратитесь к администратору."
    keyboard = [[InlineKeyboardButton(get_text('back', language), callback_data="student_profile")]]

    await safe_send_message(
        context.bot,
        chat_id=chat_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# Application management (employer side)
async def callback_view_applications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show applications to employer"""
    user_id = update.callback_query.from_user.id

    employer_id = get_employer_id(user_id)
    if not employer_id:
        chat_id = get_chat_id(update.callback_query)
        language = get_user_language(chat_id)
        text = get_text('no_employer_profile', language)
        await safe_send_message(context.bot, chat_id=chat_id, text=text)
        return

    applications = db_execute(
        """SELECT a.id, s.fullname, j.title, a.status, a.applied_at
           FROM applications a
           JOIN students s ON a.student_id = s.id
           JOIN jobs j ON a.job_id = j.id
           WHERE j.employer_id = ?
           ORDER BY a.applied_at DESC""",
        (employer_id,), fetch=True
    )

    chat_id = get_chat_id(update.callback_query)
    language = get_user_language(chat_id)

    if not applications:
        text = get_text('no_applications', language)
        keyboard = [[InlineKeyboardButton(get_text('back', language), callback_data="back_to_main")]]
        await safe_send_message(
            context.bot,
            chat_id=chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    keyboard = []
    for app_id, fullname, job_title, status, applied_at in applications:
        status_text = get_text(f'status_{status}', language)
        button_text = f"{fullname} - {job_title} ({status_text})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"review_application:{app_id}")])

    # Add back button
    keyboard.append([InlineKeyboardButton(get_text('back', language), callback_data="back_to_main")])

    text = get_text('your_applications', language)
    await safe_send_message(
        context.bot,
        chat_id=chat_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def callback_review_application(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show application details to employer"""
    query = update.callback_query
    await query.answer()

    application_id = int(query.data.split(":")[1])

    application = db_execute(
        """SELECT a.id, s.fullname, s.course, s.major, s.about, s.phone, 
                  j.title, a.status, a.applied_at, a.student_id
           FROM applications a
           JOIN students s ON a.student_id = s.id
           JOIN jobs j ON a.job_id = j.id
           WHERE a.id = ?""",
        (application_id,), fetch=True
    )

    if application:
        (app_id, fullname, course, major, about, phone,
         job_title, status, applied_at, student_id) = application[0]

        chat_id = get_chat_id(query)
        language = get_user_language(chat_id)

        status_text = get_text(f'status_{status}', language)
        applied_date = datetime.fromisoformat(applied_at).strftime("%Y-%m-%d %H:%M")

        text = (
            f"📄 {get_text('application', language)} #{app_id}\n\n"
            f"👤 {get_text('name', language)}: {fullname}\n"
            f"🎓 {get_text('course', language)}: {course}\n"
            f"📚 {get_text('major', language)}: {major}\n"
            f"📞 {get_text('phone', language)}: {phone}\n"
            f"💼 {get_text('job', language)}: {job_title}\n"
            f"📅 {get_text('applied_at', language)}: {applied_date}\n"
            f"📊 {get_text('status', language)}: {status_text}\n"
            f"📝 {get_text('about_student', language)}: {about}"
        )

        keyboard = []
        if status == ApplicationStatus.PENDING.value:
            keyboard.extend([
                [InlineKeyboardButton(get_text('accept_application', language),
                                      callback_data=f"accept_application:{app_id}")],
                [InlineKeyboardButton(get_text('reject_application', language),
                                      callback_data=f"reject_application:{app_id}")]
            ])

        keyboard.append([InlineKeyboardButton(get_text('back', language),
                                              callback_data="view_applications")])

        await safe_send_message(
            context.bot,
            chat_id=chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def callback_accept_application(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Accept an application"""
    await update_application_status(update, context, ApplicationStatus.ACCEPTED)


async def callback_reject_application(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reject an application"""
    await update_application_status(update, context, ApplicationStatus.REJECTED)


async def update_application_status(update: Update, context: ContextTypes.DEFAULT_TYPE, status: ApplicationStatus):
    """Update application status and notify student"""
    query = update.callback_query
    await query.answer()

    application_id = int(query.data.split(":")[1])

    # Update application status
    db_execute(
        "UPDATE applications SET status = ?, reviewed_at = ? WHERE id = ?",
        (status.value, datetime.now().isoformat(), application_id)
    )

    # Get application details for notification
    application = db_execute(
        """SELECT s.user_id, j.title, e.company_name
           FROM applications a
           JOIN students s ON a.student_id = s.id
           JOIN jobs j ON a.job_id = j.id
           JOIN employers e ON j.employer_id = e.id
           WHERE a.id = ?""",
        (application_id,), fetch=True
    )

    chat_id = get_chat_id(query)
    language = get_user_language(chat_id)

    if application:
        student_user_id, job_title, company_name = application[0]
        student_language = get_user_language(student_user_id)

        # Notify employer
        status_text = get_text(f'status_{status.value}', language)
        employer_text = get_text('application_updated', language).format(status=status_text)
        await safe_send_message(context.bot, chat_id=chat_id, text=employer_text)

        # Notify student
        if status == ApplicationStatus.ACCEPTED:
            student_text = get_text('application_accepted', student_language).format(
                job=job_title, company=company_name
            )
        else:
            student_text = get_text('application_rejected', student_language).format(
                job=job_title, company=company_name
            )

        await safe_send_message(context.bot, chat_id=student_user_id, text=student_text)

    await callback_view_applications(update, context)


# ------------------ My Jobs Handlers (Employer) ------------------
async def callback_my_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show employer's jobs via callback (button click)"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = get_chat_id(query)

    if not is_employer(user_id):
        language = get_user_language(user_id)
        text = get_text('admin_only', language)
        await safe_send_message(context.bot, chat_id=chat_id, text=text)
        return

    employer_id = get_employer_id(user_id)
    if not employer_id:
        language = get_user_language(user_id)
        text = get_text('no_employer_profile', language)
        await safe_send_message(context.bot, chat_id=chat_id, text=text)
        return

    jobs = db_execute(
        """SELECT id, title, description, salary, requirements, created_at, is_active
           FROM jobs WHERE employer_id = ? ORDER BY created_at DESC""",
        (employer_id,), fetch=True
    )

    language = get_user_language(user_id)

    if not jobs:
        text = get_text('no_jobs', language)
        keyboard = [[InlineKeyboardButton(get_text('back', language), callback_data="back_to_main")]]
        await safe_send_message(
            context.bot,
            chat_id=chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Создаем более информативное сообщение с кнопками для каждой вакансии
    text = get_text('my_jobs', language) + "\n\n"

    keyboard = []
    for job_id, title, description, salary, requirements, created_at, is_active in jobs:
        status = "✅ " + (
            "Активна" if language == 'ru' else "Active" if language == 'en' else "Белсенді") if is_active else "❌ " + (
            "Неактивна" if language == 'ru' else "Inactive" if language == 'en' else "Белсенді емес")

        # Добавляем кнопку для просмотра/управления каждой вакансией
        keyboard.append([InlineKeyboardButton(
            f"{title} ({status})",
            callback_data=f"view_my_job:{job_id}"
        )])

    # Добавляем кнопку "Назад"
    keyboard.append([InlineKeyboardButton(get_text('back', language), callback_data="back_to_main")])

    await safe_send_message(
        context.bot,
        chat_id=chat_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def callback_view_my_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show details of employer's specific job"""
    query = update.callback_query
    await query.answer()

    job_id = int(query.data.split(":")[1])
    user_id = query.from_user.id

    job = db_execute(
        """SELECT title, description, salary, requirements, created_at, is_active
           FROM jobs WHERE id = ? AND employer_id = (SELECT id FROM employers WHERE user_id = ?)""",
        (job_id, user_id), fetch=True
    )

    if not job:
        language = get_user_language(user_id)
        await safe_send_message(context.bot, chat_id=get_chat_id(query),
                                text="❌ Вакансия не найдена")
        return

    title, description, salary, requirements, created_at, is_active = job[0]
    language = get_user_language(user_id)
    created = datetime.fromisoformat(created_at).strftime("%d.%m.%Y %H:%M")
    status = "✅ " + (
        "Активна" if language == 'ru' else "Active" if language == 'en' else "Белсенді") if is_active else "❌ " + (
        "Неактивна" if language == 'ru' else "Inactive" if language == 'en' else "Белсенді емес")

    text = f"**{title}**\n\n"
    text += f"📅 {get_text('applied_at', language)}: {created}\n"
    text += f"📊 {get_text('status', language)}: {status}\n\n"
    text += f"**{get_text('enter_job_description', language).rstrip(':')}:**\n{description}\n\n"

    if salary:
        text += f"**{get_text('salary', language)}:** {salary}\n\n"
    if requirements:
        text += f"**{get_text('requirements', language)}:** {requirements}\n\n"

    # Получаем количество заявок на эту вакансию
    applications_count = db_execute(
        "SELECT COUNT(*) FROM applications WHERE job_id = ?",
        (job_id,), fetch=True
    )[0][0]

    text += f"📨 {get_text('application', language)}: {applications_count}"

    keyboard = [
        [InlineKeyboardButton(
            "👀 " + get_text('view_applications', language),
            callback_data=f"view_job_applications:{job_id}"
        )],
        [InlineKeyboardButton(
            "❌ " + (
                "Деактивировать" if language == 'ru' else "Deactivate" if language == 'en' else "Белсенділігін өшіру") if is_active else "✅ " + (
                "Активировать" if language == 'ru' else "Activate" if language == 'en' else "Белсендіру"),
            callback_data=f"toggle_job:{job_id}:{'deactivate' if is_active else 'activate'}"
        )],
        [InlineKeyboardButton(get_text('back', language), callback_data="my_jobs")]
    ]

    await safe_send_message(
        context.bot,
        chat_id=get_chat_id(query),
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def callback_view_job_applications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show applications for a specific job"""
    query = update.callback_query
    await query.answer()

    job_id = int(query.data.split(":")[1])
    user_id = query.from_user.id

    # Проверяем, что вакансия принадлежит работодателю
    job_owner = db_execute(
        "SELECT employer_id FROM jobs WHERE id = ? AND employer_id = (SELECT id FROM employers WHERE user_id = ?)",
        (job_id, user_id), fetch=True
    )

    if not job_owner:
        language = get_user_language(user_id)
        await safe_send_message(context.bot, chat_id=get_chat_id(query),
                                text="❌ Доступ запрещен")
        return

    applications = db_execute(
        """SELECT a.id, s.fullname, j.title, a.status, a.applied_at
           FROM applications a
           JOIN students s ON a.student_id = s.id
           JOIN jobs j ON a.job_id = j.id
           WHERE j.id = ?
           ORDER BY a.applied_at DESC""",
        (job_id,), fetch=True
    )

    chat_id = get_chat_id(query)
    language = get_user_language(user_id)

    if not applications:
        text = get_text('no_applications', language)
        await safe_send_message(context.bot, chat_id=chat_id, text=text)
        return

    keyboard = []
    for app_id, fullname, job_title, status, applied_at in applications:
        status_text = get_text(f'status_{status}', language)
        button_text = f"{fullname} - {status_text}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"review_application:{app_id}")])

    keyboard.append([InlineKeyboardButton(get_text('back', language), callback_data=f"view_my_job:{job_id}")])

    text = get_text('your_applications', language) + f" ({len(applications)})"
    await safe_send_message(
        context.bot,
        chat_id=chat_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def callback_toggle_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Activate/deactivate job"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    job_id = int(parts[1])
    action = parts[2]

    user_id = query.from_user.id

    # Проверяем владение вакансией
    job_owner = db_execute(
        "SELECT id FROM jobs WHERE id = ? AND employer_id = (SELECT id FROM employers WHERE user_id = ?)",
        (job_id, user_id), fetch=True
    )

    if not job_owner:
        language = get_user_language(user_id)
        await safe_send_message(context.bot, chat_id=get_chat_id(query),
                                text="❌ Доступ запрещен")
        return

    is_active = 1 if action == 'activate' else 0
    db_execute(
        "UPDATE jobs SET is_active = ? WHERE id = ?",
        (is_active, job_id)
    )

    language = get_user_language(user_id)
    status_text = ("активирована" if action == 'activate' else "деактивирована") if language == 'ru' else \
        ("activated" if action == 'activate' else "deactivated") if language == 'en' else \
            ("белсендірілді" if action == 'activate' else "өшірілді")

    await safe_send_message(
        context.bot,
        chat_id=get_chat_id(query),
        text=f"✅ Вакансия {status_text}"
    )

    # Возвращаемся к просмотру вакансии
    await callback_view_my_job(update, context)


async def callback_back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to main menu"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_type = get_user_type(user_id)
    await show_main_menu(update, context, user_type)


# ------------------ Mode Switching Handlers ------------------
async def callback_switch_to_student(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch employer to student mode"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = get_chat_id(query)
    language = get_user_language(user_id)

    if has_student_profile(user_id):
        await show_main_menu(update, context, 'student')
    else:
        text = "Для использования режима студента необходимо заполнить профиль студента."
        keyboard = [
            [InlineKeyboardButton("📝 Заполнить профиль студента", callback_data="start_student_registration")],
            [InlineKeyboardButton(get_text('back', language), callback_data="back_to_main")]
        ]

        await safe_send_message(
            context.bot,
            chat_id=chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def callback_switch_to_employer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch student to employer mode"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = get_chat_id(query)
    language = get_user_language(user_id)

    if is_employer(user_id):
        await show_main_menu(update, context, 'employer')
    else:
        text = get_text('admin_only', language)
        await safe_send_message(context.bot, chat_id=chat_id, text=text)


# ------------------ Admin Commands ------------------
async def cmd_help_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin help commands"""
    user_id = update.effective_user.id
    chat_id = get_chat_id(update)

    if not is_employer(user_id):
        language = get_user_language(user_id)
        text = get_text('admin_only', language)
        await safe_send_message(context.bot, chat_id=chat_id, text=text)
        return

    language = get_user_language(user_id)
    text = get_text('help_admin_text', language)

    await safe_send_message(
        context.bot,
        chat_id=chat_id,
        text=text,
        parse_mode="Markdown"
    )


async def cmd_my_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show employer's jobs"""
    user_id = update.effective_user.id
    chat_id = get_chat_id(update)

    if not is_employer(user_id):
        language = get_user_language(user_id)
        text = get_text('admin_only', language)
        await safe_send_message(context.bot, chat_id=chat_id, text=text)
        return

    employer_id = get_employer_id(user_id)
    if not employer_id:
        language = get_user_language(user_id)
        text = get_text('no_employer_profile', language)
        await safe_send_message(context.bot, chat_id=chat_id, text=text)
        return

    jobs = db_execute(
        """SELECT id, title, description, salary, requirements, created_at, is_active
           FROM jobs WHERE employer_id = ? ORDER BY created_at DESC""",
        (employer_id,), fetch=True
    )

    language = get_user_language(user_id)

    if not jobs:
        text = get_text('no_jobs', language)
        await safe_send_message(context.bot, chat_id=chat_id, text=text)
        return

    text = "💼 Ваши вакансии:\n\n"
    for job_id, title, description, salary, requirements, created_at, is_active in jobs:
        status = "✅ Активна" if is_active else "❌ Неактивна"
        created = datetime.fromisoformat(created_at).strftime("%d.%m.%Y")
        text += f"🔹 *{title}* ({status})\n"
        text += f"   📅 Создана: {created}\n"
        if salary:
            text += f"   💰 Зарплата: {salary}\n"
        text += f"   🆔 ID: {job_id}\n\n"

    await safe_send_message(
        context.bot,
        chat_id=chat_id,
        text=text,
        parse_mode="Markdown"
    )


async def cmd_list_students(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all students"""
    user_id = update.effective_user.id
    chat_id = get_chat_id(update)

    if not is_employer(user_id):
        language = get_user_language(user_id)
        text = get_text('admin_only', language)
        await safe_send_message(context.bot, chat_id=chat_id, text=text)
        return

    students = db_execute(
        """SELECT s.fullname, s.phone, s.course, s.major, s.about, s.created_at
           FROM students s ORDER BY s.created_at DESC""",
        fetch=True
    )

    language = get_user_language(user_id)

    if not students:
        text = get_text('no_students', language)
        await safe_send_message(context.bot, chat_id=chat_id, text=text)
        return

    text = get_text('students_list', language) + "\n\n"
    for fullname, phone, course, major, about, created_at in students:
        created = datetime.fromisoformat(created_at).strftime("%d.%m.%Y")
        text += f"👤 *{fullname}*\n"
        text += f"   📞 {phone}\n"
        text += f"   🎓 {course} курс, {major}\n"
        text += f"   📅 Зарегистрирован: {created}\n"
        if about:
            text += f"   📝 {about}\n"
        text += "\n"

    # Split long messages
    if len(text) > 4096:
        parts = [text[i:i + 4096] for i in range(0, len(text), 4096)]
        for part in parts:
            await safe_send_message(
                context.bot,
                chat_id=chat_id,
                text=part,
                parse_mode="Markdown"
            )
    else:
        await safe_send_message(
            context.bot,
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown"
        )


async def cmd_export_applications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export applications to Excel file"""
    user_id = update.effective_user.id
    chat_id = get_chat_id(update)

    if not is_employer(user_id):
        language = get_user_language(user_id)
        text = get_text('admin_only', language)
        await safe_send_message(context.bot, chat_id=chat_id, text=text)
        return

    # Get employer's applications
    employer_id = get_employer_id(user_id)
    if not employer_id:
        language = get_user_language(user_id)
        text = get_text('no_employer_profile', language)
        await safe_send_message(context.bot, chat_id=chat_id, text=text)
        return

    applications = db_execute(
        """SELECT a.id, s.fullname, s.phone, s.course, s.major, s.about,
                  j.title, e.company_name, a.status, a.applied_at, a.reviewed_at
           FROM applications a
           JOIN students s ON a.student_id = s.id
           JOIN jobs j ON a.job_id = j.id
           JOIN employers e ON j.employer_id = e.id
           WHERE j.employer_id = ?
           ORDER BY a.applied_at DESC""",
        (employer_id,), fetch=True
    )

    language = get_user_language(user_id)

    if not applications:
        text = get_text('no_applications', language)
        await safe_send_message(context.bot, chat_id=chat_id, text=text)
        return

    # Create DataFrame
    data = []
    for app in applications:
        (app_id, fullname, phone, course, major, about,
         job_title, company, status, applied_at, reviewed_at) = app

        status_text = get_text(f'status_{status}', 'ru')
        applied_date = datetime.fromisoformat(applied_at).strftime("%Y-%m-%d %H:%M")
        reviewed_date = datetime.fromisoformat(reviewed_at).strftime("%Y-%m-%d %H:%M") if reviewed_at else ""

        data.append({
            "ID": app_id,
            "ФИО": fullname,
            "Телефон": phone,
            "Курс": course,
            "Специальность": major,
            "О себе": about,
            "Вакансия": job_title,
            "Компания": company,
            "Статус": status_text,
            "Подана": applied_date,
            "Рассмотрена": reviewed_date
        })

    df = pd.DataFrame(data)

    # Create Excel file
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Applications")
    bio.seek(0)

    filename = f"applications_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    try:
        await context.bot.send_document(
            chat_id=chat_id,
            document=InputFile(bio, filename=filename),
            caption=f"📊 Экспорт заявок ({len(df)} записей)"
        )
    except Exception as e:
        logger.error(f"Error sending export file: {e}")
        language = get_user_language(user_id)
        text = get_text('error_export', language)
        await safe_send_message(context.bot, chat_id=chat_id, text=text)


async def handle_quick_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quick delete commands"""
    user_id = update.effective_user.id
    chat_id = get_chat_id(update)

    if not is_employer(user_id):
        language = get_user_language(user_id)
        text = get_text('admin_only', language)
        await safe_send_message(context.bot, chat_id=chat_id, text=text)
        return

    command = update.message.text
    language = get_user_language(user_id)

    try:
        if command.startswith('/delete_job_'):
            job_id = int(command.split('_')[-1])
            # Delete job and related applications
            db_execute("DELETE FROM applications WHERE job_id = ?", (job_id,))
            db_execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            text = f"✅ Вакансия #{job_id} удалена"

        elif command.startswith('/delete_application_'):
            app_id = int(command.split('_')[-1])
            db_execute("DELETE FROM applications WHERE id = ?", (app_id,))
            text = f"✅ Заявка #{app_id} удалена"

        else:
            text = "❌ Неверная команда"

        await safe_send_message(context.bot, chat_id=chat_id, text=text)

    except Exception as e:
        logger.error(f"Error in quick delete: {e}")
        await safe_send_message(context.bot, chat_id=chat_id, text="❌ Ошибка при удалении")


# ------------------ Cancel Handler ------------------
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel any conversation"""
    user_id = update.effective_user.id
    user_type = get_user_type(user_id)

    await show_main_menu(update, context, user_type)
    context.user_data.clear()
    return ConversationHandler.END


# ------------------ Main ------------------
def main():
    init_db()
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set")
        return

    # Fix for Event loop is closed error
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .connection_pool_size(8)
        .read_timeout(60.0)
        .build()
    )

    # Add command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help_admin", cmd_help_admin))
    app.add_handler(CommandHandler("my_jobs", cmd_my_jobs))
    app.add_handler(CommandHandler("list_students", cmd_list_students))
    app.add_handler(CommandHandler("export_applications", cmd_export_applications))

    # Quick delete handlers
    app.add_handler(MessageHandler(filters.Regex(r'^/delete_job_\d+$'), handle_quick_delete))
    app.add_handler(MessageHandler(filters.Regex(r'^/delete_application_\d+$'), handle_quick_delete))

    # Separate conversation handlers for different flows
    student_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_student_registration, pattern=r"^student_register$"),
            CallbackQueryHandler(start_student_registration, pattern=r"^start_student_registration$")
        ],
        states={
            STUDENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, student_name)],
            STUDENT_PHONE: [MessageHandler((filters.CONTACT | filters.TEXT) & ~filters.COMMAND, student_phone)],
            STUDENT_COURSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, student_course)],
            STUDENT_MAJOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, student_major)],
            STUDENT_ABOUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, student_about)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_chat=True,
        per_user=True,
    )

    employer_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(callback_create_job, pattern=r"^create_job$")],
        states={
            EMPLOYER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, employer_name)],
            EMPLOYER_PHONE: [MessageHandler((filters.CONTACT | filters.TEXT) & ~filters.COMMAND, employer_phone)],
            JOB_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, job_title)],
            JOB_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, job_description)],
            JOB_SALARY: [MessageHandler(filters.TEXT & ~filters.COMMAND, job_salary)],
            JOB_REQUIREMENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, job_requirements)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_chat=True,
        per_user=True,
    )

    app.add_handler(student_conv_handler)
    app.add_handler(employer_conv_handler)

    # Callback query handlers
    app.add_handler(CallbackQueryHandler(callback_browse_jobs, pattern=r"^browse_jobs$"))
    app.add_handler(CallbackQueryHandler(callback_view_job, pattern=r"^view_job:"))
    app.add_handler(CallbackQueryHandler(callback_apply_job, pattern=r"^apply_job:"))
    app.add_handler(CallbackQueryHandler(callback_view_applications, pattern=r"^view_applications$"))
    app.add_handler(CallbackQueryHandler(callback_review_application, pattern=r"^review_application:"))
    app.add_handler(CallbackQueryHandler(callback_accept_application, pattern=r"^accept_application:"))
    app.add_handler(CallbackQueryHandler(callback_reject_application, pattern=r"^reject_application:"))

    # Student handlers
    app.add_handler(CallbackQueryHandler(callback_my_applications, pattern=r"^my_applications$"))
    app.add_handler(CallbackQueryHandler(callback_student_profile, pattern=r"^student_profile$"))
    app.add_handler(CallbackQueryHandler(callback_edit_student_profile, pattern=r"^edit_student_profile$"))

    # My Jobs handlers (employer)
    app.add_handler(CallbackQueryHandler(callback_my_jobs, pattern=r"^my_jobs$"))
    app.add_handler(CallbackQueryHandler(callback_view_my_job, pattern=r"^view_my_job:"))
    app.add_handler(CallbackQueryHandler(callback_view_job_applications, pattern=r"^view_job_applications:"))
    app.add_handler(CallbackQueryHandler(callback_toggle_job, pattern=r"^toggle_job:"))
    app.add_handler(CallbackQueryHandler(callback_back_to_main, pattern=r"^back_to_main$"))

    # Mode switching handlers
    app.add_handler(CallbackQueryHandler(callback_switch_to_student, pattern=r"^switch_to_student$"))
    app.add_handler(CallbackQueryHandler(callback_switch_to_employer, pattern=r"^switch_to_employer$"))

    # Employer browsing jobs handlers
    app.add_handler(CallbackQueryHandler(callback_browse_jobs_as_employer, pattern=r"^browse_jobs_as_employer$"))
    app.add_handler(CallbackQueryHandler(callback_view_job_info, pattern=r"^view_job_info:"))

    # Language change handlers
    app.add_handler(CallbackQueryHandler(callback_change_language, pattern=r"^change_language$"))
    app.add_handler(CallbackQueryHandler(callback_set_language, pattern=r"^set_lang:"))
    app.add_handler(CallbackQueryHandler(callback_set_language, pattern=r"^change_lang:"))

    # Initial language selection handler
    app.add_handler(CallbackQueryHandler(callback_set_language, pattern=r"^set_lang:"))

    logger.info("Job search bot started")

    try:
        app.run_polling()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error running bot: {e}")
    finally:
        logger.info("Bot shutdown complete")


if __name__ == "__main__":
    main()