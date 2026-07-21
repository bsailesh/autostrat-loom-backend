# Optional — not needed for the App Runner "source code" deploy path described
# in DEPLOY.md, which builds directly from apprunner.yaml. This is here for
# local Docker testing, or if you later move to ECS/Fargate/EKS.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
