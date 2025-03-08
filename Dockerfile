# Use the official Python 3.13.1 image as a base
FROM python:3.13.1

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file first (to leverage caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files
COPY . .

# Expose the port FastAPI runs on (change if needed)
EXPOSE 8000

# Command to run FastAPI using Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
