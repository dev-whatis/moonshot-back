# ==============================================================================
# Dockerfile Optimized for Google Cloud Run
# ==============================================================================
# Use an official lightweight Python image.
# https://hub.docker.com/_/python
FROM python:3.11-slim

# Set environment variables
# 1. PYTHONUNBUFFERED: Ensures Python output (like print statements) is sent
#    straight to the terminal without being buffered, which is good for logging.
# 2. PYTHONDONTWRITEBYTECODE: Prevents Python from writing .pyc files to disc.
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Set the working directory in the container
WORKDIR /app

# --- Dependency Installation (Cached Layer) ---
# Copy only the requirements file first to take advantage of Docker layer caching.
# This layer is only rebuilt if requirements.txt changes.
COPY requirements.txt .

# Install the dependencies.
# --no-cache-dir: Disables the pip cache, which reduces image size.
# --upgrade pip: Ensures we have the latest version of pip.
# --requirement: Specifies the file to install from.
RUN pip install --no-cache-dir --upgrade pip -r requirements.txt

# --- Application Code ---
# Copy the application source code into the container.
# The 'firebase-service-account.json' file is NOT copied, as it will be
# mounted at runtime from Google Secret Manager.
COPY ./app ./app

# --- Security: Create and switch to a non-root user ---
# Create a new system user 'appuser' with no home directory and no shell access.
# This is a security best practice, even on a managed platform like Cloud Run.
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# Grant ownership of the /app directory to the new user.
# This ensures the application can run without permission errors.
RUN chown -R appuser:appgroup /app

# Switch to the non-root user. All subsequent commands will be run as 'appuser'.
USER appuser

# --- Port Exposure & Runtime Command ---
# Expose a default port. Cloud Run will override this with the value of $PORT.
# This instruction is mainly for documentation and local `docker run` usage.
EXPOSE 8000

# The command to run the application.
# This is the key change for Google Cloud Run.
# We use `sh -c` to allow shell expansion of the `$PORT` environment variable,
# which is provided automatically by the Cloud Run environment.
# --host 0.0.0.0: Makes the server accessible from outside the container.
# --port $PORT: Binds the server to the port assigned by Cloud Run.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port $PORT"]