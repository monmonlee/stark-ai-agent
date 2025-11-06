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
        '.rb', '.php', '.swift', '.kt'
        ]
    
    # black list: common non-source or redundant files (reference: .gitignore templates)
    exclude_keyworks = [
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

    exclude_keywords_file = any(keyword in filename for keyword in exclude_keyworks)
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
    target_count_hint: int = 10,
) -> str:

    # Backslashes are not allowed inside f-strings.
    # To make file names display neatly line-by-line, define them outside first.
    file_index_all = "\n".join(file_index_all)
    file_index_code = "\n".join(file_index_code)

    prompt = f"""
        You are a **software project analysis expert**. Your mission is:
        1. **Understand the requirements**: The user has submitted a code project and described the functionalities they want to analyze.
        2. **Filter files**: From many files in the project, identify which ones truly implement the described core features.
        3. **Provide execution advice**: Tell the user how to run this project locally.
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
    target_count_hint: int = 10,
) -> dict:

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
    
    # step 3: call LLM-1 to identify key source files and generate execution suggestions
    stage1_report = llm_stage1_navigate(
        problem_description=problem_description,
        file_index_all=file_index_all,
        file_index_code=file_index_code,
        target_count_hint=10,  # optional
    )

    return {
        "status": "received",
        "filename": code_zip.filename,
        "code_files_found": len(file_index_code),
        "report": stage1_report,
    }

if __name__ == "__main__":
    import uvicorn
    # Run the app locally
    uvicorn.run(app, host="0.0.0.0", port=8000)
