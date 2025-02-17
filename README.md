# LK Gem POS Backend

This project is the backend for the LK Gem POS system. It includes both Django for admin and management functionality, and FastAPI for high-performance APIs. Both share the same database and work in tandem to provide a full solution for managing users, products, sales, and orders.

## Prerequisites

- Docker
- Docker Compose

## Quick Start

1. Clone the repository:

```bash
git clone https://github.com/your-repo.git
cd backend

docker-compose up --build


#source venv/bin/activate     env\Scripts\activate   uvicorn fastapi_app.main:app --reload   brew services start mongodb-community  


#python -m venv .venv

#.venv\Scripts\activate

brew services start mysql
brew services start mongodb-community  


# Stop any running containers and remove volumes
docker-compose down -v

# Build the images
docker-compose build

# Start the services
docker-compose up -d

# Check the logs
docker-compose logs -f

# Connect to MongoDB container
docker exec -it luster-mongodb mongosh -u luster -p 123456

# Test the connection
use luster
db.test.insert({ test: "test" })
db.test.find()


CREATE USER 'luster'@'localhost' IDENTIFIED BY '076042NimE';
GRANT ALL PRIVILEGES ON luster.* TO 'luster'@'localhost';

CREATE DATABASE luster;

ngrok http 8000
