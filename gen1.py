import streamlit as st
import anthropic
from io import StringIO
import json
import time
import PyPDF2
import docx2txt

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
        st.error("Файл 'examples.json' не найден. Убедитесь, что он находится в той же директории, что и приложение.")
        return {}
    except json.JSONDecodeError:
        st.error("Ошибка при чтении файла 'examples.json'. Проверьте формат JSON.")
        return {}

# Инициализация клиента Anthropic Claude
@st.cache_resource
def init_claude_client():
    api_key = st.secrets["ANTHROPIC_API_KEY"]
    return anthropic.Anthropic(api_key=api_key)

# Функция для извлечения ключевых фактов из описания дела
def extract_key_facts(client, text):
    prompt = f"""
Извлеките ключевые факты и обстоятельства из следующего описания дела:

{text}

Пожалуйста, предоставьте список ключевых фактов в виде пунктов.
"""

    response = client.messages.create(
        model="claude-3-sonnet-20240229",
        max_tokens=4000,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    key_facts = response.content[0].text
    return key_facts

# Функция для генерации судебного решения
def generate_judgment(client, key_facts, examples):
    example = list(examples.values())[0]
    example_descriptive = example['descriptive']['content']
    example_reasoning = example['reasoning']['content']
    example_operative = example['operative']['content']

    prompt = f"""
На основе следующих ключевых фактов сгенерируйте судебное решение, разделенное на три части: описательная, мотивировочная и резолютивная. Используйте стиль и структуру предоставленных примеров.

Ключевые факты:
{key_facts}

Пример описательной части:
{example_descriptive}

Пример мотивировочной части:
{example_reasoning}

Пример резолютивной части:
{example_operative}

Сгенерируйте судебное решение для данного дела.
"""

    response = client.messages.create(
        model="claude-3-sonnet-20240229",
        max_tokens=4000,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    generated_judgment = response.content[0].text
    return generated_judgment

# Основная функция приложения
def main():
    st.title("Генератор Судебных Решений")

    # Инициализация клиента
    claude_client = init_claude_client()

    # Загрузка примеров судебных решений
    examples = load_judgment_examples()

    if not examples:
        st.warning("Примеры судебных решений не загружены. Генерация решения может быть менее точной.")
        return

    # Загрузка описания дела
    st.header("Загрузите описание дела или документ")
    uploaded_file = st.file_uploader("Выберите файл", type=["txt", "pdf", "docx"])
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
            st.error("Неподдерживаемый формат файла.")
            return
    else:
        case_text = st.text_area("Или введите описание дела здесь:")

    if not case_text:
        st.warning("Пожалуйста, предоставьте описание дела для анализа.")
        return

    # Извлечение ключевых фактов
    with st.spinner('Извлечение ключевых фактов...'):
        try:
            key_facts = extract_key_facts(claude_client, case_text)
        except Exception as e:
            st.error(f"Ошибка при извлечении ключевых фактов: {e}")
            return

    if key_facts:
        st.subheader("Извлеченные ключевые факты")
        st.write(key_facts)
    else:
        st.error("Не удалось извлечь ключевые факты.")
        return

    # Генерация судебного решения
    if st.button("Сгенерировать судебное решение"):
        with st.spinner('Генерация судебного решения...'):
            try:
                generated_judgment = generate_judgment(claude_client, key_facts, examples)
            except Exception as e:
                st.error(f"Ошибка при генерации судебного решения: {e}")
                return

        if generated_judgment:
            st.subheader("Сгенерированное судебное решение")
            st.write(generated_judgment)
        else:
            st.error("Не удалось сгенерировать судебное решение.")

# Запуск приложения
if __name__ == "__main__":
    main()