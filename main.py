import uvicorn

if __name__ == '__main__':
    uvicorn.run('src.App:app', host='129.6.196.189', port=8000, reload=True)