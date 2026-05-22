import streamlit as st
import dataikuapi
import pandas as pd
import yaml
import json

# --- SECURE CONFIGURATION ---
# These will be populated by Streamlit Cloud's Secrets Manager
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
        # Download the file via REST API
        file_stream = folder.get_file("ontology.yaml")
        ontology_data = yaml.safe_load(file_stream.content)
        return ontology_data
    except Exception as e:
        st.error(f"Error loading ontology: {e}")
        return None

# --- LLM INTEGRATION (EXTERNAL) ---
def generate_sql(question, ontology):
    ontology_str = json.dumps(ontology, indent=2)
    prompt = f"""
    You are an expert SQL assistant. 
    Here is the current database ontology and schema rules:
    {ontology_str}
    
    Based ONLY on the provided ontology, write a SQL query to answer the following question. 
    Return ONLY the raw SQL query, no markdown, no explanations.
    
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
        # We proxy the query through Dataiku's REST API using the connection name
        query_runner = client.sql_query(sql_query, connection=CONNECTION_NAME)
        
        # Extract schema to build pandas columns
        schema = query_runner.get_schema()
        
        # Check if schema is a dictionary or directly a list
        if isinstance(schema, dict) and 'columns' in schema:
            columns = [col['name'] for col in schema['columns']]
        else:
            columns = [col['name'] for col in schema]
        
        # Fetch the data row by row
        data = []
        for row in query_runner.iter_rows():
            data.append(row)
            
        query_runner.verify() # Verifies stream completed successfully
        
        # Convert to DataFrame
        df = pd.DataFrame(data, columns=columns)
        return df, None
    except Exception as e:
        return None, str(e)


# --- STREAMLIT UI (CHAT AGENT) ---
st.title("Financial Intelligence, Unleashed")
st.write("Powered by Tiger’s advanced analytics to bring you institutional-grade market insights in real time.")
st.markdown("---")

# 1. Initialize chat history in session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Variable to hold the user's query, whether from a button or chat input
prompt = None

# 2. Suggested Questions (Only show if chat history is empty)
if not st.session_state.messages:
    st.write("**💡 Suggested Questions:**")
    
    row1_col1, row1_col2, row1_col3 = st.columns(3)
    if row1_col1.button("What is our Total Revenue?", use_container_width=True):
        prompt = "What is our Total Revenue?"
    if row1_col2.button("How many leads converted last month?", use_container_width=True):
        prompt = "How many leads converted last month?"
    if row1_col3.button("Who are our top 5 sales reps?", use_container_width=True):
        prompt = "Who are our top 5 sales reps?"
    
    row2_col1, row2_col2, row2_col3 = st.columns(3)
    if row2_col1.button("What is the Cost Per Lead (CPL)?", use_container_width=True):
        prompt = "What is the Cost Per Lead (CPL) for each campaign?"
    if row2_col2.button("Calculate ROMI by Region", use_container_width=True):
        prompt = "Calculate Return on Marketing Investment (ROMI) by Region"
    if row2_col3.button("Identify CAC for converted leads", use_container_width=True):
        prompt = "Identify Customer Acquisition Cost (CAC) for converted leads"

# 3. Standard Chat Input
chat_input = st.chat_input("Ask a question about your data...")
if chat_input:
    prompt = chat_input

# 4. Display historical chat messages on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "sql" in message:
            st.code(message["sql"], language="sql")
        if "df" in message and isinstance(message["df"], pd.DataFrame):
            st.dataframe(message["df"])

# 5. React to user input (either from chat box or suggested buttons)
if prompt:
    # Display user message in chat container
    st.chat_message("user").markdown(prompt)
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Generate and display assistant response
    with st.chat_message("assistant"):
        with st.spinner("Fetching ontology and generating SQL..."):
            current_ontology = load_latest_ontology()
            
            if current_ontology:
                # Generate raw response
                raw_llm_output = generate_sql(prompt, current_ontology)
                
                # Clean the output to remove Markdown backticks
                sql_query = raw_llm_output.strip()
                if sql_query.startswith("```sql"):
                    sql_query = sql_query[6:]
                elif sql_query.startswith("```"):
                    sql_query = sql_query[3:]
                if sql_query.endswith("```"):
                    sql_query = sql_query[:-3]
                sql_query = sql_query.strip()
                
                st.markdown("**Generated SQL Query:**")
                st.code(sql_query, language="sql")
                
                if not raw_llm_output.startswith("Error"):
                    with st.spinner("Executing query remotely..."):
                        results_df, error_msg = execute_generated_sql(sql_query)
                        
                        if error_msg:
                            error_text = f"SQL Execution Error: {error_msg}"
                            st.error(error_text)
                            st.session_state.messages.append({
                                "role": "assistant", 
                                "content": error_text,
                                "sql": sql_query
                            })
                        elif results_df is not None:
                            if results_df.empty:
                                empty_msg = "Query executed successfully, but returned 0 rows."
                                st.info(empty_msg)
                                st.session_state.messages.append({
                                    "role": "assistant", 
                                    "content": empty_msg,
                                    "sql": sql_query
                                })
                            else:
                                st.dataframe(results_df) 
                                st.session_state.messages.append({
                                    "role": "assistant", 
                                    "content": "Here are your results:",
                                    "sql": sql_query,
                                    "df": results_df
                                })
