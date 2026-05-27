Architecture & Data Flow Design: Internal Dataiku Text-to-SQL Agent

This document outlines the system architecture and data flow for the Text-to-SQL Chat Agent deployed as an internal WebApp within the Dataiku Data Science Studio (DSS) environment.

By utilizing Dataiku as the unified platform, the application benefits from centralized governance, secure credential management, and isolated compute environments.

1. High-Level Architecture Diagram

The following diagram illustrates the structural components of the application. The entire core processing engine is encapsulated within the Dataiku infrastructure.

graph TD
    %% Define Styles
    classDef user fill:#f9f9f9,stroke:#333,stroke-width:2px;
    classDef dss fill:#e1f5fe,stroke:#0288d1,stroke-width:2px;
    classDef external fill:#f3e5f5,stroke:#8e24aa,stroke-width:2px;
    classDef db fill:#fff3e0,stroke:#f57c00,stroke-width:2px;

    %% Nodes
    U[👤 End User / Analyst]:::user
    
    subgraph Dataiku DSS Environment [Dataiku DSS Infrastructure]
        direction TB
        SWA[💻 Streamlit WebApp<br/><i>(Python Code Env)</i>]:::dss
        MF[📁 Managed Folder<br/><i>(ontology.yaml)</i>]:::dss
        LM[🧠 LLM Mesh<br/><i>(Prompt Orchestration)</i>]:::dss
        SQLE[⚙️ Dataiku SQLExecutor2<br/><i>(Query Execution Engine)</i>]:::dss
        CONN[🔌 Dataiku Connections<br/><i>(Secure Credentials)</i>]:::dss
    end

    EXT_LLM[☁️ External LLM Provider<br/><i>(e.g., OpenAI, Anthropic)</i>]:::external
    DWH[(🗄️ Enterprise Data Warehouse<br/><i>(e.g., Snowflake)</i>)]:::db

    %% Connections
    U <-->|1. HTTP/WSS (UI Interaction)| SWA
    SWA -->|2. dataiku.Folder API| MF
    SWA <-->|3. project.get_llm API| LM
    LM <-->|4. Secure API Call| EXT_LLM
    SWA -->|5. dataiku.core.sql API| SQLE
    SQLE -->|6. Retrieves Credentials| CONN
    CONN -->|7. Authenticated Query| DWH
    DWH -->|8. Result Set| SQLE


1.1 Architectural Components Description

Streamlit WebApp: The frontend user interface hosted directly on Dataiku's backend compute nodes. It leverages a dedicated Python Code Environment containing the necessary libraries (streamlit, pandas, PyYAML).

Managed Folder: A governed storage layer inside the Dataiku project containing the ontology.yaml. This ensures the application dynamically reads the latest business logic without requiring code redeployments.

LLM Mesh: Dataiku's centralized LLM gateway. It abstracts the API connectivity to external LLM providers, ensuring prompt logging, cost tracking, and PII masking (if configured) are handled uniformly.

SQLExecutor2 & Connections: Dataiku's internal query routing system. The Streamlit app does not contain raw database credentials; instead, it delegates query execution to Dataiku, which uses securely stored connection parameters to communicate with the target database.

2. Sequence & Data Flow Diagram

The following sequence diagram maps the step-by-step chronological data flow that occurs when a user submits a natural language question via the Chat UI.

sequenceDiagram
    autonumber
    actor User
    participant App as Streamlit WebApp
    participant Folder as Managed Folder (YAML)
    participant Mesh as Dataiku LLM Mesh
    participant Exec as SQLExecutor2
    participant DB as Data Warehouse

    User->>App: Submits Natural Language Question
    
    rect rgb(230, 240, 255)
        Note right of App: Phase 1: Context Gathering
        App->>Folder: Request latest `ontology.yaml` via stream
        Folder-->>App: Returns YAML payload
        App->>App: Parses YAML & formats System Prompt
    end
    
    rect rgb(240, 230, 255)
        Note right of App: Phase 2: SQL Generation
        App->>Mesh: Sends System Prompt + Chat History
        Mesh-->>App: Returns Conversational Response + SQL Block
        App->>App: Regex extracts & sanitizes raw SQL
    end
    
    App->>User: Renders LLM Text Response & Code Expander
    
    rect rgb(255, 240, 230)
        Note right of App: Phase 3: Secure Execution
        App->>Exec: Submits sanitized SQL query
        Exec->>DB: Executes query via Dataiku Connection
        DB-->>Exec: Returns raw data rows
        Exec-->>App: Converts stream to Pandas DataFrame
    end
    
    App->>App: Updates Session State (Memory)
    App->>User: Renders DataFrame as Interactive Table


2.1 Data Flow Technical specifics

Trigger: The user inputs a query via st.chat_input. Streamlit reruns the internal Python script.

Context Hydration: The application utilizes dataiku.Folder(FOLDER_ID).get_download_stream() to pull the absolute latest version of the ontology into memory.

Prompt Injection: The ontology.yaml is serialized into a JSON string and injected into the System Prompt. The entire conversation history (stored in st.session_state) is appended to maintain contextual awareness for follow-up questions.

LLM Invocation: The request is routed internally to Dataiku's LLM Mesh using the llm.new_completion() API.

Sanitization: The application parses the returned string using Regular Expressions to identify and extract the ```sql block, stripping away any conversational Markdown formatting to ensure valid syntax.

Execution & Rendering: The cleaned SQL is passed to dataiku.core.sql.SQLExecutor2(connection=CONN_NAME).query_to_df(). This pushes the compute down to the target Data Warehouse, returning a structured Pandas DataFrame which Streamlit natively renders into an HTML table.
