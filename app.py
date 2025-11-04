from fastapi import FastAPI, UploadFile, File, Form
import zipfile
import io


def read_file_or_not(filename):
    
    # white list: programming-related file extensions for LLm (reference by github-linguist)
    code_extensions = [
        '.py', '.js', '.ts', '.jsx', '.tsx',
        '.java', '.go', '.cpp', '.c', '.rs',
        '.rb', '.php', '.swift', '.kt'
        ]
    
    # black list:  common non-source or redundant files (reference by .gitignore templates)
    exclude_keyworks = [
        '.test.', '.spec.',           # testing files
        'node_modules/', '__pycache__/',  # dependent folders
        '.min.js',                    # minified build files
    ]

    exclude_extensions = [
        # documents
        '.md', '.txt', '.doc', '.docx', '.pdf', '.rtf',
        '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp',
        # data or settings
        '.csv', '.tsv', '.json', '.yaml', '.yml', '.xml',
        '.lock', '.log', '.ini', '.cfg', '.conf', '.toml', '.bak',
        # systems and enviorment files
        '.env', '.gitignore', '.dockerignore', '.DS_Store', 'Thumbs.db',
        # binary, compressed or image files
        '.zip', '.tar', '.gz', '.7z', '.rar',
        '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp',
        '.mp3', '.mp4', '.mov', '.avi', '.ogg', '.wav'
    ]

    is_code_file = any((filename.endswith(ext)) for ext in code_extensions)  # use any to check filename 
    if not is_code_file: 
        return False

    exclude_keywords_file = any(keyword in filename for keyword in exclude_keyworks)
    if exclude_keywords_file:
        return False        
    
    exclude_extension_file = any(filename.endswith(ext) for ext in exclude_extensions)
    if exclude_extension_file:
        return False
    
    return True
   


app = FastAPI()

# first api: for testing
@app.get("/")
def hello():
    return {"message": "Hello! API is running!"}

# second api: receive uploaded file(main feature)
@app.post("/analyze")
async def analyze_code(
    problem_description: str = Form(...),
    code_zip: UploadFile = File(...) 
    # UploadFile = File object provided by FastAPI. 
    # The uploaded file is wrapped as this object.

):
    # read the upload content
    content = await code_zip.read()

    code_files = []
    # convert the content into a ZIP object
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        for filename in zf.namelist():
            if read_file_or_not(filename):
                code_files.append(filename)


    # sample response to confirm data received
    return {
        "status": "received",
        "problem_description": problem_description,
        "filename": code_zip.filename,
        "total_files": len(zf.namelist()),
        "code_files_found": len(code_files),
        "code_files": code_files  # only show qualify files
    }

if __name__ == "__main__":
    import uvicorn
    # run the app locally
    uvicorn.run(app, host="0.0.0.0", port=8000)