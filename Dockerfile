FROM supervisely/base-py-sdk:6.73.56

EXPOSE 80

ENTRYPOINT ["uvicorn"]
CMD ["src.main:app", "--host", "0.0.0.0", "--port", "80", "--ws", "websockets"]

RUN pip3 install -U supervisely==6.73.56
