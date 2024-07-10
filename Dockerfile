FROM supervisely/base-py-sdk:6.73.94

WORKDIR /app

RUN pip3 install -U supervisely==6.73.128

COPY src /app/src

EXPOSE 80

ENTRYPOINT ["uvicorn", "src.main:app"]
CMD ["--host", "0.0.0.0", "--port", "80"]
