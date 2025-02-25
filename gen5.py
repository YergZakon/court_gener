import streamlit as st
import anthropic
from io import StringIO
import json
import time
import PyPDF2
import docx2txt
import os
import re
from datetime import datetime

# Настройка состояний сессии
if 'history' not in st.session_state:
    st.session_state.history = []
if 'current_judgment' not in st.session_state:
    st.session_state.current_judgment = None
if 'language' not in st.session_state:
    st.session_state.language = 'ru'

# Многоязычные тексты
translations = {
    'ru': {
        'title': 'Генератор Судебных Решений',
        'upload_header': 'Загрузите описание дела или документ',
        'file_uploader': 'Выберите файл',
        'text_area': 'Или введите описание дела здесь:',
        'settings': 'Настройки',
        'temperature': 'Температура (креативность):',
        'low_temp': 'Низкая',
        'high_temp': 'Высокая',
        'extract_button': 'Извлечь ключевые факты',
        'key_facts': 'Извлеченные ключевые факты',
        'edit_facts': 'Редактировать факты',
        'generate_button': 'Сгенерировать судебное решение',
        'results_header': 'Сгенерированное судебное решение',
        'descriptive': 'Описательная часть',
        'reasoning': 'Мотивировочная часть',
        'operative': 'Резолютивная часть',
        'save_button': 'Сохранить решение',
        'history_tab': 'История',
        'no_history': 'История пуста',
        'error_api': 'Ошибка API: ',
        'error_file': 'Неподдерживаемый формат файла.',
        'warning_examples': 'Примеры судебных решений не загружены. Генерация решения может быть менее точной.',
        'warning_case': 'Пожалуйста, предоставьте описание дела для анализа.',
        'error_facts': 'Не удалось извлечь ключевые факты.',
        'error_judgment': 'Не удалось сгенерировать судебное решение.',
        'progress_facts': 'Извлечение ключевых фактов...',
        'progress_judgment': 'Генерация судебного решения...'
    },
    'en': {
        'title': 'Court Judgment Generator',
        'upload_header': 'Upload case description or document',
        'file_uploader': 'Choose a file',
        'text_area': 'Or enter case description here:',
        'settings': 'Settings',
        'temperature': 'Temperature (creativity):',
        'low_temp': 'Low',
        'high_temp': 'High',
        'extract_button': 'Extract key facts',
        'key_facts': 'Extracted key facts',
        'edit_facts': 'Edit facts',
        'generate_button': 'Generate court judgment',
        'results_header': 'Generated court judgment',
        'descriptive': 'Descriptive part',
        'reasoning': 'Reasoning part',
        'operative': 'Operative part',
        'save_button': 'Save judgment',
        'history_tab': 'History',
        'no_history': 'History is empty',
        'error_api': 'API Error: ',
        'error_file': 'Unsupported file format.',
        'warning_examples': 'Court judgment examples not loaded. Judgment generation may be less accurate.',
        'warning_case': 'Please provide a case description for analysis.',
        'error_facts': 'Failed to extract key facts.',
        'error_judgment': 'Failed to generate court judgment.',
        'progress_facts': 'Extracting key facts...',
        'progress_judgment': 'Generating court judgment...'
    }
}

# Функция для получения текста на выбранном языке
def t(key, nested_key=None):
    if nested_key:
        return translations[st.session_state.language][key][nested_key]
    return translations[st.session_state.language][key]

# Функция для создания эффекта печати (опционально)
def typewriter(text, speed=0.03):
    container = st.empty()
    displayed_text = ""
    for char in text:
        displayed_text += char
        container.markdown(displayed_text)
        time.sleep(speed)
    return container

# Функция для загрузки примеров судебных решений из файла JSON
@st.cache_data
def load_judgment_examples():
    try:
        with open('examples.json', 'r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}

# Инициализация клиента Anthropic Claude
@st.cache_resource
def init_claude_client():
    # Пытаемся получить API ключ из секретов Streamlit
    try:
        api_key = st.secrets["ANTHROPIC_API_KEY"]
        return anthropic.Anthropic(api_key=api_key)
    except Exception as e:
        st.error(f"Не удалось получить API ключ из secrets: {str(e)}")
        st.info("Для правильной работы приложения, добавьте API ключ Anthropic в secrets Streamlit.")
        return None

# Функция для повторных попыток API запросов
def retry_api_call(func, *args, max_retries=3, **kwargs):
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except (anthropic.APIConnectionError, anthropic.RateLimitError) as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Экспоненциальная задержка
                continue
            raise e
        except anthropic.AuthenticationError:
            # Сразу пробрасываем ошибки аутентификации без повторных попыток
            raise

# Функция для извлечения ключевых фактов из описания дела
def extract_key_facts(client, text, language):
    lang_str = "Russian" if language == 'ru' else "English"
    prompt = f"""
Extract key facts and circumstances from the following case description in {lang_str}:

{text}

Please provide a list of key facts as bullet points in {lang_str}.
"""

    response = retry_api_call(
        client.messages.create,
        model="claude-3-5-sonnet-20241022",
        max_tokens=4000,
        temperature=0.3,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    key_facts = response.content[0].text
    return key_facts

# Функция для разделения текста решения на части
def split_judgment_parts(text):
    parts = {
        'descriptive': '',
        'reasoning': '',
        'operative': ''
    }
    
    # Регулярные выражения для поиска частей на русском и английском
    patterns = {
        'descriptive': r'(ОПИСАТЕЛЬНАЯ ЧАСТЬ|DESCRIPTIVE PART)[\s\S]+?(?=(МОТИВИРОВОЧНАЯ ЧАСТЬ|REASONING PART|$))',
        'reasoning': r'(МОТИВИРОВОЧНАЯ ЧАСТЬ|REASONING PART)[\s\S]+?(?=(РЕЗОЛЮТИВНАЯ ЧАСТЬ|OPERATIVE PART|$))',
        'operative': r'(РЕЗОЛЮТИВНАЯ ЧАСТЬ|OPERATIVE PART)[\s\S]+'
    }
    
    for part, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            parts[part] = match.group(0).strip()
    
    # Если не удалось разделить, возвращаем весь текст в описательной части
    if not any(parts.values()):
        parts['descriptive'] = text
        
    return parts

# Функция для генерации судебного решения
def generate_judgment(client, key_facts, examples, temperature, language):
    # Выбор нескольких примеров (до 3) для большего разнообразия
    example_list = list(examples.values())
    examples_to_use = example_list[:min(3, len(example_list))]
    
    examples_text = ""
    for i, example in enumerate(examples_to_use):
        examples_text += f"""
Пример {i+1} описательной части:
{example['descriptive']['content']}

Пример {i+1} мотивировочной части:
{example['reasoning']['content']}

Пример {i+1} резолютивной части:
{example['operative']['content']}

"""
    
    lang_str = "Russian" if language == 'ru' else "English"
    headers = {
        'ru': ['ОПИСАТЕЛЬНАЯ ЧАСТЬ', 'МОТИВИРОВОЧНАЯ ЧАСТЬ', 'РЕЗОЛЮТИВНАЯ ЧАСТЬ'],
        'en': ['DESCRIPTIVE PART', 'REASONING PART', 'OPERATIVE PART']
    }

    prompt = f"""
Generate a court judgment in {lang_str} based on the following key facts. Divide the judgment into three distinct parts: descriptive, reasoning, and operative, using the style and structure of the provided examples.

Key facts:
{key_facts}

{examples_text}

Important: Clearly separate each part with headers: {", ".join(headers[language])}

Make sure each part is comprehensive and follows legal writing standards. The judgment should be well-reasoned and cover all aspects of the case.
"""

    response = retry_api_call(
        client.messages.create,
        model="claude-3-5-sonnet-20241022",
        max_tokens=4000,
        temperature=temperature,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    generated_judgment = response.content[0].text
    return generated_judgment

# Функция для сохранения решения в историю
def save_to_history(judgment, key_facts):
    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")
    judgment_parts = split_judgment_parts(judgment)
    
    # Создаем краткое название на основе первых 50 символов описательной части
    title = judgment_parts['descriptive'][:50] + "..." if len(judgment_parts['descriptive']) > 50 else judgment_parts['descriptive']
    
    history_item = {
        'timestamp': timestamp,
        'title': title,
        'judgment': judgment,
        'key_facts': key_facts,
        'parts': judgment_parts
    }
    
    st.session_state.history.append(history_item)

# Функция для отображения прогресс-бара с этапами
def progress_bar_with_stages(stages, current_stage):
    total_stages = len(stages)
    current_idx = stages.index(current_stage)
    progress = current_idx / (total_stages - 1)
    
    st.progress(progress)
    cols = st.columns(total_stages)
    
    for i, stage in enumerate(stages):
        with cols[i]:
            if i < current_idx:
                st.markdown(f"✅ {stage}")
            elif i == current_idx:
                st.markdown(f"🔄 **{stage}**")
            else:
                st.markdown(f"⏳ {stage}")

# Основная функция приложения
def main():
    # Переключатель языка в боковой панели
    with st.sidebar:
        language_option = st.selectbox(
            "Language / Язык",
            options=["Русский"],
            index=0 if st.session_state.language == 'ru' else 1
        )
        st.session_state.language = 'ru' if language_option == "Русский" else 'en'
        
        st.divider()
        
        # Информация о приложении
        st.info("v1.3.0 - 2025")

    st.title(t('title'))

    # Загрузка примеров судебных решений
    examples = load_judgment_examples()

    if not examples:
        st.warning(t('warning_examples'))
        
    # Инициализация клиента
    try:
        claude_client = init_claude_client()
        if claude_client is None:
            st.error("""
            ### API Key Required
            
            Для работы приложения требуется ключ API Anthropic. Добавьте его в secrets Streamlit.
            Подробности в документации Streamlit: https://docs.streamlit.io/streamlit-community-cloud/deploy-your-app/secrets-management
            """)
            st.stop()  # Останавливаем выполнение приложения до настройки ключа
    except Exception as e:
        st.error(f"Failed to initialize Claude client: {str(e)}")
        st.stop()

    # Создание вкладок для организации интерфейса
    tabs = st.tabs(["📝 Ввод", "⚙️ Настройки", "📋 Результаты", "📚 История"])
    
    with tabs[0]:  # Вкладка "Ввод"
        st.header(t('upload_header'))
        uploaded_file = st.file_uploader(t('file_uploader'), type=["txt", "pdf", "docx"])
        case_text = ""

        if uploaded_file is not None:
            if uploaded_file.type == "application/pdf":
                pdf_reader = PyPDF2.PdfReader(uploaded_file)
                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    case_text += page.extract_text()
            elif uploaded_file.type == "text/plain":
                case_text = uploaded_file.read().decode('utf-8')
            elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                case_text = docx2txt.process(uploaded_file)
            else:
                st.error(t('error_file'))
        else:
            case_text = st.text_area(t('text_area'), height=300)

        if st.button(t('extract_button')) and case_text:
            stages = ["Upload", "Extract Facts", "Generate", "Save"]
            current_stage = "Extract Facts"
            progress_bar_with_stages(stages, current_stage)
            
            with st.spinner(t('progress_facts')):
                try:
                    # Получаем выбранную модель со вкладки настроек
                    selected_model = st.session_state.get('selected_model', 'claude-3-5-sonnet-20241022')
                    key_facts = extract_key_facts(claude_client, case_text, st.session_state.language)
                    st.session_state.key_facts = key_facts
                    st.success("✅ " + t('key_facts'))
                    st.rerun()
                except Exception as e:
                    st.error(f"{t('error_api')}{str(e)}")
    
    with tabs[1]:  # Вкладка "Настройки"
        st.header(t('settings'))
        
        # Настройка температуры
        temperature = st.slider(
            t('temperature'),
            min_value=0.0,
            max_value=1.0,
            value=0.7,
            step=0.1,
            format="%.1f",
            help=f"{t('low_temp')} (0.0) → {t('high_temp')} (1.0)"
        )
        st.session_state.temperature = temperature
    
    with tabs[2]:  # Вкладка "Результаты"
        if 'key_facts' in st.session_state:
            st.subheader(t('key_facts'))
            key_facts = st.text_area(
                t('edit_facts'),
                value=st.session_state.key_facts,
                height=200
            )
            
            if st.button(t('generate_button')):
                # Проверяем доступность клиента
                if claude_client is None:
                    st.error("Claude API client is not initialized. Please check your API key in the sidebar.")
                    return
                    
                stages = ["Upload", "Extract Facts", "Generate", "Save"]
                current_stage = "Generate"
                progress_bar_with_stages(stages, current_stage)
                
                with st.spinner(t('progress_judgment')):
                    try:
                        temperature = st.session_state.get('temperature', 0.7)
                        
                        generated_judgment = generate_judgment(
                            claude_client, 
                            key_facts, 
                            examples, 
                            temperature,
                            st.session_state.language
                        )
                        
                        # Разделяем на части
                        judgment_parts = split_judgment_parts(generated_judgment)
                        st.session_state.current_judgment = {
                            'full_text': generated_judgment,
                            'parts': judgment_parts
                        }
                        
                        # Сохраняем в историю
                        save_to_history(generated_judgment, key_facts)
                        
                        st.success("✅ " + t('results_header'))
                        st.rerun()
                    except anthropic.AuthenticationError:
                        st.error("Ошибка аутентификации API. Пожалуйста, проверьте ваш API ключ в боковой панели.")
                    except anthropic.RateLimitError:
                        st.error("Превышен лимит запросов API. Пожалуйста, подождите несколько минут и попробуйте снова.")
                    except anthropic.APIStatusError as e:
                        st.error(f"Ошибка API статуса: {e.status_code} - {e.message}")
                    except Exception as e:
                        st.error(f"{t('error_api')}{str(e)}")
            
            # Отображение результата
            if 'current_judgment' in st.session_state and st.session_state.current_judgment:
                st.header(t('results_header'))
                
                # Создаем вкладки для каждой части решения
                result_tabs = st.tabs([t('descriptive'), t('reasoning'), t('operative')])
                
                with result_tabs[0]:
                    st.markdown(st.session_state.current_judgment['parts']['descriptive'])
                
                with result_tabs[1]:
                    st.markdown(st.session_state.current_judgment['parts']['reasoning'])
                
                with result_tabs[2]:
                    st.markdown(st.session_state.current_judgment['parts']['operative'])
                
                # Кнопка для скачивания полного текста
                full_text = st.session_state.current_judgment['full_text']
                st.download_button(
                    label="📥 " + t('save_button'),
                    data=full_text,
                    file_name=f"judgment_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain"
                )
    
    with tabs[3]:  # Вкладка "История"
        st.header(t('history_tab'))
        
        if not st.session_state.history:
            st.info(t('no_history'))
        else:
            # Отображаем историю в обратном хронологическом порядке
            for i, item in enumerate(reversed(st.session_state.history)):
                with st.expander(f"📄 {item['timestamp']} - {item['title']}"):
                    # Создаем вкладки для каждой части решения
                    history_tabs = st.tabs([t('descriptive'), t('reasoning'), t('operative')])
                    
                    with history_tabs[0]:
                        st.markdown(item['parts']['descriptive'])
                    
                    with history_tabs[1]:
                        st.markdown(item['parts']['reasoning'])
                    
                    with history_tabs[2]:
                        st.markdown(item['parts']['operative'])
                    
                    # Кнопка для скачивания
                    st.download_button(
                        label="📥 " + t('save_button'),
                        data=item['judgment'],
                        file_name=f"judgment_{item['timestamp'].replace('.', '').replace(':', '').replace(' ', '_')}.txt",
                        mime="text/plain"
                    )

# Запуск приложения
if __name__ == "__main__":
    main()