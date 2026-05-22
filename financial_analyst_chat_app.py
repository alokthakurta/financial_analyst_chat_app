import streamlit as st
import dataikuapi
import pandas as pd
import yaml
import json

# --- SECURE CONFIGURATION ---
DSS_HOST = st.secrets["DSS_HOST"]
DSS_API_KEY = st.secrets["DSS_API_KEY"]
PROJECT_KEY = st.secrets["PROJECT_KEY"]
FOLDER_ID = st.secrets["FOLDER_ID"]
LLM_ID = st.secrets["LLM_ID"]
CONNECTION_NAME = st.secrets["CONNECTION_NAME"]

# Initialize External Client
client = dataikuapi.DSSClient(DSS_HOST, DSS_API_KEY)
project = client.get_project(PROJECT_KEY)

# --- DYNAMIC DATA LOADING (EXTERNAL) ---
def load_latest_ontology():
    try:
        folder = project.get_managed_folder(FOLDER_ID)
        file_stream = folder.get_file("ontology.yaml")
        ontology_data = yaml.safe_load(file_stream.content)
        return ontology_data
    except Exception as e:
        st.error(f"Error loading ontology: {e}")
        return None

# --- LLM INTEGRATION (EXTERNAL) ---
def generate_sql_and_description(question, ontology):
    """Calls the LLM to generate SQL, a description, and connected questions as JSON."""
    ontology_str = json.dumps(ontology, indent=2)
    prompt = f"""
    You are an expert SQL assistant. 
    Here is the current database ontology and schema rules:
    {ontology_str}
    
    Based ONLY on the provided ontology, write a SQL query to answer the following question. 
    You must ALSO provide a brief description explaining how the query works, AND suggest 2-3 logical follow-up questions the user might want to ask next.
    
    CRITICAL INSTRUCTIONS:
    1. Output ONLY a valid JSON object.
    2. The JSON object must have exactly three keys: "sql", "description", and "connected_questions".
    3. "connected_questions" must be a list of strings.
    4. Do not include markdown formatting blocks like ```json or ```sql.
    
    Example Output format:
    {{
      "sql": "SELECT SUM(amount) FROM sales WHERE status = 'Won';",
      "description": "This query calculates the total revenue by summing the amount column in the sales table for all 'Won' deals.",
      "connected_questions": [
        "What is the total revenue broken down by region?",
        "How does this revenue compare to the previous quarter?"
      ]
    }}
    
    Question: {question}
    """
    try:
        llm = project.get_llm(LLM_ID)
        completion = llm.new_completion()
        completion.with_message(prompt, role="user")
        response = completion.execute()
        
        if response.success:
            return response.text
        else:
            return "Error: LLM completion failed."
    except Exception as e:
        return f"Error generating SQL: {e}"
        
# --- SQL EXECUTION (EXTERNAL VIA API) ---
def execute_generated_sql(sql_query):
    try:
        query_runner = client.sql_query(sql_query, connection=CONNECTION_NAME)
        schema = query_runner.get_schema()
        
        if isinstance(schema, dict) and 'columns' in schema:
            columns = [col['name'] for col in schema['columns']]
        else:
            columns = [col['name'] for col in schema]
        
        data = []
        for row in query_runner.iter_rows():
            data.append(row)
            
        query_runner.verify() 
        df = pd.DataFrame(data, columns=columns)
        return df, None
    except Exception as e:
        return None, str(e)


# --- STREAMLIT UI (CHAT AGENT) ---
st.title("Financial Intelligence, Unleashed")
st.write("Powered by Tiger’s advanced analytics to bring you institutional-grade market insights in real time.")
st.markdown("---")

st.markdown("""
    <style>
    /* Target the text inside Streamlit buttons to make it smaller */
    div[data-testid="stButton"] button p {
        font-size: 8px !important; /* Change this number to make it bigger/smaller */
    }
    </style>
""", unsafe_allow_html=True)

# 1. Initialize chat history and button state
if "messages" not in st.session_state:
    st.session_state.messages = []

if "active_prompt" not in st.session_state:
    st.session_state.active_prompt = None

prompt = None
# 2. Suggested Questions
if not st.session_state.messages and not st.session_state.active_prompt:
    
    st.markdown("<p style='font-size: 15px; font-weight: 600; color: #555; margin-bottom: 5px;'>💡 Suggested Questions:</p>", unsafe_allow_html=True)
    
    row1_col1, row1_col2, row1_col3 = st.columns(3)
    # Notice we removed use_container_width=True from all buttons below!
    if row1_col1.button("What is our Total Revenue?"):
        st.session_state.active_prompt = "What is our Total Revenue?"
        st.rerun()
        
    if row1_col2.button("How many leads converted last month?"):
        st.session_state.active_prompt = "How many leads converted last month?"
        st.rerun()
        
    if row1_col3.button("Who are our top 5 sales reps?"):
        st.session_state.active_prompt = "Who are our top 5 sales reps?"
        st.rerun()
    
    row2_col1, row2_col2, row2_col3 = st.columns(3)
    if row2_col1.button("What is the Cost Per Lead (CPL)?"):
        st.session_state.active_prompt = "What is the Cost Per Lead (CPL) for each campaign?"
        st.rerun()
        
    if row2_col2.button("Calculate ROMI by Region"):
        st.session_state.active_prompt = "Calculate Return on Marketing Investment (ROMI) by Region"
        st.rerun()
        
    if row2_col3.button("Identify CAC for converted leads"):
        st.session_state.active_prompt = "Identify Customer Acquisition Cost (CAC) for converted leads"
        st.rerun()
        
# 3. Standard Chat Input
chat_input = st.chat_input("Ask a question about your data...")

# Determine where the prompt came from (chat box or button)
if chat_input:
    prompt = chat_input
elif st.session_state.active_prompt:
    prompt = st.session_state.active_prompt
    st.session_state.active_prompt = None 

# 4. Display historical chat messages on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "description" in message:
            st.info(f"**Query Description:** {message['description']}")
        if "sql" in message:
            st.code(message["sql"], language="sql")
        if "df" in message and isinstance(message["df"], pd.DataFrame):
            st.dataframe(message["df"])
        
        # RENDER CONNECTED QUESTIONS WITH SMALLER FONT
        if "connected_questions" in message and message["connected_questions"]:
            questions_html = "<br>".join([f"• <i>{q}</i>" for q in message["connected_questions"]])
            styled_html = f"""
            <div style='font-size: 13px; color: #666; margin-top: 10px; padding-left: 5px; border-left: 2px solid #ccc;'>
                <b>🔗 Connected Questions to try:</b><br>{questions_html}
            </div>
            """
            st.markdown(styled_html, unsafe_allow_html=True)

# 5. React to user input
if prompt:
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        with st.spinner("Fetching ontology and generating SQL..."):
            current_ontology = load_latest_ontology()
            
            if current_ontology:
                # Generate raw JSON response from LLM
                raw_llm_output = generate_sql_and_description(prompt, current_ontology)
                
                if raw_llm_output.startswith("Error"):
                    st.error(raw_llm_output)
                    st.session_state.messages.append({"role": "assistant", "content": raw_llm_output})
                else:
                    # Clean the output
                    cleaned_output = raw_llm_output.strip()
                    if cleaned_output.startswith("```json"):
                        cleaned_output = cleaned_output[7:]
                    elif cleaned_output.startswith("```"):
                        cleaned_output = cleaned_output[3:]
                    if cleaned_output.endswith("```"):
                        cleaned_output = cleaned_output[:-3]
                    cleaned_output = cleaned_output.strip()
                    
                    # Parse JSON
                    try:
                        response_data = json.loads(cleaned_output)
                        sql_query = response_data.get("sql", "")
                        sql_description = response_data.get("description", "No description provided.")
                        connected_questions = response_data.get("connected_questions", [])
                    except json.JSONDecodeError:
                        st.error("Failed to parse LLM response as JSON. Showing raw output instead.")
                        sql_query = cleaned_output
                        sql_description = "Parsing error: Could not extract description."
                        connected_questions = []
                    
                    # Display the newly added description
                    st.info(f"**Query Description:** {sql_description}")
                    
                    st.markdown("**Generated SQL Query:**")
                    st.code(sql_query, language="sql")
                    
                    with st.spinner("Executing query remotely..."):
                        results_df, error_msg = execute_generated_sql(sql_query)
                        
                        # Save state based on execution success/failure
                        if error_msg:
                            error_text = f"SQL Execution Error: {error_msg}"
                            st.error(error_text)
                            st.session_state.messages.append({
                                "role": "assistant", 
                                "content": error_text,
                                "description": sql_description,
                                "sql": sql_query,
                                "connected_questions": connected_questions
                            })
                        elif results_df is not None:
                            if results_df.empty:
                                empty_msg = "Query executed successfully, but returned 0 rows."
                                st.info(empty_msg)
                                st.session_state.messages.append({
                                    "role": "assistant", 
                                    "content": empty_msg,
                                    "description": sql_description,
                                    "sql": sql_query,
                                    "connected_questions": connected_questions
                                })
                            else:
                                st.dataframe(results_df) 
                                st.session_state.messages.append({
                                    "role": "assistant", 
                                    "content": "Here are your results:",
                                    "description": sql_description,
                                    "sql": sql_query,
                                    "df": results_df,
                                    "connected_questions": connected_questions
                                })
                                
                        # Print the connected questions for the current run
                        if connected_questions:
                            questions_html = "<br>".join([f"• <i>{q}</i>" for q in connected_questions])
                            styled_html = f"""
                            <div style='font-size: 13px; color: #666; margin-top: 10px; padding-left: 5px; border-left: 2px solid #ccc;'>
                                <b>🔗 Connected Questions to try:</b><br>{questions_html}
                            </div>
                            """
                            st.markdown(styled_html, unsafe_allow_html=True)
