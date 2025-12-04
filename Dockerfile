FROM supervisely/base-py-sdk:6.73.322

RUN pip install "git+https://github.com/supervisely/supervisely.git@oriented-bbox"

WORKDIR /app

COPY src /app/src

EXPOSE 80

ENTRYPOINT ["uvicorn", "src.main:app"]
CMD ["--host", "0.0.0.0", "--port", "80"]
