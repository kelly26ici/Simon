import uvicorn

def main():
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        access_log=False,
    )

if __name__ == "__main__":
    main()
