FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY server.py .
COPY start_api.sh .

# Make startup script executable
RUN chmod +x start_api.sh

# Expose port
EXPOSE 8000

# Run the server
CMD ["./start_api.sh"]
