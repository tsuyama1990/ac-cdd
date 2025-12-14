from fastapi import FastAPI

app = FastAPI(title="AC-CDD Application")

@app.get("/")
def read_root():
    return {"message": "Hello from AC-CDD Environment"}
