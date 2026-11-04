# Use the same Python version as CI
FROM python:3.12-slim

# Set the working directory inside the container
WORKDIR /app

# Install pinned dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Folder for saved records (mount a volume here to keep data)
RUN mkdir -p /app/data

# No real key is baked in; pass it with -e or --env-file
ENV GEMINI_API_KEY=""

# Flask listens on this port
EXPOSE 5000

# Start the web app on all interfaces
CMD ["python", "-m", "flask", "--app", "main:create_app", "run", "--host", "0.0.0.0", "--port", "5000"]