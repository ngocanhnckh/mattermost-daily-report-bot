# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application
COPY . .


# Run bot.py when the container launches
CMD ["python", "bot.py"]