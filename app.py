from fastapi import FastAPI, UploadFile, File, Form
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv
import zipfile
import io, os, json, zipfile

# Global variables
# openai api
load_dotenv(find_dotenv())  # Load .env file
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    raise ValueError("cannot find OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# fastapi
app = FastAPI()

# Purpose: build a whitelist and blacklist to initially exclude non-code files
def read_file_or_not(filename):
    
    # white list: programming-related file extensions for LLM (reference: GitHub Linguist)
    code_extensions = [
        '.py', '.js', '.ts', '.jsx', '.tsx',
        '.java', '.go', '.cpp', '.c', '.rs',
        '.rb', '.php', '.swift', '.kt',

        # Schema & API definition files
        '.gql', '.graphql',  # GraphQL schema
        '.proto',            # Protocol Buffers
        ]
    
    # black list: common non-source or redundant files (reference: .gitignore templates)
    exclude_keywords = [
        '.test.', '.spec.',           # testing files
        'node_modules/', '__pycache__/',  # dependency folders
        '.min.js',                    # minified build files
    ]

    exclude_extensions = [
        # documents
        '.md', '.txt', '.doc', '.docx', '.pdf', '.rtf',
        '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp',
        # data or settings
        '.csv', '.tsv', '.json', '.yaml', '.yml', '.xml',
        '.lock', '.log', '.ini', '.cfg', '.conf', '.toml', '.bak',
        # system and environment files
        '.env', '.gitignore', '.dockerignore', '.DS_Store', 'Thumbs.db',
        # binary, compressed or image files
        '.zip', '.tar', '.gz', '.7z', '.rar',
        '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp',
        '.mp3', '.mp4', '.mov', '.avi', '.ogg', '.wav'
    ]

    is_code_file = any((filename.endswith(ext)) for ext in code_extensions)  # use any() to check filename
    if not is_code_file: 
        return False

    exclude_keywords_file = any(keyword in filename for keyword in exclude_keywords)
    if exclude_keywords_file:
        return False        
    
    exclude_extension_file = any(filename.endswith(ext) for ext in exclude_extensions)
    if exclude_extension_file:
        return False
    
    return True

def llm1_prompt(
    problem_description: str, 
    file_index_all: list, 
    file_index_code: list,
) -> str:
    """
    Build the Stage-1 LLM prompt.
    Purpose: summarize user requirement + file list + filtered code files, then ask the model to identify key source files and execution suggestions.
    """

    # Backslashes are not allowed inside f-strings.
    # To make file names display neatly line-by-line, define them outside first.
    file_index_all = "\n".join(file_index_all)
    file_index_code = "\n".join(file_index_code)

    prompt = f"""
        You are a software project analysis expert. Your mission is:
        1. Understand the requirements: The user has submitted a code project and described the functionalities they want to analyze.
        2. Filter files: From many files in the project, identify which ones truly implement the described core features.
        3. Provide execution advice: Tell the user how to run this project locally.
        ---
        {problem_description}
        ---
        ## Complete File List in the Project 
        {file_index_all}
        ---
        ## Filtered Code Files
        {file_index_code}
        ---
        ## Your Task
        Please return a **JSON object** in the following format:
        ```json
        {{
            "context_for_llm2": "A short summary explaining which files likely implement the described features (to guide LLM-2).",
            "execution_plan_suggestion": "Practical instructions for running this project (e.g., installing dependencies, starting the service).",
            "key_files_to_analyze": ["5–10 key file names that actually implement the described features"]
        }}
        ```
        ##  Notes
        1. context_for_llm2: A brief (100–200 word) description like
        “The channel creation feature is implemented in channel.resolver.ts and channel.service.ts.”

        2. execution_plan_suggestion: Include real executable commands, such as
        “Run npm install and then npm run start:dev.”

        3. key_files_to_analyze: Select only files that directly implement the main features.
        Avoid including test files, config files, or utilities.

        4. Return only JSON — do not include any other text!
        """
    return prompt

   
def llm_stage1_navigate(
    problem_description: str, 
    file_index_all:list, 
    file_index_code: list,
) -> dict:
    """
    Purpose: Calls GPT-4o-mini to analyze the entire project directory, identify key functional files, and suggest how to execute the project.
    """

    # establish prompt
    prompt = llm1_prompt(problem_description, file_index_all, file_index_code)


    try:

        response = openai_client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[ 
                # System instruction: define the LLM's role
                {"role": "system", "content": "You are a software project analysis expert, good at understanding coding structure and position identify."},
                # User query
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1500
        )

        llm_output = response.choices[0].message.content.strip() 

        # Remove possible markdown syntax (```json ... ```)
        if llm_output.startswith("```json"):
            llm_output = llm_output[7:]
        if llm_output.endswith("```"):
            llm_output = llm_output[:-3]
        
        result = json.loads(llm_output)
        
        # Validate output format
        assert "context_for_llm2" in result
        assert "execution_plan_suggestion" in result
        assert "key_files_to_analyze" in result
        
        return result
    
    except json.JSONDecodeError as e:  # When LLM output is not valid JSON
        raise ValueError(f"LLM-1 response format error: {e}\nOriginal output: {llm_output}")
    except Exception as e:
        raise RuntimeError(f"LLM-1 call failed: {e}")


def prepare_file_for_llm2(key_files: list[str], code_contents: dict) -> dict:
    """
    Purpose: Match filenames selected by LLM-1 with actual decoded source files.
    Returns a dictionary containing filename–content pairs for LLM-2.
    """

    result = []

    # Match key file names with actual full paths in code_contents
    for relative_path in key_files:
        matched_file = None
        for full_path in code_contents.keys():
            if full_path.endswith(relative_path):
                matched_file = full_path
                break # stop searching once a match is found

        if matched_file: # found a matching code file
            result.append(
                {"filename": relative_path,
                "content": code_contents[matched_file]
                })
            print(f"sucessfully found {relative_path}")
        else:
            print(f"warning: cannot find {relative_path}")
    
    return {"key_files_content": result}


def llm2_prompt(problem_description: str, stage1_report: dict, code_files_text: list[str]) -> str:
    """
    Purpose: Construct the Stage-2 LLM prompt: combine user requirements, Stage-1 report, and full code context to locate feature implementations.
    """
    
    prompt = f"""
    You are an expert code analyst, Your task is to locate the exact implementation of each feature described in the user's requirements.

    ---
    ## User Requirements (Problem Description)
    {problem_description}
    
    ---
    ## Project Overview (From stage 1 Analysis)
    {stage1_report}

    ---
    ## Core Code Files
    {code_files_text}
    
    ---
    ## Your Task

    1. Identify each distinct feature mentioned in the problem description
    2. For each feature, find ALL files and functions that implement it
    3. Locate the exact line numbers where each function is defined

    Return a JSON object in this exact format:
    ```json
    {{
    "feature_analysis": [
        {{
        "feature_description": "實現`建立頻道`功能",
        "implementation_location": [
            {{
            "file": "src/modules/channel/channel.resolver.ts",
            "function": "createChannel",
            "lines": "13-16"
            }},
            {{
            "file": "src/modules/channel/channel.service.ts",
            "function": "create",
            "lines": "21-24"
            }}
        ]
        }}
    ],
    "execution_plan_suggestion": "{stage1_report['execution_plan_suggestion']}"
    }}
    ```

    ---
    Rules:
    1. One Feature = One object in feature_analysis array
    2. Each feature MUST list ALL related files where it's implemented
    3. File pathe MUST NOT include the root directory (e.g., use `src/app.py`, not `project-main/src/app.py`)
    4. The "lines" field MUST include the COMPLETE function definition, Start from the FIRST line of the function (including any decorators or comments directly above it), end at the LAST closing brace of the function
    5. Function names must match the actual function/method names in the code
    6. Return ONLY valid JSON — no explanations, no markdown, no extra text
    7. Return 'feature_description' and 'execution_plan_suggestion' in traditional Mandarin
    
    ---

    ## Example Feature Breakdown

    If the problem description says: "建立一個多頻道論壇 API，支援建立頻道、在頻道中傳送訊息、按時間倒序列出頻道中的訊息"

    Then you should identify 3 features:
    - Feature 1: 建立頻道
    - Feature 2: 在頻道中傳送訊息  
    - Feature 3: 按時間倒序列出頻道中的訊息

    Each feature should trace through ALL files involved in its implementation.

    ## Line example:
        - If a function starts at line 22 (with comment) and ends at line 40 (closing brace)
        - Then "lines" should be "22-40"
        - NOT just the first few lines like "22-24"
    """
    return prompt

def format_code_files(stage2_input):
    """
    Purpose: Convert Stage-2 input into a readable text block with line numbers for feeding into the LLM.
    """

    code_files_text = ""
    for item in stage2_input["key_files_content"]:
        code_files_text += f"\n\n{'='*50}\n"
        code_files_text += f"FILE: {item['filename']}\n"
        code_files_text += f"{'='*50}\n"

        # Add line numbers
        lines = item['content'].split('\n')
        for i, line in enumerate(lines, start=1):
            code_files_text += f"{i:4d} | {line}\n"
            
    return code_files_text


def llm_stage2_anaylze(
    problem_description: str, 
    stage1_report: dict, 
    stage2_input: dict
    ) -> dict:
    """
    Purpose:  Calls GPT-4o-mini to deeply analyze selected source files and generate the final structured JSON report.
    """

    # Format code files for model input
    code_files_text = format_code_files(stage2_input)

    # Build the Stage-2 prompt
    prompt = llm2_prompt(problem_description, stage1_report, code_files_text)

    try:

        response = openai_client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[ 
                # System instruction: define the LLM's role
                {"role": "system", "content": "You are an expert code analyst, good at understanding coding structure and position identify."},
                # User query
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1500
        )

        llm_output = response.choices[0].message.content.strip() 

        # Remove possible markdown syntax (```json ... ```)
        if llm_output.startswith("```json"):
            llm_output = llm_output[7:]
        if llm_output.endswith("```"):
            llm_output = llm_output[:-3]
        
        result = json.loads(llm_output)

        return result
    
    except json.JSONDecodeError as e:  # When LLM output is not valid JSON
        raise ValueError(f"LLM-2 response format error: {e}\nOriginal output: {llm_output}")
    except Exception as e:
        raise RuntimeError(f"LLM-2 call failed: {e}")



# First API: for testing
@app.get("/")
def hello():
    return {"message": "Hello! API is running!"}

# Second API: receive uploaded file (main feature)
@app.post("/analyze")
async def analyze_code(
    problem_description: str = Form(...),
    code_zip: UploadFile = File(...) 
    # UploadFile = File object provided by FastAPI.
    # The uploaded file is wrapped inside this object.
):
    # step 1: read the uploaded content
    content = await code_zip.read()

    # step 2: list all filenames inside the zip and filter code files
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        file_index_all = zf.namelist()
        file_index_code = [fn for fn in file_index_all if read_file_or_not(fn)]
        # read code files directly to minimize I/O operations
        code_contents = {}
        for filename in file_index_code:
            try:
                code_contents[filename] = zf.open(filename).read().decode('utf-8') # 對應檔名的內容解碼
            except UnicodeDecodeError:
                print(" Cannot decode {filename}")
                continue 
    
    # step 3: call LLM-1 to identify key source files and generate execution suggestions
    stage1_report = llm_stage1_navigate(
        problem_description=problem_description,
        file_index_all=file_index_all,
        file_index_code=file_index_code,
    )
    print(f"Stage 1 structure：{stage1_report.keys()}")

    # step4: prepare decode files for LLM-2
    key_files =  stage1_report["key_files_to_analyze"]
    print(f"stage 1 selected files：{key_files}")
    stage2_input = prepare_file_for_llm2(key_files, code_contents)

    # step5: call LLM-2 for final Json output
    stage2_report = llm_stage2_anaylze(
        problem_description=problem_description,
        stage1_report=stage1_report,
        stage2_input=stage2_input,
    )

    return stage2_report

if __name__ == "__main__":
    import uvicorn
    # Run the app locally
    uvicorn.run(app, host="0.0.0.0", port=8000)



