import os
import re
import httpx
import streamlit as st
from typing import Optional

# Configuration
# Use internal Docker service names when running in containers
API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://api-gateway:8000")
ADMIN_API_TOKEN = os.getenv("ADMIN_API_TOKEN", "")
EMAIL_NOTIFIER_URL = os.getenv("EMAIL_NOTIFIER_URL", "http://email-notifier:8003")
# SMTP email is for SENDING emails (configured in .env)
SMTP_USER = os.getenv("SMTP_USER", "")

st.set_page_config(page_title="Запуск бота", layout="wide")
st.title("🤖 AI Scrum Master • Запуск бота для встречи")


def parse_google_meet_id(url: str) -> Optional[str]:
    """Extract meeting ID from Google Meet URL."""
    # Patterns: 
    # https://meet.google.com/xxx-yyyy-zzz
    # meet.google.com/xxx-yyyy-zzz
    # xxx-yyyy-zzz
    patterns = [
        r'meet\.google\.com/([a-z]{3}-[a-z]{4}-[a-z]{3})',
        r'([a-z]{3}-[a-z]{4}-[a-z]{3})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url.lower())
        if match:
            return match.group(1)
    return None


def get_or_create_user(email: str) -> Optional[dict]:
    """Get or create user and return user data."""
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{API_GATEWAY_URL}/admin/users",
                headers={
                    "Content-Type": "application/json",
                    "X-Admin-API-Key": ADMIN_API_TOKEN
                },
                json={
                    "email": email,
                    "max_concurrent_bots": 2
                },
                timeout=10.0
            )
            if response.status_code in [200, 201]:
                return response.json()
            else:
                st.error(f"Ошибка создания пользователя: {response.status_code} - {response.text}")
                return None
    except Exception as e:
        st.error(f"Ошибка при обращении к API: {e}")
        return None


def create_user_token(user_id: int) -> Optional[str]:
    """Create API token for user."""
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{API_GATEWAY_URL}/admin/users/{user_id}/tokens",
                headers={
                    "X-Admin-API-Key": ADMIN_API_TOKEN
                },
                timeout=10.0
            )
            if response.status_code == 201:
                token_data = response.json()
                return token_data.get("token")
            else:
                st.error(f"Ошибка создания токена: {response.status_code} - {response.text}")
                return None
    except Exception as e:
        st.error(f"Ошибка при создании токена: {e}")
        return None


def launch_bot(meeting_id: str, user_token: str, bot_name: str = "Scrum Recorder") -> Optional[dict]:
    """Launch bot for meeting."""
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{API_GATEWAY_URL}/bots",
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": user_token
                },
                json={
                    "platform": "google_meet",
                    "native_meeting_id": meeting_id,
                    "display_name": bot_name
                },
                timeout=30.0
            )
            if response.status_code == 201:
                return response.json()
            else:
                st.error(f"Ошибка запуска бота: {response.status_code} - {response.text}")
                return None
    except Exception as e:
        st.error(f"Ошибка при запуске бота: {e}")
        return None


def update_email_notifier_config(email: str, user_id: int) -> bool:
    """Update email notifier target email via user data."""
    try:
        # Store email preference in user data via admin API
        # This will be used by email-notifier to send emails
        with httpx.Client() as client:
            response = client.patch(
                f"{API_GATEWAY_URL}/admin/users/{user_id}",
                headers={
                    "Content-Type": "application/json",
                    "X-Admin-API-Key": ADMIN_API_TOKEN
                },
                json={
                    "data": {
                        "notification_email": email
                    }
                },
                timeout=10.0
            )
            if response.status_code == 200:
                return True
            else:
                st.warning(f"Не удалось обновить настройки email: {response.status_code}")
                return False
    except Exception as e:
        st.warning(f"Не удалось обновить настройки email: {e}")
        return False


# Initialize session state
if "user_token" not in st.session_state:
    st.session_state.user_token = None
if "user_email" not in st.session_state:
    st.session_state.user_email = None
if "target_email" not in st.session_state:
    st.session_state.target_email = None

# Main UI
st.markdown("### Шаг 1: Введите данные")

col1, col2 = st.columns(2)

with col1:
    meet_url = st.text_input(
        "🔗 Ссылка на Google Meet",
        placeholder="https://meet.google.com/xxx-yyyy-zzz",
        help="Вставьте полную ссылку на встречу или только ID встречи"
    )

with col2:
    # Use SMTP_USER as default if available, otherwise empty
    default_account_email = st.session_state.user_email or SMTP_USER or ""
    user_email_input = st.text_input(
        "📧 Email для аккаунта",
        value=default_account_email,
        placeholder="your.email@example.com",
        help="Email для создания/поиска вашего аккаунта в системе. Используется для авторизации и управления ботами. По умолчанию используется SMTP_USER из .env файла."
    )

st.markdown("### Шаг 2: Настройки")

col3, col4 = st.columns(2)

with col3:
    bot_name = st.text_input(
        "🤖 Имя бота в встрече",
        value="Scrum Recorder",
        help="Имя, которое будет отображаться в списке участников"
    )

with col4:
    # Default to account email or SMTP_USER
    default_notification_email = st.session_state.target_email or user_email_input or SMTP_USER or ""
    target_email = st.text_input(
        "📬 Email для уведомлений (получатель)",
        value=default_notification_email,
        placeholder="notifications@example.com",
        help="Email, НА КОТОРЫЙ будут отправляться письма с инсайтами (получатель). SMTP_USER из .env используется как ОТПРАВИТЕЛЬ. Если не указан, будет использован email аккаунта."
    )

st.divider()

# Parse meeting ID
meeting_id = None
if meet_url:
    meeting_id = parse_google_meet_id(meet_url)
    if meeting_id:
        st.success(f"✅ ID встречи: `{meeting_id}`")
    else:
        st.error("❌ Не удалось распознать ID встречи. Проверьте формат ссылки.")
else:
    st.info("👆 Введите ссылку на Google Meet встречу")

# Launch button
if st.button("🚀 Запустить бота", type="primary", disabled=not (meeting_id and user_email_input)):
    if not ADMIN_API_TOKEN:
        st.error("❌ ADMIN_API_TOKEN не настроен. Обратитесь к администратору.")
        st.stop()
    
    if not meeting_id:
        st.error("❌ Не удалось распознать ID встречи")
        st.stop()
    
    if not user_email_input:
        st.error("❌ Введите ваш email")
        st.stop()
    
    # Progress bar
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Step 1: Get or create user
    status_text.text("📝 Создание/поиск пользователя...")
    progress_bar.progress(20)
    user_data = get_or_create_user(user_email_input)
    
    if not user_data:
        st.error("❌ Не удалось создать/найти пользователя")
        st.stop()
    
    user_id = user_data.get("id")
    st.session_state.user_email = user_email_input
    
    # Step 2: Get or create token
    status_text.text("🔑 Получение токена доступа...")
    progress_bar.progress(40)
    
    # Try to get existing token or create new one
    user_token = st.session_state.user_token
    if not user_token:
        user_token = create_user_token(user_id)
        if user_token:
            st.session_state.user_token = user_token
    
    if not user_token:
        st.error("❌ Не удалось получить токен доступа")
        st.stop()
    
    # Step 3: Update email notifier config
    if target_email:
        status_text.text("📧 Настройка email уведомлений...")
        progress_bar.progress(60)
        st.session_state.target_email = target_email
        if update_email_notifier_config(target_email, user_id):
            st.info(f"📬 Уведомления будут отправляться на: {target_email}")
        else:
            st.warning(f"⚠️ Не удалось сохранить настройки email, но бот будет запущен")
    
    # Step 4: Launch bot
    status_text.text("🚀 Запуск бота...")
    progress_bar.progress(80)
    bot_response = launch_bot(meeting_id, user_token, bot_name)
    
    if bot_response:
        progress_bar.progress(100)
        status_text.text("✅ Бот успешно запущен!")
        
        meeting_id_db = bot_response.get("id")
        status = bot_response.get("status")
        
        st.success(f"""
        ### ✅ Бот запущен успешно!
        
        - **ID встречи в системе:** {meeting_id_db}
        - **Статус:** {status}
        - **Платформа:** Google Meet
        - **ID встречи:** {meeting_id}
        """)
        
        st.info("""
        💡 **Что дальше?**
        - Бот присоединится к встрече автоматически
        - Транскрипция начнется после начала встречи
        - После завершения встречи вы получите email с инсайтами (если указан email)
        - Просмотрите результаты в разделе "Инсайты"
        """)
        
        # Show monitoring options
        with st.expander("📊 Мониторинг статуса"):
            st.code(f"""
# Проверить статус через API:
curl -H "X-API-Key: {user_token[:20]}..." \\
     http://localhost:18056/bots/{meeting_id_db}

# Или посмотреть логи:
docker compose logs -f bot-manager
docker compose logs -f hackathon-bot
            """)
    else:
        progress_bar.progress(0)
        status_text.text("❌ Ошибка запуска бота")
        st.error("Не удалось запустить бота. Проверьте логи и попробуйте снова.")

# Sidebar with info
with st.sidebar:
    st.header("ℹ️ Информация")
    st.markdown("""
    ### Как это работает:
    
    1. **Введите ссылку** на Google Meet встречу
    2. **Укажите email для аккаунта** - используется для создания/поиска вашего аккаунта в системе (по умолчанию берется из SMTP_USER в .env)
    3. **Настройте email для уведомлений** (опционально) - куда отправлять письма с инсайтами (получатель). Если не указан, используется email аккаунта
    
    ### Важно про email:
    
    - **SMTP_USER в .env** = email для ОТПРАВКИ писем (отправитель, уже настроен)
    - **Email для аккаунта** = ваш аккаунт в системе (по умолчанию = SMTP_USER)
    - **Email для уведомлений** = куда ПРИХОДЯТ письма (получатель, может отличаться)
    
    4. **Запустите бота** - он присоединится к встрече
    
    ### Что делает бот:
    
    - ✅ Присоединяется к встрече
    - ✅ Записывает транскрипцию в реальном времени
    - ✅ Анализирует встречу с помощью AI
    - ✅ Отправляет email с инсайтами после завершения
    
    ### Требования:
    
    - Встреча должна быть активна или запланирована
    - Бот должен быть допущен в встречу (если требуется)
    - У вас должен быть доступ к встрече
    """)
    
    if st.session_state.user_token:
        st.success("✅ Авторизован")
        st.caption(f"Email: {st.session_state.user_email}")
        if st.button("🔄 Сбросить токен"):
            st.session_state.user_token = None
            st.rerun()

