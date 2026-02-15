.PHONY: all build up down logs clean restart

# Default target — build and start everything
all:
	docker compose up --build

# Build images only
build:
	docker compose build

# Start in background (detached)
up:
	docker compose up -d --build

# Stop and remove containers
down:
	docker compose down

# Follow live logs
logs:
	docker compose logs -f

# Full cleanup: remove containers, volumes, and images
clean:
	docker compose down -v --rmi local

# Restart everything
restart: down up
