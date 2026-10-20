from fastapi import FastAPI

app = FastAPI(
    title="BuzzIn",
    description="change me",
    version="1.0.0"
)

@app.get("/")
async def root():
    return {"status": "healthy", "message": "Hello World!"}
