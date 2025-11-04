from fastapi import FastAPI, UploadFile, File, Form
import zipfile
import io


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

    # convert the content into a ZIP object
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        file_list = zf.namelist()

    # sample response to confirm data received
    return {
        "status": "received",
        "problem_description": problem_description,
        "filename": code_zip.filename,
        "file_size": code_zip.size,
        "file_in_zip": file_list  
    }

if __name__ == "__main__":
    import uvicorn
    # run the app locally
    uvicorn.run(app, host="0.0.0.0", port=8000)
